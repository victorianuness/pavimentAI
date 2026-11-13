"""Aplica um ou mais arquivos .sql no banco, usando o usuário dono (postgres).
Serve no lugar do pgAdmin/psql.

Uso (dentro da pasta api, com a venv ativa):
    python scripts/aplicar_sql.py sql/banco.sql sql/migracao_pavimentai_v2.sql ...
"""
import getpass
import os
import re
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


def _chave_natural(caminho: Path) -> list:
    """Garante que v2.sql venha antes de v10.sql caso o terminal expanda *.sql."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", caminho.name)]


def _remover_begin_commit_externos(sql_texto: str) -> str:
    """Remove BEGIN/COMMIT soltos no topo/fim para usar conn.transaction() sem warnings."""
    linhas = sql_texto.splitlines()
    filtradas = [
        l for l in linhas
        if not re.fullmatch(r"\s*(BEGIN|COMMIT)\s*;\s*(--.*)?", l, flags=re.IGNORECASE)
    ]
    return "\n".join(filtradas).strip()


def main() -> int:
    arquivos = [Path(a) for a in sys.argv[1:]]
    if not arquivos:
        print("Uso: python scripts/aplicar_sql.py arquivo1.sql [arquivo2.sql ...]")
        return 1
    faltando = [str(a) for a in arquivos if not a.is_file()]
    if faltando:
        print("Não encontrei estes arquivos (confira se está na pasta api):")
        for f in faltando:
            print("  -", f)
        return 1

    if len(arquivos) > 1 and all("migracao" in a.name.lower() for a in arquivos):
        arquivos = sorted(arquivos, key=_chave_natural)

    _carregar_env()
    conexao = dict(
        host=os.getenv("PGHOST") or os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("PGPORT") or os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("PGDATABASE") or os.getenv("DB_NAME", "pavimentai"),
        user=os.getenv("PGUSER", "postgres"),
    )
    senha = os.getenv("PGPASSWORD") or getpass.getpass(f"Senha do usuário {conexao['user']}: ")

    try:
        with psycopg.connect(**conexao, password=senha, autocommit=True) as conn:
            for arquivo in arquivos:
                print(f"Aplicando {arquivo} ... ", end="", flush=True)
                conteudo = _remover_begin_commit_externos(arquivo.read_text(encoding="utf-8"))
                if not conteudo:
                    print("vazio (ignorado)")
                    continue
                try:
                    with conn.transaction():
                        conn.execute(conteudo)
                except psycopg.Error as erro:
                    print("ERRO (rollback deste arquivo efetuado)")
                    print(f"\n{erro}\n\nParei aqui. Nada deste arquivo nem dos seguintes foi aplicado.")
                    return 1
                print("ok")
    except psycopg.OperationalError as erro:
        print(f"\nNão consegui conectar no banco: {erro}")
        print("Confira se o PostgreSQL está ligado e se a senha do postgres está certa.")
        return 1

    print("\nTudo aplicado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())