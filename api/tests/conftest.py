"""Preparação dos testes de rota (usam um banco de TESTE de verdade, com PostGIS).

Como rodar (uma vez, como superusuário do Postgres):
    CREATE DATABASE pavimentai_teste;      -- depois aplique banco.sql e as migrações nele
Variáveis de ambiente (as mesmas do .env, apontando para o banco de teste):
    DB_NAME=pavimentai_teste  DB_USER=pavimentai_app  DB_PASSWORD=...  JWT_SECRET=<32+ caracteres>
    TEST_ADMIN_DSN="dbname=pavimentai_teste user=postgres ..."   (superusuário, só para montar os dados)

Por segurança, os testes APAGAM os dados do banco: só rodam se o nome terminar em "_teste".
"""
import os
import sys
import types

import pytest

# Nos testes a conferência automática de clusters fica desligada: ela mexeria no banco no meio dos testes.
os.environ.setdefault("ALERTA_CLUSTER_INTERVALO_MIN", "0")

# Se o ultralytics (YOLO) não estiver instalado, usa um substituto: estes testes não rodam a IA.
try:
    import ultralytics  # noqa: F401
except ImportError:  # pragma: no cover
    fake = types.ModuleType("ultralytics")

    class YOLO:  # noqa: D401
        def __init__(self, *a, **k):
            raise RuntimeError("YOLO de mentira nos testes")

    fake.YOLO = YOLO
    sys.modules["ultralytics"] = fake


def _dsn_admin() -> str:
    dsn = os.environ.get("TEST_ADMIN_DSN")
    if not dsn:
        pytest.skip("Defina TEST_ADMIN_DSN (superusuário do banco de teste) para rodar estes testes.")
    return dsn


@pytest.fixture(scope="session")
def admin_conn():
    import psycopg

    nome = os.environ.get("DB_NAME", "")
    if not nome.endswith("_teste"):
        pytest.skip("DB_NAME precisa terminar em _teste (estes testes apagam dados).")
    with psycopg.connect(_dsn_admin(), autocommit=True) as c:
        # Zera o limite de login por IP: rodar os testes várias vezes seguidas estourava o limite (429).
        c.execute("TRUNCATE limites_requisicoes_ip")
        yield c


@pytest.fixture(scope="session")
def client_api():
    """Um único TestClient para a sessão inteira de testes que o usam.

    O pool de conexões da API (app/db.py) é um só e, depois de fechado, não reabre. Por isso cada
    `with TestClient(app)` num arquivo de teste fecha o pool para os arquivos seguintes.
    Quem usa este fixture não depende da ordem; os arquivos antigos continuam com o próprio client.
    """
    from fastapi.testclient import TestClient
    from psycopg_pool import PoolClosed

    from app.main import app

    cm = TestClient(app)
    try:
        client = cm.__enter__()
    except PoolClosed:
        pytest.skip("O pool da API já foi fechado por outro arquivo de teste: rode este arquivo antes ou sozinho.")
    try:
        yield client
    finally:
        cm.__exit__(None, None, None)
