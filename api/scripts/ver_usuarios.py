"""Lista os usuários do banco com o papel e a cidade de cada um (sem mostrar senha).
Serve para conferir quem é cidadão, gestor ou admin.

Uso (dentro da pasta api, com a venv ativa):
    python scripts/ver_usuarios.py
"""
import getpass
import os
import sys
from pathlib import Path

import psycopg


def _carregar_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for linha in env_path.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip().strip("'\""))


def main() -> int:
    _carregar_env()
    conexao = dict(
        host=os.getenv("PGHOST") or os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("PGPORT") or os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("PGDATABASE") or os.getenv("DB_NAME", "pavimentai"),
        user=os.getenv("PGUSER", "postgres"),
    )
    senha = os.getenv("PGPASSWORD") or getpass.getpass(f"Senha do usuário {conexao['user']}: ")
    try:
        with psycopg.connect(**conexao, password=senha) as conn:
            linhas = conn.execute(
                """
                SELECT u.id_usuario, u.email, u.papel, u.status_conta,
                       coalesce(g.nome, '-') AS gestao, coalesce(r.nome, '-') AS reside_em
                FROM usuarios u
                LEFT JOIN areas_atendimento g ON g.id_area = u.id_area_gestao
                LEFT JOIN areas_atendimento r ON r.id_area = u.id_area_residencia
                ORDER BY u.id_usuario
                """
            ).fetchall()
    except psycopg.Error as erro:
        print(f"Não consegui ler o banco: {erro}")
        return 1

    if not linhas:
        print("Nenhum usuário cadastrado no banco ainda.")
        return 0

    cabecalho = ("id", "e-mail", "papel", "conta", "gestão da cidade", "reside em")
    tabela = [cabecalho] + [tuple(str(c) for c in l) for l in linhas]
    larguras = [max(len(l[i]) for l in tabela) for i in range(len(cabecalho))]
    for n, l in enumerate(tabela):
        print("  ".join(c.ljust(larguras[i]) for i, c in enumerate(l)))
        if n == 0:
            print("  ".join("-" * w for w in larguras))
    return 0


if __name__ == "__main__":
    sys.exit(main())