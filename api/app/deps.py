from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from .db import get_conn
from .seguranca import ler_token_com_sessao

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")
# Para rotas públicas que mostram mais coisas a quem está logado (sem exigir login)
oauth2_opcional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# Colunas do usuário que a API carrega a cada requisição (nunca inclui a senha)
COLUNAS_USUARIO = """
    id_usuario, nome, email, telefone, papel, status_conta,
    email_verificado, telefone_verificado,
    (cep IS NOT NULL) AS residencia_informada,
    municipio_residencia, uf_residencia, id_area_residencia, id_area_gestao
"""


def usuario_atual(token: str = Depends(oauth2), conn=Depends(get_conn)):
    """Descobre quem está logado a partir do token.

    Confere no banco a cada requisição: se o gestor suspender uma conta,
    o bloqueio vale na hora, mesmo com o token ainda dentro do prazo.
    """
    erro = HTTPException(
        401,
        "Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    identidade = ler_token_com_sessao(token)
    if identidade is None:
        raise erro
    id_usuario, id_sessao = identidade
    u = conn.execute(
        f"""
        SELECT {COLUNAS_USUARIO} FROM usuarios
        WHERE id_usuario = %s AND status_conta = 'ativa'
          AND EXISTS (
              SELECT 1 FROM sessoes
              WHERE id_sessao = %s AND id_usuario = %s
                AND revogada_em IS NULL AND expira_em > now()
          )
        """,
        (id_usuario, id_sessao, id_usuario),
    ).fetchone()
    if u is None:
        raise erro
    u["id_sessao"] = id_sessao
    return u


def usuario_opcional(token: str | None = Depends(oauth2_opcional), conn=Depends(get_conn)):
    """Igual a usuario_atual, mas devolve None (visitante) em vez de erro.
    Token ausente, inválido ou de conta suspensa conta como visitante."""
    if not token:
        return None
    identidade = ler_token_com_sessao(token)
    if identidade is None:
        return None
    id_usuario, id_sessao = identidade
    u = conn.execute(
        f"""
        SELECT {COLUNAS_USUARIO} FROM usuarios
        WHERE id_usuario = %s AND status_conta = 'ativa'
          AND EXISTS (
              SELECT 1 FROM sessoes
              WHERE id_sessao = %s AND id_usuario = %s
                AND revogada_em IS NULL AND expira_em > now()
          )
        """,
        (id_usuario, id_sessao, id_usuario),
    ).fetchone()
    if u is None:
        return None
    u["id_sessao"] = id_sessao
    return u


def exigir_gestao_da_area(u: dict, id_area: int | None) -> None:
    """Isolamento por município: admin gerencia qualquer cidade; gestor só a dele.
    Chame esta função em TODA rota de gestão que mexa numa ocorrência."""
    if u["papel"] == "admin":
        return
    if u["papel"] == "gestor" and id_area is not None and u["id_area_gestao"] == id_area:
        return
    raise HTTPException(
        403,
        {"codigo": "outro_municipio", "mensagem": "Esta ocorrência pertence a outro município."},
    )


def checar_quem_pode_registrar(u: dict, id_area: int | None, exige_residencia: bool) -> None:
    """Regras por perfil ao criar ou sinalizar ocorrências, considerando o município."""
    if u["papel"] == "admin":
        return
    if u["papel"] == "gestor":
        if id_area is None or u["id_area_gestao"] != id_area:
            raise HTTPException(
                403,
                {"codigo": "outro_municipio", "mensagem": "Você administra outro município."},
            )
        return
    # Cidadão: se o município exigir residência local, confere id_area_residencia
    if exige_residencia and id_area is not None:
        if not u.get("residencia_informada") or u.get("id_area_residencia") != id_area:
            raise HTTPException(
                403,
                {
                    "codigo": "exige_residencia",
                    "mensagem": (
                        "Este município exige que você seja morador cadastrado na cidade "
                        "para registrar ou sinalizar ocorrências. Informe seu CEP no perfil."
                    ),
                },
            )


def exigir_papel(*papeis: str):
    """Uso: Depends(exigir_papel('gestor', 'admin')) protege rotas de gestão."""
    def checar(u=Depends(usuario_atual)):
        if u["papel"] not in papeis:
            raise HTTPException(403, "Sem permissão para esta ação")
        return u
    return checar