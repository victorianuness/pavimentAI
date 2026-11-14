"""Formato único de erro da API.

Todo erro chega ao front assim:
    {"codigo": "nao_encontrado", "mensagem": "Ocorrência não encontrada"}

Alguns erros trazem campos extras (ex.: "proximas" na duplicidade, "campos" na validação).
O front deve olhar sempre `codigo` (para decidir o que fazer) e `mensagem` (para mostrar ao usuário).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("pavimentai")

# Código padrão quando a rota não definiu um próprio
CODIGOS_PADRAO = {
    400: "requisicao_invalida",
    401: "nao_autenticado",
    403: "sem_permissao",
    404: "nao_encontrado",
    405: "metodo_nao_permitido",
    409: "conflito",
    413: "arquivo_grande",
    415: "tipo_nao_suportado",
    422: "dados_invalidos",
    429: "muitas_requisicoes",
    500: "erro_interno",
    503: "servico_indisponivel",
}

MENSAGEM_PADRAO = "Não foi possível concluir a operação."


def corpo_do_erro(status: int, detail) -> dict:
    """Converte o `detail` de uma HTTPException (texto ou dicionário) no formato padrão."""
    codigo = CODIGOS_PADRAO.get(status, f"erro_{status}")
    if isinstance(detail, dict):
        corpo = dict(detail)
        corpo.setdefault("codigo", codigo)
        corpo.setdefault("mensagem", MENSAGEM_PADRAO)
        return corpo
    return {"codigo": codigo, "mensagem": str(detail) if detail else MENSAGEM_PADRAO}


def registrar_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            corpo_do_erro(exc.status_code, exc.detail),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError):
        campos = []
        for e in exc.errors():
            caminho = [str(p) for p in e.get("loc", ()) if p not in ("body", "query", "path")]
            campos.append({"campo": ".".join(caminho) or "(corpo)", "mensagem": str(e.get("msg", ""))})
        resumo = "; ".join(f"{c['campo']}: {c['mensagem']}" for c in campos[:3])
        return JSONResponse(
            {
                "codigo": "dados_invalidos",
                "mensagem": f"Dados inválidos. {resumo}" if resumo else "Dados inválidos.",
                "campos": campos,
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, exc: Exception):
        # O detalhe técnico vai só para o log do servidor, nunca para o usuário
        log.exception("Erro inesperado em %s %s", request.method, request.url.path)
        return JSONResponse(
            {"codigo": "erro_interno", "mensagem": "Erro interno. Tente novamente em instantes."},
            status_code=500,
        )
