"""Cria o usuário do banco "pavimentai_admin", usado SÓ pelo painel de admin da API.

Por que um usuário separado? O usuário comum da API (pavimentai_app) atende o público
e NÃO pode cadastrar cidades nem mudar papéis. Assim, se algum dia houver uma falha
numa rota pública, ninguém consegue se promover a admin.

Uso (dentro da pasta api, com a venv ativa):
    python scripts/criar_papel_admin_db.py
"""
import getpass
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

PAPEL = "pavimentai_admin"


def _carregar_env() -> None:
    """Lê variáveis básicas do api/.env caso não estejam exportadas no terminal."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for linha in env_path.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip().strip("'\""))


def _obter_conexao() -> dict:
    _carregar_env()
    return dict(
        host=os.getenv("PGHOST") or os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("PGPORT") or os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("PGDATABASE") or os.getenv("DB_NAME", "pavimentai"),
        user=os.getenv("PGUSER", "postgres"),
    )


def main() -> int:
    conexao = _obter_conexao()
    senha_pg = os.getenv("PGPASSWORD") or getpass.getpass(f"Senha do usuário {conexao['user']}: ")
    nova = os.getenv("ADMIN_DB_PASSWORD")
    if not nova:
        nova = getpass.getpass(f"Escolha uma senha NOVA para o usuário {PAPEL} (mínimo 10 caracteres): ")
        if nova != getpass.getpass("Repita a senha: "):
            print("As senhas não são iguais. Nada foi alterado.")
            return 1
    if len(nova) < 10:
        print("A senha precisa ter pelo menos 10 caracteres. Nada foi alterado.")
        return 1

    try:
        with psycopg.connect(**conexao, password=senha_pg, autocommit=True) as conn:
            existe = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (PAPEL,)).fetchone()
            papel = sql.Identifier(PAPEL)
            acao = (
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}")
                if existe
                else sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}")
            )
            conn.execute(acao.format(papel, sql.Literal(nova)))

            def seq(tabela: str, coluna: str) -> str | None:
                r = conn.execute(
                    "SELECT to_regclass(%s) IS NOT NULL", (f"public.{tabela}",)
                ).fetchone()
                if not r or not r[0]:
                    return None
                s_row = conn.execute(
                    "SELECT pg_get_serial_sequence(%s, %s)", (f"public.{tabela}", coluna)
                ).fetchone()
                return s_row[0] if s_row else None

            comandos = [
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(conexao["dbname"]), papel
                ),
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(papel),
                sql.SQL(
                    "GRANT SELECT ON public.areas_atendimento, public.usuarios, public.ocorrencias TO {}"
                ).format(papel),
                sql.SQL("GRANT INSERT ON public.areas_atendimento TO {}").format(papel),
                sql.SQL(
                    "GRANT UPDATE (nome, ativa, exige_residencia) ON public.areas_atendimento TO {}"
                ).format(papel),
                sql.SQL(
                    "GRANT UPDATE (papel, id_area_gestao, id_area_residencia) ON public.usuarios TO {}"
                ).format(papel),
                sql.SQL("GRANT UPDATE (id_area) ON public.ocorrencias TO {}").format(papel),
                sql.SQL("GRANT INSERT ON public.auditoria TO {}").format(papel),
            ]

            # Se a tabela tipos_ocorrencia (v8) já existir, concede as permissões necessárias para /admin/tipos
            tem_tipos = conn.execute(
                "SELECT to_regclass('public.tipos_ocorrencia') IS NOT NULL"
            ).fetchone()[0]
            if tem_tipos:
                comandos.extend([
                    sql.SQL("GRANT SELECT, INSERT ON public.tipos_ocorrencia TO {}").format(papel),
                    sql.SQL(
                        "GRANT UPDATE (nome, ativo, ordem, categorias) ON public.tipos_ocorrencia TO {}"
                    ).format(papel),
                ])

            sequencias = (
                ("areas_atendimento", "id_area"),
                ("tipos_ocorrencia", "id_tipo"),
                ("auditoria", "id_auditoria"),
            )
            for tabela, coluna in sequencias:
                s = seq(tabela, coluna)
                if s:
                    comandos.append(sql.SQL("GRANT USAGE ON SEQUENCE {} TO {}").format(sql.SQL(s), papel))

            for c in comandos:
                conn.execute(c)
    except psycopg.Error as erro:
        print(f"Não consegui configurar o banco: {erro}")
        return 1

    print(f"Pronto! O usuário {PAPEL} foi {'atualizado' if existe else 'criado'}.\n")
    print("Agora abra o arquivo .env (na pasta api) e acrescente estas 2 linhas:")
    print(f"DB_ADMIN_USER={PAPEL}")
    print("DB_ADMIN_PASSWORD=<a senha que você acabou de escolher>")
    print("\nDepois reinicie a API.")
    return 0


if __name__ == "__main__":
    sys.exit(main())