import json
import re
import urllib.error
import urllib.request
from functools import lru_cache

from fastapi import HTTPException

from .config import settings

BRASILAPI_CEP_URL = "https://brasilapi.com.br/api/cep/v2"


def _pedir_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "PavimentAI/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=settings.cep_timeout_s) as resposta:
        return json.load(resposta)


def _consultar_viacep(cep: str) -> dict | None:
    """Tenta consultar no ViaCEP. Devolve None se o CEP não existir, ou levanta erro de rede."""
    url = f"{settings.cep_api_url.rstrip('/')}/{cep}/json/"
    try:
        dados = _pedir_json(url)
    except urllib.error.HTTPError as erro:
        if erro.code in (400, 404):
            return None
        raise
    if not isinstance(dados, dict) or dados.get("erro") in (True, "true"):
        return None
    ibge = str(dados.get("ibge") or "")
    if not re.fullmatch(r"\d{7}", ibge):
        raise ValueError("ViaCEP sem código IBGE válido")
    return {
        "codigo_ibge": ibge,
        "municipio": dados.get("localidade"),
        "uf": dados.get("uf"),
        "logradouro": dados.get("logradouro") or None,
        "bairro": dados.get("bairro") or None,
    }


def _consultar_brasilapi(cep: str) -> dict | None:
    """Fallback caso o ViaCEP esteja indisponível."""
    url = f"{BRASILAPI_CEP_URL}/{cep}"
    try:
        dados = _pedir_json(url)
    except urllib.error.HTTPError as erro:
        if erro.code in (400, 404):
            return None
        raise
    if not isinstance(dados, dict):
        return None
    ibge = str(dados.get("city_ibge") or "")
    if not re.fullmatch(r"\d{7}", ibge):
        return None
    return {
        "codigo_ibge": ibge,
        "municipio": dados.get("city"),
        "uf": dados.get("state"),
        "logradouro": dados.get("street") or None,
        "bairro": dados.get("neighborhood") or None,
    }


@lru_cache(maxsize=512)
def _consultar_cacheado(cep_limpo: str) -> dict:
    """Pergunta ao ViaCEP e, se houver falha de rede, tenta a BrasilAPI.
    Só respostas válidas entram no cache em memória."""
    try:
        resultado = _consultar_viacep(cep_limpo)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        try:
            resultado = _consultar_brasilapi(cep_limpo)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            raise HTTPException(
                503, "Não consegui consultar o CEP agora. Tente de novo em instantes."
            )

    if resultado is None:
        raise HTTPException(422, "CEP inválido ou não encontrado.")
    return resultado


def consultar_cep(cep: str) -> dict:
    cep_limpo = re.sub(r"\D", "", str(cep))
    if len(cep_limpo) != 8:
        raise HTTPException(422, "CEP inválido (são 8 números).")
    return dict(_consultar_cacheado(cep_limpo))