from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from .. import auditoria
from ..config import settings
from ..db import get_conn
from ..acesso import exigir_acesso_a_ocorrencia
from ..deps import (
    checar_quem_pode_registrar,
    exigir_gestao_da_area,
    usuario_atual,
    usuario_opcional,
)
from ..paginacao import paginar
from ..schemas import OcorrenciaIn, OcorrenciaOut, PaginaOcorrencias

router = APIRouter(prefix="/ocorrencias", tags=["Ocorrências"])

# Colunas devolvidas ao app. A gravidade mostrada é:
# 1) A verificada pelo gestor; 2) A informada pelo cidadão (ou preenchida pela IA); 3) A pior estimada em deteccoes_ia.
COLUNAS = """
    id_ocorrencia, tipo, categoria, descricao,
    COALESCE(
        gravidade_verificada,
        gravidade_cidadao,
        (SELECT (ARRAY_AGG(d.gravidade_estimada ORDER BY
            CASE d.gravidade_estimada WHEN 'grave' THEN 3 WHEN 'moderado' THEN 2
                                      WHEN 'leve' THEN 1 ELSE 0 END DESC))[1]
         FROM deteccoes_ia d WHERE d.id_ocorrencia = ocorrencias.id_ocorrencia)
    ) AS gravidade,
    latitude, longitude, status, canal_registro,
    criado_em, verificada_em, id_ocorrencia_principal, id_area, situacao_ia,
    CASE WHEN triagem_decisao = 'recusada' THEN 'recusada_gestor'
         WHEN triagem_decisao = 'aprovada' THEN 'aprovada_gestor'
         WHEN situacao_ia = 'confirmada'   THEN 'confirmada_ia'
         WHEN situacao_ia = 'triagem'      THEN 'em_triagem'
         WHEN NOT COALESCE((SELECT t.usa_ia FROM tipos_ocorrencia t
                             WHERE t.codigo = ocorrencias.tipo), TRUE) THEN 'sem_ia'
         ELSE 'sem_foto' END AS verificacao
"""

MAX_GRAUS_MAPA = 10  # tamanho máximo da área pedida no mapa (em graus)


def _checar_tipo(conn, dados: OcorrenciaIn) -> None:
    """Valida tipo, categoria e gravidade contra o catálogo (e dá mensagem clara)."""
    t = conn.execute(
        "SELECT nome, usa_gravidade, categorias, ativo FROM tipos_ocorrencia WHERE codigo = %s",
        (dados.tipo,),
    ).fetchone()
    if t is None or not t["ativo"]:
        raise HTTPException(422, "Tipo de ocorrência inválido ou desativado.")
    if t["categorias"]:
        if dados.categoria is None:
            raise HTTPException(422, f"Informe a categoria. Opções: {', '.join(t['categorias'])}")
        if dados.categoria not in t["categorias"]:
            raise HTTPException(
                422,
                f"Categoria inválida para {t['nome']}. Opções: {', '.join(t['categorias'])}",
            )
    elif dados.categoria is not None:
        raise HTTPException(422, f"{t['nome']} não tem categoria.")
    if dados.gravidade is not None and not t["usa_gravidade"]:
        raise HTTPException(422, f"Gravidade não se aplica a {t['nome']}.")


def _checar_area_de_atendimento(conn, lat: float, lon: float) -> tuple[int | None, bool]:
    """Cerca geográfica: só aceita ocorrência dentro de uma área de atendimento ativa
    (com tolerância na divisa por causa do erro do GPS)."""
    r = conn.execute(
        """
        WITH p AS (
            SELECT ST_SetSRID(ST_MakePoint(%(lon)s::float8, %(lat)s::float8), 4326)::geography AS geo
        ),
        achada AS (
            SELECT a.id_area, a.exige_residencia FROM areas_atendimento a, p
            WHERE a.ativa AND ST_DWithin(a.geometria, p.geo, %(tol)s::float8)
            ORDER BY ST_Distance(a.geometria, p.geo) LIMIT 1
        )
        SELECT (SELECT count(*) FROM areas_atendimento WHERE ativa) AS total,
               (SELECT string_agg(nome, ', ' ORDER BY nome) FROM areas_atendimento WHERE ativa) AS nomes,
               (SELECT id_area FROM achada) AS id_area,
               coalesce((SELECT exige_residencia FROM achada), false) AS exige_residencia
        """,
        {"lat": lat, "lon": lon, "tol": settings.tolerancia_area_m},
    ).fetchone()
    if r["total"] > 0 and r["id_area"] is None:
        raise HTTPException(
            422,
            f"Este local está fora da área de atendimento ({r['nomes']}). "
            "Só é possível registrar ocorrências dentro dela.",
        )
    return r["id_area"], r["exige_residencia"]


@router.post("", response_model=OcorrenciaOut, status_code=201)
def criar(dados: OcorrenciaIn, u=Depends(usuario_atual), conn=Depends(get_conn)):
    """Registra uma ocorrência. Se já houver uma aberta por perto, avisa (409)."""
    _checar_tipo(conn, dados)

    # 1) Freio contra spam: limite de registros por hora
    n = conn.execute(
        """
        SELECT count(*) AS n FROM ocorrencias
        WHERE id_usuario_criador = %s AND criado_em > now() - interval '1 hour'
        """,
        (u["id_usuario"],),
    ).fetchone()["n"]
    if n >= settings.limite_ocorrencias_hora:
        raise HTTPException(429, "Limite de registros por hora atingido. Tente mais tarde.")

    # 2) Cerca geográfica e verificação de permissão/residência no município
    id_area, exige_residencia = _checar_area_de_atendimento(conn, dados.latitude, dados.longitude)
    checar_quem_pode_registrar(u, id_area, exige_residencia)

    # 3) Duplicidade: mesmo tipo e categoria, aberta, num raio de poucos metros
    if not dados.criar_mesmo_assim:
        proximas = conn.execute(
            """
            WITH p AS (
                SELECT ST_SetSRID(ST_MakePoint(%(lon)s::float8, %(lat)s::float8), 4326)::geography AS geo
            )
            SELECT o.id_ocorrencia, o.status, o.criado_em,
                   round(ST_Distance(o.localizacao, p.geo)::numeric, 1)::float8 AS distancia_m
            FROM ocorrencias o, p
            WHERE o.status = 'aberta'
              AND o.tipo = %(tipo)s
              AND o.id_area IS NOT DISTINCT FROM %(id_area)s::int
              AND o.categoria IS NOT DISTINCT FROM %(categoria)s::text
              AND ST_DWithin(o.localizacao, p.geo, %(raio)s::float8)
            ORDER BY distancia_m
            LIMIT 5
            """,
            {
                "lat": dados.latitude,
                "lon": dados.longitude,
                "tipo": dados.tipo,
                "id_area": id_area,
                "categoria": dados.categoria,
                "raio": settings.raio_duplicidade_m,
            },
        ).fetchall()
        if proximas:
            raise HTTPException(
                409,
                detail={
                    "codigo": "ocorrencia_duplicada",
                    "mensagem": (
                        "Já existe uma ocorrência parecida aberta por perto. "
                        "Envie criar_mesmo_assim=true para registrar assim mesmo."
                    ),
                    "proximas": [
                        {
                            "id_ocorrencia": p["id_ocorrencia"],
                            "distancia_m": p["distancia_m"],
                            "status": p["status"],
                            "criado_em": p["criado_em"].isoformat(),
                        }
                        for p in proximas
                    ],
                },
            )

    # 4) Grava a ocorrência, o primeiro item do histórico e a auditoria
    canal = "app_cidadao" if u["papel"] == "cidadao" else "painel_gestao"
    o = conn.execute(
        f"""
        INSERT INTO ocorrencias
            (tipo, categoria, descricao, gravidade_cidadao,
             latitude, longitude, canal_registro, id_usuario_criador, id_area)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING {COLUNAS}
        """,
        (
            dados.tipo,
            dados.categoria,
            dados.descricao,
            dados.gravidade,
            dados.latitude,
            dados.longitude,
            canal,
            u["id_usuario"],
            id_area,
        ),
    ).fetchone()

    conn.execute(
        """
        INSERT INTO historico_status
            (id_ocorrencia, id_usuario, status_anterior, status_novo, justificativa)
        VALUES (%s, %s, NULL, 'aberta', 'Ocorrência registrada')
        """,
        (o["id_ocorrencia"], u["id_usuario"]),
    )
    auditoria.registrar(
        conn,
        "ocorrencia_criada",
        u["id_usuario"],
        "ocorrencias",
        o["id_ocorrencia"],
        {"tipo": dados.tipo, "ignorou_aviso_duplicidade": dados.criar_mesmo_assim},
    )
    return o


@router.get("/mapa")
def mapa(
    lat_min: Annotated[float, Query(ge=-90, le=90)],
    lat_max: Annotated[float, Query(ge=-90, le=90)],
    lon_min: Annotated[float, Query(ge=-180, le=180)],
    lon_max: Annotated[float, Query(ge=-180, le=180)],
    tipo: Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9_]{1,19}$")] = None,
    id_area: Annotated[int | None, Query(ge=1, description="Só ocorrências desta cidade/área")] = None,
    verificacao: Annotated[
        Literal["verificadas", "todas"],
        Query(
            description=(
                "verificadas = só o que a IA confirmou ou o gestor aprovou; "
                "todas = inclui as que ainda estão em triagem ou sem foto"
            )
        ),
    ] = "verificadas",
    limite: Annotated[int, Query(ge=1, le=2000)] = 500,
    u=Depends(usuario_opcional),
    conn=Depends(get_conn),
):
    """Ocorrências abertas dentro de uma área, em GeoJSON (pronto para Leaflet/Mapbox).

    Qualquer pessoa vê as verificadas. `verificacao=todas` (inclui triagem e sem foto) é só para
    gestão: o gestor vê apenas a própria cidade; o admin vê qualquer uma.
    """
    if lat_min >= lat_max or lon_min >= lon_max:
        raise HTTPException(422, "A área precisa ter lat_min < lat_max e lon_min < lon_max")
    if lat_max - lat_min > MAX_GRAUS_MAPA or lon_max - lon_min > MAX_GRAUS_MAPA:
        raise HTTPException(422, "Área muito grande. Dê mais zoom no mapa.")

    if verificacao == "todas":
        if u is None:
            raise HTTPException(
                401,
                "Entre com uma conta de gestão para ver as ocorrências ainda não verificadas.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if u["papel"] not in ("gestor", "admin"):
            raise HTTPException(
                403,
                {"codigo": "so_gestao", "mensagem": "Só a gestão vê ocorrências ainda não verificadas."},
            )
        if u["papel"] == "gestor":
            if id_area is not None:
                exigir_gestao_da_area(u, id_area)  # 403 se pediu outra cidade
            id_area = u["id_area_gestao"]

    linhas = conn.execute(
        """
        SELECT v.id_ocorrencia, v.tipo, v.categoria, v.gravidade, v.status, v.canal_registro,
               v.confianca_max, v.criado_em, v.latitude, v.longitude, v.id_area,
               CASE WHEN o.triagem_decisao = 'aprovada' THEN 'aprovada_gestor'
                    WHEN o.situacao_ia = 'confirmada'   THEN 'confirmada_ia'
                    WHEN o.situacao_ia = 'triagem'      THEN 'em_triagem'
                    WHEN NOT t.usa_ia                   THEN 'sem_ia'
                    ELSE 'sem_foto' END AS verificacao
        FROM vw_mapa_ocorrencias v
        JOIN ocorrencias o ON o.id_ocorrencia = v.id_ocorrencia
        JOIN tipos_ocorrencia t ON t.codigo = v.tipo
        WHERE ST_Intersects(
                  v.localizacao,
                  ST_MakeEnvelope(%(lon_min)s::float8, %(lat_min)s::float8,
                                  %(lon_max)s::float8, %(lat_max)s::float8, 4326)::geography)
          AND (%(tipo)s::text IS NULL OR v.tipo = %(tipo)s::text)
          AND (%(id_area)s::int IS NULL OR v.id_area = %(id_area)s::int)
          AND o.triagem_decisao IS DISTINCT FROM 'recusada'
          AND (%(verif)s::text = 'todas'
               OR NOT t.usa_ia
               OR o.situacao_ia = 'confirmada'
               OR o.triagem_decisao = 'aprovada')
        ORDER BY v.criado_em DESC
        LIMIT %(limite)s
        """,
        {
            "lat_min": lat_min,
            "lat_max": lat_max,
            "lon_min": lon_min,
            "lon_max": lon_max,
            "tipo": tipo,
            "id_area": id_area,
            "verif": verificacao,
            "limite": limite,
        },
    ).fetchall()

    return {
        "type": "FeatureCollection",
        "truncado": len(linhas) == limite,
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
                "properties": {
                    "id_ocorrencia": r["id_ocorrencia"],
                    "id_area": r["id_area"],
                    "tipo": r["tipo"],
                    "categoria": r["categoria"],
                    "gravidade": r["gravidade"],
                    "status": r["status"],
                    "canal_registro": r["canal_registro"],
                    "confianca_ia": r["confianca_max"],
                    "verificacao": r["verificacao"],
                    "criado_em": r["criado_em"],
                },
            }
            for r in linhas
        ],
    }


@router.get("/minhas", response_model=PaginaOcorrencias)
def minhas(
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
    u=Depends(usuario_atual),
    conn=Depends(get_conn),
):
    """Ocorrências registradas por quem está logado (mais novas primeiro)."""
    return paginar(
        conn,
        f"""
        SELECT {COLUNAS}, count(*) OVER () AS total FROM ocorrencias
        WHERE id_usuario_criador = %(usuario)s
        ORDER BY criado_em DESC
        LIMIT %(limite)s OFFSET %(desloc)s
        """,
        {"usuario": u["id_usuario"]},
        limite,
        deslocamento,
    )


@router.get("/tipos")
def listar_tipos(conn=Depends(get_conn)):
    """Tipos de ocorrência ativos, com as categorias de cada um (para o app montar o formulário)."""
    return conn.execute(
        """
        SELECT codigo, nome, usa_ia, usa_gravidade, categorias
        FROM tipos_ocorrencia WHERE ativo ORDER BY ordem, nome
        """
    ).fetchall()


@router.get("/{id_ocorrencia}", response_model=OcorrenciaOut)
def obter(
    id_ocorrencia: Annotated[int, Path(ge=1, le=2**63 - 1)],
    u=Depends(usuario_opcional),
    conn=Depends(get_conn),
):
    """Detalhe de uma ocorrência. Verificadas: qualquer pessoa. As demais: dono, gestor da cidade ou admin."""
    exigir_acesso_a_ocorrencia(conn, u, id_ocorrencia)
    o = conn.execute(
        f"SELECT {COLUNAS} FROM ocorrencias WHERE id_ocorrencia = %s",
        (id_ocorrencia,),
    ).fetchone()
    if o is None:
        raise HTTPException(404, "Ocorrência não encontrada")
    return o