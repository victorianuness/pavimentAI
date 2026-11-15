"""Alertas automáticos de cluster: avisa a secretaria quando surge uma concentração de ocorrências novas.

Como funciona (resumo):
1. A cada ALERTA_CLUSTER_INTERVALO_MIN minutos (ou quando o gestor pede, em
   POST /gestao/alertas/verificar) a API olha cada cidade que tem contato cadastrado.
2. Conta, por célula da grade (mesma ideia do GET /ocorrencias/clusters), as ocorrências
   abertas e VERIFICADAS registradas nas últimas ALERTA_CLUSTER_JANELA_H horas.
3. Célula com ALERTA_CLUSTER_MINIMO ocorrências ou mais é um cluster. Para não encher a
   caixa da secretaria, só avisa quando:
     - é um cluster que nunca foi avisado ("novo");
     - ou ele subiu de nível de concentração desde o último aviso ("escalada");
     - ou passaram ALERTA_CLUSTER_REENVIO_H horas e há pelo menos ALERTA_CLUSTER_MINIMO
       ocorrências registradas depois do último aviso ("crescimento").
4. O alerta é gravado em alertas_cluster e enviado por e-mail a cada contato da cidade.
   Alerta em que TODOS os envios falharam não conta como "já avisado": a próxima conferência tenta de novo.

Observação: o nível (normal/moderada/alta) indica concentração de relatos, não risco real.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from . import auditoria
from .acesso import SQL_VERIFICADA
from .config import settings
from .db import pool
from .email_envio import enviar_email_com_resultado
from .routers.ocorrencias import _nivel_concentracao

log = logging.getLogger("pavimentai.alertas")

# Número fixo que identifica "conferência de clusters" no banco: com mais de um processo da
# API rodando, só um confere por vez (pg_try_advisory_xact_lock) e ninguém avisa em dobro.
CHAVE_LOCK = 7251201

FUSO_BRASILIA = timezone(timedelta(hours=-3))  # o Brasil não tem mais horário de verão
ORDEM_NIVEL = {"normal": 0, "moderada": 1, "alta": 2}
ORDEM_GRAVIDADE = ["grave", "moderado", "leve", "sem_classificacao"]
MOTIVOS = {
    "novo": "Novo agrupamento de ocorrências nesta região.",
    "escalada": "O agrupamento subiu de nível de concentração desde o último aviso.",
    "crescimento": "Surgiram novas ocorrências nesta região desde o último aviso.",
}


# --------------------------------------------------------------------------- regras (sem banco)
def srid_da_area(longitude: float, latitude: float) -> int:
    """Zona UTM (em metros) do centro da cidade, para montar a grade de células."""
    zona = max(1, min(60, int((longitude + 180) // 6) + 1))
    return (32600 if latitude >= 0 else 32700) + zona


def decidir_motivo(
    nivel: str,
    criados_em: list[datetime],
    ultimo: dict | None,
    agora: datetime,
    *,
    minimo: int,
    reenvio_h: int,
) -> str | None:
    """Diz se esta célula merece um novo aviso. Devolve o motivo ou None (não avisar)."""
    if ultimo is None:
        return "novo"
    if ORDEM_NIVEL[nivel] > ORDEM_NIVEL[ultimo["nivel"]]:
        return "escalada"
    novas = sum(1 for c in criados_em if c > ultimo["criado_em"])
    if agora - ultimo["criado_em"] >= timedelta(hours=reenvio_h) and novas >= minimo:
        return "crescimento"
    return None


def _limpar(texto: str) -> str:
    return " ".join(str(texto).split())  # tira quebras de linha (nada de cabeçalho quebrado no e-mail)


def _lista(contagens: dict[str, int], ordem: list[str] | None = None) -> str:
    chaves = sorted(contagens, key=lambda k: (ordem.index(k) if ordem and k in ordem else 99, k))
    return "; ".join(f"{k}: {contagens[k]}" for k in chaves) or "—"


def montar_mensagem(nome_area: str, c: dict) -> tuple[str, str]:
    """Monta (assunto, texto) do e-mail. `c` traz os dados do cluster (veja _celulas_quentes)."""
    nome_area = _limpar(nome_area)
    ultima = c["ultima_ocorrencia_em"].astimezone(FUSO_BRASILIA).strftime("%d/%m/%Y %H:%M")
    mapa = f"https://www.google.com/maps?q={c['latitude']:.6f},{c['longitude']:.6f}"
    assunto = (
        f"PavimentAI: {c['total']} ocorrências concentradas em {nome_area} "
        f"(concentração {c['nivel']})"
    )
    texto = (
        f"Olá!\n\n"
        f"O PavimentAI identificou uma concentração de ocorrências novas em {nome_area}.\n\n"
        f"{MOTIVOS[c['motivo']]}\n\n"
        f"Resumo\n"
        f"- Ocorrências abertas e verificadas nas últimas {c['janela_h']} horas nesta região: {c['total']}\n"
        f"- Nível de concentração: {c['nivel']}\n"
        f"- Tipos: {_lista(c['por_tipo'])}\n"
        f"- Gravidade: {_lista(c['por_gravidade'], ORDEM_GRAVIDADE)}\n"
        f"- Ocorrência mais recente: {ultima} (horário de Brasília)\n"
        f"- Região: quadrado de {c['celula_m']} m ao redor deste ponto: {mapa}\n\n"
        f"O nível mostra concentração de relatos na região, não o risco real do local. "
        f"Vale conferir as ocorrências no painel de gestão do PavimentAI.\n\n"
        f"Este é um aviso automático. Para parar de receber, peça ao gestor da sua cidade "
        f"que remova este e-mail dos contatos de alerta.\n"
    )
    return assunto, texto


# --------------------------------------------------------------------------- banco
def _areas(conn, id_area: int | None) -> list[dict]:
    return conn.execute(
        """
        SELECT a.id_area, a.nome,
               ST_X(ST_Centroid(a.geometria::geometry)) AS longitude,
               ST_Y(ST_Centroid(a.geometria::geometry)) AS latitude
        FROM areas_atendimento a
        WHERE a.ativa AND (%(id)s::int IS NULL OR a.id_area = %(id)s::int)
        ORDER BY a.id_area
        """,
        {"id": id_area},
    ).fetchall()


def _celulas_quentes(conn, id_area: int, srid: int, celula_m: int, janela_h: int, minimo: int) -> list[dict]:
    """Células com ocorrências novas suficientes. Mesmas regras de 'verificada' do mapa público."""
    return conn.execute(
        f"""
        WITH base AS (
            SELECT o.id_ocorrencia, t.nome AS tipo_nome, o.criado_em,
                   COALESCE(o.gravidade_verificada, o.gravidade_cidadao, ia.gravidade_ia,
                            'sem_classificacao') AS gravidade,
                   ST_Transform(o.localizacao::geometry, %(srid)s) AS ponto_metrico
            FROM ocorrencias o
            JOIN tipos_ocorrencia t ON t.codigo = o.tipo
            LEFT JOIN LATERAL (
                SELECT (ARRAY_AGG(d.gravidade_estimada ORDER BY
                           CASE d.gravidade_estimada
                               WHEN 'grave' THEN 3 WHEN 'moderado' THEN 2
                               WHEN 'leve' THEN 1 ELSE 0
                           END DESC))[1] AS gravidade_ia
                FROM deteccoes_ia d WHERE d.id_ocorrencia = o.id_ocorrencia
            ) ia ON true
            WHERE o.id_area = %(id_area)s
              AND o.status = 'aberta'
              AND o.criado_em >= now() - make_interval(hours => %(janela)s)
              AND {SQL_VERIFICADA}
        ),
        marcadas AS (
            SELECT floor(ST_X(ponto_metrico) / %(celula)s)::bigint AS coluna,
                   floor(ST_Y(ponto_metrico) / %(celula)s)::bigint AS linha,
                   id_ocorrencia, tipo_nome, gravidade, criado_em
            FROM base
        ),
        agregadas AS (
            SELECT coluna, linha, count(*)::int AS total,
                   array_agg(criado_em ORDER BY criado_em) AS criados_em,
                   (array_agg(id_ocorrencia ORDER BY criado_em DESC))[1:20] AS ids_ocorrencias,
                   max(criado_em) AS ultima_ocorrencia_em
            FROM marcadas
            GROUP BY coluna, linha
            HAVING count(*) >= %(minimo)s
        ),
        por_tipo AS (
            SELECT coluna, linha, jsonb_object_agg(tipo_nome, n) AS valor
            FROM (SELECT coluna, linha, tipo_nome, count(*)::int AS n
                  FROM marcadas GROUP BY coluna, linha, tipo_nome) x
            GROUP BY coluna, linha
        ),
        por_gravidade AS (
            SELECT coluna, linha, jsonb_object_agg(gravidade, n) AS valor
            FROM (SELECT coluna, linha, gravidade, count(*)::int AS n
                  FROM marcadas GROUP BY coluna, linha, gravidade) x
            GROUP BY coluna, linha
        )
        SELECT a.coluna, a.linha, a.total, a.criados_em, a.ids_ocorrencias, a.ultima_ocorrencia_em,
               pt.valor AS por_tipo, pg.valor AS por_gravidade,
               ST_X(ST_Transform(ST_SetSRID(ST_MakePoint(
                   (a.coluna + 0.5) * %(celula)s, (a.linha + 0.5) * %(celula)s), %(srid)s), 4326)) AS longitude,
               ST_Y(ST_Transform(ST_SetSRID(ST_MakePoint(
                   (a.coluna + 0.5) * %(celula)s, (a.linha + 0.5) * %(celula)s), %(srid)s), 4326)) AS latitude
        FROM agregadas a
        JOIN por_tipo pt USING (coluna, linha)
        JOIN por_gravidade pg USING (coluna, linha)
        ORDER BY a.total DESC, a.coluna, a.linha
        """,
        {
            "id_area": id_area,
            "srid": srid,
            "celula": celula_m,
            "janela": janela_h,
            "minimo": minimo,
        },
    ).fetchall()


def _ultimo_alerta(conn, id_area: int, referencia: str) -> dict | None:
    """Último aviso que 'valeu' para esta célula (ignora os que falharam em todos os envios)."""
    return conn.execute(
        """
        SELECT nivel, criado_em FROM alertas_cluster
        WHERE id_area = %s AND referencia_espacial = %s
          AND (status IN ('enviado', 'parcial', 'simulado')
               OR (status = 'pendente' AND criado_em > now() - interval '30 minutes'))
        ORDER BY criado_em DESC
        LIMIT 1
        """,
        (id_area, referencia),
    ).fetchone()


def _enviar(contatos: list[dict], assunto: str, texto: str) -> tuple[str, int]:
    """Envia a todos os contatos. Devolve (status do alerta, quantos deram certo)."""
    ok = simulados = 0
    for contato in contatos:
        if contato["canal"] != "email":
            log.warning("Canal %s ainda não é suportado nos alertas.", contato["canal"])
            continue
        resultado = enviar_email_com_resultado(contato["destino"], assunto, texto)
        if resultado == "simulado":
            simulados += 1
            if settings.ambiente == "dev":
                print(f"\n[DEV] Alerta de cluster para {contato['destino']}:\n{assunto}\n\n{texto}", flush=True)
        elif resultado == "enviado":
            ok += 1
    sucessos = ok + simulados
    if sucessos == 0:
        return "falhou", 0
    if sucessos < len(contatos):
        return "parcial", sucessos
    return ("simulado" if simulados else "enviado"), sucessos


# --------------------------------------------------------------------------- orquestração
def executar(id_area: int | None = None, simular: bool = False) -> dict:
    """Confere os clusters, grava os alertas novos e envia os e-mails.

    id_area=None confere todas as cidades ativas. simular=True só mostra o que seria avisado:
    não grava nada e não envia nada.
    """
    celula = settings.alerta_cluster_celula_m
    minimo = settings.alerta_cluster_minimo
    janela = settings.alerta_cluster_janela_h
    agora = datetime.now(timezone.utc)

    resultado = {
        "executado": True,
        "simulado": simular,
        "motivo": None,
        "areas_verificadas": 0,
        "areas_sem_contato": [],
        "alertas": [],
    }
    para_enviar = []  # (item, contatos, assunto, texto)

    # Parte 1 (uma transação): descobre os clusters e GRAVA os alertas. O lock vale até o commit.
    with pool.connection(timeout=10.0) as conn:
        if not simular:
            livre = conn.execute(
                "SELECT pg_try_advisory_xact_lock(%s) AS livre", (CHAVE_LOCK,)
            ).fetchone()["livre"]
            if not livre:
                resultado.update(executado=False, motivo="Já existe uma conferência em andamento.")
                return resultado

        for area in _areas(conn, id_area):
            contatos = conn.execute(
                "SELECT id_contato, canal, destino FROM contatos_alerta WHERE id_area = %s ORDER BY id_contato",
                (area["id_area"],),
            ).fetchall()
            if not contatos:
                resultado["areas_sem_contato"].append(area["id_area"])
                continue
            resultado["areas_verificadas"] += 1

            srid = srid_da_area(area["longitude"], area["latitude"])
            for c in _celulas_quentes(conn, area["id_area"], srid, celula, janela, minimo):
                referencia = f"epsg:{srid}:{celula}:{c['coluna']}:{c['linha']}"
                nivel = _nivel_concentracao(c["total"])
                ultimo = _ultimo_alerta(conn, area["id_area"], referencia)
                motivo = decidir_motivo(
                    nivel, c["criados_em"], ultimo, agora,
                    minimo=minimo, reenvio_h=settings.alerta_cluster_reenvio_h,
                )
                if motivo is None:
                    continue

                dados = {
                    **c, "nivel": nivel, "motivo": motivo, "janela_h": janela, "celula_m": celula,
                }
                item = {
                    "id_alerta": None,
                    "id_area": area["id_area"],
                    "area": area["nome"],
                    "referencia_espacial": referencia,
                    "latitude": c["latitude"],
                    "longitude": c["longitude"],
                    "total_ocorrencias": c["total"],
                    "nivel": nivel,
                    "motivo": motivo,
                    "destinatarios_total": len(contatos),
                    "status": "nao_enviado",
                }
                if not simular:
                    item["id_alerta"] = conn.execute(
                        """
                        INSERT INTO alertas_cluster
                            (id_area, referencia_espacial, tamanho_celula_m, latitude, longitude,
                             total_ocorrencias, nivel, janela_horas, motivo, resumo, destinatarios_total)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id_alerta
                        """,
                        (
                            area["id_area"], referencia, celula, c["latitude"], c["longitude"],
                            c["total"], nivel, janela, motivo,
                            Jsonb({
                                "por_tipo": c["por_tipo"],
                                "por_gravidade": c["por_gravidade"],
                                "ids_ocorrencias": c["ids_ocorrencias"],
                                "ultima_ocorrencia_em": c["ultima_ocorrencia_em"].isoformat(),
                            }),
                            len(contatos),
                        ),
                    ).fetchone()["id_alerta"]
                    item["status"] = "pendente"
                    assunto, texto = montar_mensagem(area["nome"], dados)
                    para_enviar.append((item, contatos, assunto, texto))
                resultado["alertas"].append(item)

    # Parte 2: envia fora da transação (SMTP pode demorar) e depois anota o resultado.
    if para_enviar:
        resultados = []
        for item, contatos, assunto, texto in para_enviar:
            status, sucessos = _enviar(contatos, assunto, texto)
            item["status"] = status
            resultados.append((item, status, sucessos))
        with pool.connection(timeout=10.0) as conn:
            for item, status, sucessos in resultados:
                conn.execute(
                    """
                    UPDATE alertas_cluster
                    SET status = %s, destinatarios_enviados = %s, enviado_em = now()
                    WHERE id_alerta = %s
                    """,
                    (status, sucessos, item["id_alerta"]),
                )
                auditoria.registrar(
                    conn, "alerta_cluster_gerado", None, "alertas_cluster", item["id_alerta"],
                    {
                        "id_area": item["id_area"], "status": status, "motivo": item["motivo"],
                        "total_ocorrencias": item["total_ocorrencias"], "nivel": item["nivel"],
                        "destinatarios": f"{sucessos}/{item['destinatarios_total']}",
                    },
                )
        log.info("Alertas de cluster: %d gerado(s).", len(resultados))
    return resultado


async def laco_de_verificacao() -> None:
    """Tarefa de fundo: confere os clusters de tempos em tempos enquanto a API está de pé."""
    await asyncio.sleep(30)  # deixa a API terminar de subir antes da primeira conferência
    while True:
        try:
            await asyncio.to_thread(executar)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Falha na conferência automática de clusters")
        await asyncio.sleep(settings.alerta_cluster_intervalo_min * 60)
