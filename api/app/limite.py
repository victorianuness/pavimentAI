import hashlib
import hmac
import ipaddress
from dataclasses import dataclass

from fastapi import HTTPException, Request

from .config import settings


@dataclass(frozen=True)
class RegraLimite:
    limite: int
    janela_segundos: int
    mensagem: str


def _ip_do_cliente(request: Request) -> str:
    """Usa X-Forwarded-For somente quando a conexão vem de um proxy confiável."""
    host = request.client.host if request.client else "desconhecido"
    proxies_confiaveis = {
        item.strip()
        for item in settings.proxies_confiaveis.split(",")
        if item.strip()
    }
    if host not in proxies_confiaveis:
        return host

    encaminhados = request.headers.get("x-forwarded-for", "")
    candidatos = [item.strip() for item in encaminhados.split(",") if item.strip()]
    for candidato in reversed(candidatos):
        try:
            ipaddress.ip_address(candidato)
        except ValueError:
            continue
        if candidato not in proxies_confiaveis:
            return candidato
    return host


def _chave_ip(request: Request, endpoint: str) -> str:
    ip = _ip_do_cliente(request)
    digest = hmac.new(
        hashlib.sha256(f"pavimentai-rate-limit:{settings.jwt_secret}".encode()).digest(),
        ip.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{endpoint}:{digest}"


def verificar_limite(request: Request, conn, endpoint: str, regra: RegraLimite) -> None:
    resultado = conn.execute(
        """
        INSERT INTO limites_requisicoes_ip
            (chave, janela_inicio, contagem)
        VALUES (%s, now(), 1)
        ON CONFLICT (chave) DO UPDATE
        SET janela_inicio = CASE
                WHEN limites_requisicoes_ip.janela_inicio
                     <= now() - make_interval(secs => %s)
                THEN now()
                ELSE limites_requisicoes_ip.janela_inicio
            END,
            contagem = CASE
                WHEN limites_requisicoes_ip.janela_inicio
                     <= now() - make_interval(secs => %s)
                THEN 1
                ELSE limites_requisicoes_ip.contagem + 1
            END,
            atualizado_em = now()
        RETURNING contagem
        """,
        (_chave_ip(request, endpoint), regra.janela_segundos, regra.janela_segundos),
    ).fetchone()
    # O contador deve sobreviver mesmo quando a rota termina em 4xx/5xx.
    conn.commit()
    if resultado["contagem"] > regra.limite:
        raise HTTPException(
            status_code=429,
            detail=regra.mensagem,
            headers={"Retry-After": str(regra.janela_segundos)},
        )
