"""Define o papel de um usuário: cidadao, gestor ou admin. Usa o usuário dono (postgres).

Uso (dentro da pasta api, com a venv ativa):
    python scripts/definir_papel.py carla@email.com gestor 3543303
    python scripts/definir_papel.py joao@email.com admin
    python scripts/definir_papel.py joao@email.com admin --forcar
    python scripts/definir_papel.py carla@email.com cidadao

O gestor precisa do código IBGE do município que ele vai administrar
(o município precisa estar cadastrado em areas_atendimento).
"""
import getpass
import os
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb


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
    args = [a for a in sys.argv[1:] if a != "--forcar"]
    forcar = "--forcar" in sys.argv[1:]

    if len(args) not in (2, 3) or args[1] not in ("cidadao", "gestor", "admin"):
        print(__doc__)
        return 1

    email, papel = args[0].strip().lower(), args[1]
    codigo = args[2].strip() if len(args) == 3 else None

    if papel == "gestor" and not codigo:
        print("Para gestor, informe também o código IBGE do município (ex.: 3543303).")
        return 1
    if papel != "gestor" and codigo:
        print("O código do município só se usa para gestor.")
        return 1

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
            usuario = conn.execute(
                "SELECT id_usuario, papel, status_conta FROM usuarios WHERE lower(email) = %s FOR UPDATE",
                (email,),
            ).fetchone()
            if usuario is None:
                print(f"Não achei nenhum usuário com o e-mail {email}.")
                return 1

            id_usuario, papel_anterior, status_conta = usuario
            if status_conta != "ativa" and not forcar:
                print(
                    f"A conta de {email} está com status '{status_conta}' (precisa estar 'ativa').\n"
                    "Confirme o e-mail primeiro ou adicione --forcar para ativar e promover agora."
                )
                return 1

            id_area = None
            if papel == "gestor":
                area = conn.execute(
                    "SELECT id_area, nome FROM areas_atendimento WHERE codigo_ibge = %s AND ativa",
                    (codigo,),
                ).fetchone()
                if area is None:
                    print(f"O município {codigo} não está cadastrado (ou está desativado) em areas_atendimento.")
                    return 1
                id_area = area[0]

            if forcar and status_conta != "ativa":
                conn.execute(
                    "UPDATE usuarios SET status_conta = 'ativa', email_verificado = true, "
                    "email_verificado_em = coalesce(email_verificado_em, now()) WHERE id_usuario = %s",
                    (id_usuario,),
                )

            conn.execute(
                "UPDATE usuarios SET papel = %s, id_area_gestao = %s WHERE id_usuario = %s",
                (papel, id_area, id_usuario),
            )
            conn.execute(
                """
                INSERT INTO auditoria (id_usuario, acao, entidade_afetada, id_registro_afetado, detalhes)
                VALUES (NULL, 'papel_alterado', 'usuarios', %s, %s)
                """,
                (
                    id_usuario,
                    Jsonb({
                        "origem": "script_definir_papel",
                        "de": papel_anterior,
                        "para": papel,
                        "id_area_gestao": id_area,
                        "codigo_ibge": codigo,
                    }),
                ),
            )
            print(f"Pronto: {email} agora é {papel}" + (f" do município {codigo}." if codigo else "."))
    except psycopg.Error as erro:
        print(f"Não consegui alterar: {erro}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())