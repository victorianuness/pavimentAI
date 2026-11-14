"""Quem pode ver uma ocorrência (e as fotos dela).

Regra única, usada no detalhe da ocorrência e nas fotos:
- ocorrência VERIFICADA (a IA confirmou, o gestor aprovou, ou o tipo não usa IA): qualquer pessoa vê;
- ocorrência ainda NÃO verificada (em triagem, sem foto, recusada): só quem registrou,
  o gestor daquela cidade ou o admin.
Quem não pode ver recebe 404 (e não 403), para não revelar que o número existe.
"""

from fastapi import HTTPException

# Mesma regra do mapa. Espera as tabelas: ocorrencias AS o e tipos_ocorrencia AS t.
SQL_VERIFICADA = """(
    o.triagem_decisao IS DISTINCT FROM 'recusada'
    AND (NOT t.usa_ia OR o.situacao_ia = 'confirmada' OR o.triagem_decisao = 'aprovada')
)"""


def pode_ver(u: dict | None, o: dict) -> bool:
    """`o` precisa ter: verificada, id_usuario_criador, id_area."""
    if o["verificada"]:
        return True
    if u is None:
        return False
    if u["papel"] == "admin":
        return True
    if o["id_usuario_criador"] == u["id_usuario"]:
        return True
    return u["papel"] == "gestor" and o["id_area"] is not None and u["id_area_gestao"] == o["id_area"]


def exigir_acesso_a_ocorrencia(conn, u: dict | None, id_ocorrencia: int) -> None:
    o = conn.execute(
        f"""
        SELECT o.id_usuario_criador, o.id_area, {SQL_VERIFICADA} AS verificada
        FROM ocorrencias o
        JOIN tipos_ocorrencia t ON t.codigo = o.tipo
        WHERE o.id_ocorrencia = %s
        """,
        (id_ocorrencia,),
    ).fetchone()
    if o is None or not pode_ver(u, o):
        raise HTTPException(404, "Ocorrência não encontrada")
