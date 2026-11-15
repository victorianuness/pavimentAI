"""Alertas de cluster para a secretaria: contatos que recebem o aviso, histórico e conferência na hora.

Quem usa: gestor (só a própria cidade) e admin (qualquer cidade). Veja notificacoes.py para as regras.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from .. import auditoria, notificacoes
from ..config import settings
from ..db import get_conn
from ..deps import exigir_papel
from ..paginacao import paginar
from ..schemas import (
    ContatoAlertaIn,
    ContatoAlertaOut,
    PaginaAlertas,
    VerificacaoOut,
)
from .gestao import _escopo

log = logging.getLogger("pavimentai.alertas")

router = APIRouter(prefix="/gestao/alertas", tags=["Alertas de cluster"])

Gestao = exigir_papel("gestor", "admin")
IdBigint = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.get("/contatos", response_model=list[ContatoAlertaOut])
def listar_contatos(
    id_area: Annotated[int | None, Query(ge=1, description="Só para admin")] = None,
    u=Depends(Gestao),
    conn=Depends(get_conn),
):
    """Contatos que recebem os alertas de cluster. O gestor vê só os da própria cidade."""
    area = _escopo(u, id_area)
    return conn.execute(
        """
        SELECT id_contato, id_area, canal, destino, rotulo, criado_em
        FROM contatos_alerta
        WHERE (%(a)s::int IS NULL OR id_area = %(a)s::int)
        ORDER BY id_area, id_contato
        """,
        {"a": area},
    ).fetchall()


@router.post("/contatos", response_model=ContatoAlertaOut, status_code=201)
def cadastrar_contato(dados: ContatoAlertaIn, u=Depends(Gestao), conn=Depends(get_conn)):
    """Cadastra um e-mail da secretaria para receber os alertas da cidade."""
    area = _escopo(u, dados.id_area)
    if area is None:
        raise HTTPException(422, "Informe id_area: o admin escolhe para qual cidade é o contato.")

    existe = conn.execute(
        "SELECT 1 FROM areas_atendimento WHERE id_area = %s AND ativa", (area,)
    ).fetchone()
    if existe is None:
        raise HTTPException(404, "Cidade não encontrada ou desativada.")

    total = conn.execute(
        "SELECT count(*) AS n FROM contatos_alerta WHERE id_area = %s", (area,)
    ).fetchone()["n"]
    if total >= settings.max_contatos_alerta_por_area:
        raise HTTPException(
            422,
            f"Esta cidade já tem {total} contatos de alerta (o máximo é "
            f"{settings.max_contatos_alerta_por_area}). Remova algum antes de cadastrar outro.",
        )

    contato = conn.execute(
        """
        INSERT INTO contatos_alerta (id_area, canal, destino, rotulo, id_usuario_criador)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id_area, canal, destino) DO NOTHING
        RETURNING id_contato, id_area, canal, destino, rotulo, criado_em
        """,
        (area, dados.canal, dados.destino, dados.rotulo, u["id_usuario"]),
    ).fetchone()
    if contato is None:
        raise HTTPException(409, "Este contato já está cadastrado para a cidade.")

    # Na auditoria vai só o id: o e-mail em si é dado pessoal.
    auditoria.registrar(
        conn, "contato_alerta_criado", u["id_usuario"], "contatos_alerta", contato["id_contato"],
        {"id_area": area, "canal": dados.canal},
    )
    return contato


@router.delete("/contatos/{id_contato}", status_code=204)
def remover_contato(id_contato: IdBigint, u=Depends(Gestao), conn=Depends(get_conn)):
    """Remove um contato. Contato de outra cidade responde 404 (não revela que existe)."""
    contato = conn.execute(
        "SELECT id_area FROM contatos_alerta WHERE id_contato = %s", (id_contato,)
    ).fetchone()
    if contato is None or (
        u["papel"] == "gestor" and contato["id_area"] != u["id_area_gestao"]
    ):
        raise HTTPException(404, "Contato não encontrado.")

    conn.execute("DELETE FROM contatos_alerta WHERE id_contato = %s", (id_contato,))
    auditoria.registrar(
        conn, "contato_alerta_removido", u["id_usuario"], "contatos_alerta", id_contato,
        {"id_area": contato["id_area"]},
    )
    return Response(status_code=204)


@router.get("", response_model=PaginaAlertas)
def historico(
    id_area: Annotated[int | None, Query(ge=1, description="Só para admin")] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
    u=Depends(Gestao),
    conn=Depends(get_conn),
):
    """Alertas de cluster já gerados, do mais recente para o mais antigo."""
    area = _escopo(u, id_area)
    return paginar(
        conn,
        """
        SELECT id_alerta, id_area, referencia_espacial, latitude, longitude, total_ocorrencias,
               nivel, motivo, status, destinatarios_total, destinatarios_enviados, resumo,
               criado_em, enviado_em, count(*) OVER () AS total
        FROM alertas_cluster
        WHERE (%(a)s::int IS NULL OR id_area = %(a)s::int)
        ORDER BY criado_em DESC, id_alerta DESC
        LIMIT %(limite)s OFFSET %(desloc)s
        """,
        {"a": area},
        limite,
        deslocamento,
    )


@router.post("/verificar", response_model=VerificacaoOut)
def verificar_agora(
    simular: Annotated[
        bool, Query(description="true = só mostra o que seria avisado, sem gravar nem enviar nada")
    ] = False,
    id_area: Annotated[int | None, Query(ge=1, description="Só para admin; vazio = todas as cidades")] = None,
    u=Depends(Gestao),
):
    """Confere os clusters agora (sem esperar a conferência automática) e avisa a secretaria.

    Não repete aviso do mesmo cluster sem motivo: veja as regras em notificacoes.py.
    """
    area = _escopo(u, id_area)
    resultado = notificacoes.executar(id_area=area, simular=simular)
    # Rota síncrona: o FastAPI a roda numa thread, então o envio de e-mail não trava a API.
    log.info("Conferência manual de clusters por usuário %s (simular=%s)", u["id_usuario"], simular)
    return resultado
