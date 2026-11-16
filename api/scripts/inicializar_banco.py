"""Monta o banco do zero, sem nenhum passo manual. É o que o Docker roda ao subir.

O que faz, nesta ordem:
  1. espera o PostgreSQL aceitar conexão;
  2. aplica sql/banco.sql e todas as migrações (v2, v3 ... v12) em ordem numérica;
  3. ajusta a senha do usuário pavimentai_app para a do DB_PASSWORD do .env;
  4. se DB_ADMIN_PASSWORD existir, cria/atualiza o usuário pavimentai_admin;
  5. insere a cidade de exemplo (Ribeirão Pires), a não ser que SEMEAR_CIDADE=0.

Pode rodar quantas vezes quiser: os .sql do projeto são idempotentes.

Variáveis lidas (as mesmas do .env da API, mais a senha do superusuário):
    DB_HOST, DB_PORT, DB_NAME, DB_PASSWORD, DB_ADMIN_PASSWORD
    PGUSER (padrão: postgres) e PGPASSWORD (senha do superusuário)

Uso fora do Docker (dentro da pasta api):
    PGPASSWORD=<senha do postgres> python scripts/inicializar_banco.py
"""
import contextlib
import io
import os
import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql

RAIZ_API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aplicar_sql import _carregar_env, _chave_natural, _remover_begin_commit_externos  # noqa: E402

ESPERA_MAX_S = 60


def _conexao() -> dict:
    return dict(
        host=os.getenv("PGHOST") or os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("PGPORT") or os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("PGDATABASE") or os.getenv("DB_NAME", "pavimentai"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD"),
    )


def _esperar_banco(conexao: dict) -> None:
    limite = time.monotonic() + ESPERA_MAX_S
    while True:
        try:
            with psycopg.connect(**conexao, connect_timeout=3):
                return
        except psycopg.OperationalError as erro:
            if time.monotonic() > limite:
                raise SystemExit(f"O banco não respondeu em {ESPERA_MAX_S}s: {erro}")
            print("Esperando o banco ficar pronto...", flush=True)
            time.sleep(2)


def _arquivos_sql(incluir_cidade: bool) -> list[Path]:
    pasta = RAIZ_API / "sql"
    migracoes = sorted(pasta.glob("migracao_pavimentai_v*.sql"), key=_chave_natural)
    arquivos = [pasta / "banco.sql", *migracoes]
    if incluir_cidade:
        arquivos.append(pasta / "limite_ribeirao_pires.sql")
    faltando = [a for a in arquivos if not a.is_file()]
    if faltando:
        raise SystemExit(f"Arquivos .sql não encontrados: {', '.join(map(str, faltando))}")
    return arquivos


def _aplicar(conn, arquivos: list[Path]) -> None:
    for arquivo in arquivos:
        print(f"Aplicando {arquivo.name} ... ", end="", flush=True)
        conteudo = _remover_begin_commit_externos(arquivo.read_text(encoding="utf-8"))
        try:
            with conn.transaction():
                conn.execute(conteudo)
        except psycopg.Error as erro:
            print("ERRO")
            raise SystemExit(f"\n{arquivo.name} falhou e foi desfeito:\n{erro}")
        print("ok")


def _definir_senha_app(conn) -> None:
    senha = os.getenv("DB_PASSWORD")
    if not senha:
        print("DB_PASSWORD vazio: o usuário pavimentai_app ficou com a senha provisória do banco.sql.")
        return
    conn.execute(sql.SQL("ALTER ROLE pavimentai_app LOGIN PASSWORD {}").format(sql.Literal(senha)))
    print("Senha do pavimentai_app ajustada para o DB_PASSWORD.")


def _criar_admin() -> None:
    senha = os.getenv("DB_ADMIN_PASSWORD", "")
    if not senha or senha.startswith("troque_por"):
        print("DB_ADMIN_PASSWORD não definido: rotas /admin ficam sem o usuário pavimentai_admin.")
        return
    # Reaproveita o script que já existe, passando a senha por variável de ambiente.
    os.environ["ADMIN_DB_PASSWORD"] = senha
    import criar_papel_admin_db

    saida = io.StringIO()  # o script imprime instruções de .env que aqui não servem
    with contextlib.redirect_stdout(saida):
        codigo = criar_papel_admin_db.main()
    if codigo != 0:
        raise SystemExit(f"Não consegui criar o pavimentai_admin:\n{saida.getvalue()}")
    print("Usuário pavimentai_admin criado/atualizado com a senha do DB_ADMIN_PASSWORD.")


def main() -> int:
    _carregar_env()
    conexao = _conexao()
    if not conexao["password"]:
        print("Defina PGPASSWORD com a senha do superusuário do PostgreSQL.")
        return 1

    # O script do admin lê a conexão destas variáveis.
    os.environ["PGPASSWORD"] = conexao["password"]
    _esperar_banco(conexao)
    incluir_cidade = os.getenv("SEMEAR_CIDADE", "1") != "0"

    with psycopg.connect(**conexao, autocommit=True) as conn:
        _aplicar(conn, _arquivos_sql(incluir_cidade))
        _definir_senha_app(conn)
    _criar_admin()
    print("\nBanco pronto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
