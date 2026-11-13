import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from .config import settings

_hasher = PasswordHash.recommended()  # Argon2

# Hash falso: o login gasta o mesmo tempo mesmo quando o e-mail não existe,
# para ninguém descobrir quais e-mails têm conta medindo o tempo da resposta.
_HASH_FALSO = _hasher.hash("senha-falsa-para-igualar-o-tempo")

# Chave derivada específica para códigos de 6 dígitos (separação de domínio criptográfico do JWT)
_HMAC_KEY = hashlib.sha256(f"pavimentai-otp:{settings.jwt_secret}".encode()).digest()
_JWT_ISSUER = "pavimentai-api"


def gerar_hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def verificar_senha(senha: str, hash_guardado: str | None) -> bool:
    if hash_guardado is None:
        _hasher.verify(senha, _HASH_FALSO)
        return False
    return _hasher.verify(senha, hash_guardado)


def gerar_codigo_6_digitos() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_codigo(id_usuario: int, codigo: str) -> str:
    """O código nunca é guardado em texto puro no banco, só este hash HMAC-SHA256."""
    msg = f"{id_usuario}:{codigo}".encode()
    return hmac.new(_HMAC_KEY, msg, hashlib.sha256).hexdigest()


def criar_token(id_usuario: int) -> str:
    agora = datetime.now(timezone.utc)
    payload = {
        "sub": str(id_usuario),
        "iss": _JWT_ISSUER,
        "iat": agora,
        "exp": agora + timedelta(minutes=settings.jwt_expira_minutos),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def ler_token(token: str) -> int | None:
    """Devolve o id do usuário, ou None se o token for inválido/expirado."""
    try:
        dados = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "iat"]},
        )
        return int(dados["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None