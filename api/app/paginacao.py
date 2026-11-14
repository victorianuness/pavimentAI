"""Paginação padrão da API.

Toda lista paginada devolve o mesmo envelope:
    {"total": 120, "limite": 50, "deslocamento": 0, "itens": [...]}

Como usar numa rota: escreva a consulta com `count(*) OVER () AS total` no SELECT e
`LIMIT %(limite)s OFFSET %(desloc)s` no final, e chame `paginar(...)`.
"""


def paginar(conn, sql: str, params: dict, limite: int, deslocamento: int) -> dict:
    parametros = {**params, "limite": limite, "desloc": deslocamento}
    linhas = conn.execute(sql, parametros).fetchall()

    if linhas:
        total = linhas[0]["total"]
    elif deslocamento > 0:
        # Página além do fim: a consulta não devolveu linhas, então não há de onde ler o total.
        # Repete a consulta pedindo só a primeira linha para descobrir quantos itens existem.
        primeira = conn.execute(sql, {**parametros, "limite": 1, "desloc": 0}).fetchall()
        total = primeira[0]["total"] if primeira else 0
    else:
        total = 0

    return {
        "total": total,
        "limite": limite,
        "deslocamento": deslocamento,
        "itens": [{k: v for k, v in linha.items() if k != "total"} for linha in linhas],
    }
