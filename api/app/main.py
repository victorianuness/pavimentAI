import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import get_conn, pool, pool_admin
from .erros import registrar_handlers
from .routers import admin, areas, auth, cep, fotos, gestao, ocorrencias, sinalizacoes
from .servico_yolo import carregar_modelo

log = logging.getLogger("pavimentai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True, timeout=10)  # falha logo se não conseguir conectar no banco
    if pool_admin is not None:
        pool_admin.open(wait=False)  # se a senha estiver errada, só as rotas /admin reclamam
    # Garante que a pasta de uploads exista
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    # Tenta pré-carregar o modelo YOLO no startup para evitar latência no primeiro upload
    try:
        carregar_modelo()
    except Exception as exc:
        log.warning("Modelo YOLO não pôde ser pré-carregado no startup: %s", exc)
    yield
    pool.close()
    if pool_admin is not None:
        pool_admin.close()


app = FastAPI(title="PavimentAI API", version="1.0.0", lifespan=lifespan)

registrar_handlers(app)  # todo erro sai como {codigo, mensagem}

# Deixa o front (HTML/JS em outro endereço) chamar a API pelo navegador
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origens.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

app.include_router(auth.router)
app.include_router(areas.router)
app.include_router(cep.router)
app.include_router(ocorrencias.router)
app.include_router(fotos.router)
app.include_router(gestao.router)
app.include_router(admin.router)
app.include_router(sinalizacoes.router)


@app.get("/saude")
def saude(conn=Depends(get_conn)):
    """Teste rápido de ponta a ponta: API -> banco -> PostGIS -> índice de ocorrências abertas."""
    row = conn.execute(
        """
        SELECT current_user      AS usuario_banco,
               postgis_version() AS postgis,
               (SELECT count(*) FROM ocorrencias WHERE status = 'aberta') AS ocorrencias_abertas
        """
    ).fetchone()
    return {"status": "ok", **row}


# O front vai por último, para nunca esconder uma rota da API
if settings.web_dir.is_dir():
    app.mount("/web", StaticFiles(directory=settings.web_dir, html=True), name="web")