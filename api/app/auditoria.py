from typing import Any
from psycopg.types.json import Jsonb


def registrar(
    conn,
    acao: str,
    id_usuario: int | None = None,
    entidade: str | None = None,
    id_registro: int | None = None,
    detalhes: dict[str, Any] | None = None,
) -> None:
    """Grava uma linha na tabela auditoria (a API só pode inserir, nunca alterar)."""
    conn.execute(
        """
        INSERT INTO auditoria (id_usuario, acao, entidade_afetada, id_registro_afetado, detalhes)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            id_usuario,
            acao,
            entidade,
            id_registro,
            Jsonb(detalhes) if detalhes is not None else None,
        ),
    )