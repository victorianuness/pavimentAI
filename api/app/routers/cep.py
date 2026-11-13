from typing import Annotated

from fastapi import APIRouter, Depends, Path

from .. import residencia
from ..cep import consultar_cep
from ..db import get_conn

router = APIRouter(prefix="/cep", tags=["CEP"])


@router.get("/{cep}")
def consultar(cep: Annotated[str, Path(pattern=r"^\d{5}-?\d{3}$")], conn=Depends(get_conn)):
    """Usado pela tela de cadastro: preenche cidade/bairro e avisa se a cidade já é atendida."""
    cep_limpo = cep.replace("-", "")
    info_cep = consultar_cep(cep_limpo)
    return residencia.resolver(conn, cep_limpo, info_cep=info_cep)