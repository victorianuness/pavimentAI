import io
import os
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from pydantic import ValidationError

# Garante variáveis mínimas caso o ambiente de CI não tenha um arquivo .env físico
os.environ.setdefault("DB_PASSWORD", "senha_teste_ci_12345")
os.environ.setdefault("JWT_SECRET", "chave_secreta_de_teste_com_mais_de_32_caracteres_123456")

from app import imagens, schemas, seguranca, servico_yolo


# =====================================================================
# 1. Testes de Criptografia, Argon2, HMAC e JWT (seguranca.py)
# =====================================================================
def test_hash_e_verificacao_senha_argon2():
    h = seguranca.gerar_hash_senha("SenhaForte@2026")
    assert h != "SenhaForte@2026"
    assert seguranca.verificar_senha("SenhaForte@2026", h) is True
    assert seguranca.verificar_senha("SenhaErrada", h) is False
    # Proteção contra Timing Attack quando o e-mail não existe no banco (hash_guardado=None)
    assert seguranca.verificar_senha("QualquerSenha", None) is False


def test_geracao_e_leitura_jwt():
    token = seguranca.criar_token(42)
    assert seguranca.ler_token(token) == 42
    assert seguranca.ler_token(token + "adulterado") is None
    assert seguranca.ler_token("token.invalido.aqui") is None


def test_codigo_6_digitos_e_hmac():
    cod = seguranca.gerar_codigo_6_digitos()
    assert len(cod) == 6 and cod.isdigit()
    # O mesmo código para usuários diferentes deve gerar hashes diferentes
    h1 = seguranca.hash_codigo(1, cod)
    h2 = seguranca.hash_codigo(2, cod)
    assert h1 != h2


# =====================================================================
# 2. Testes de Validação de Schemas e Regras de Negócio (schemas.py)
# =====================================================================
def test_normalizacao_email_e_telefone_no_cadastro():
    cad = schemas.CadastroIn(
        nome="  Ricardo   Silva  ",
        email="  RICARDO.SILVA@Email.COM ",
        telefone="(11) 98765-4321",
        senha="senha_segura_123",
    )
    assert cad.nome == "Ricardo Silva"
    assert cad.email == "ricardo.silva@email.com"
    assert cad.telefone == "11987654321"


def test_bloqueio_coordenada_zero_zero():
    with pytest.raises(ValidationError):
        schemas.OcorrenciaIn(tipo="buraco", latitude=0.0, longitude=0.0)


def test_regras_mudanca_status_descarte_e_duplicada():
    # Descartada exige justificativa com pelo menos 5 caracteres
    with pytest.raises(ValidationError):
        schemas.MudarStatusIn(status="descartada", justificativa="oi")

    # Duplicada exige id_ocorrencia_principal
    with pytest.raises(ValidationError):
        schemas.MudarStatusIn(status="duplicada")

    valido = schemas.MudarStatusIn(status="duplicada", id_ocorrencia_principal=10)
    assert valido.id_ocorrencia_principal == 10


# =====================================================================
# 3. Testes de Processamento de Imagem, EXIF, PNG Alpha e dHash (imagens.py)
# =====================================================================
def _gerar_bytes_imagem_xadrez(formato="JPEG", modo="RGB", tamanho=(400, 300)) -> bytes:
    """Cria uma imagem com gradiente/xadrez para gerar um dHash válido."""
    img = Image.new(modo, tamanho)
    pixels = img.load()
    for x in range(tamanho[0]):
        for y in range(tamanho[1]):
            val = (x * 7 + y * 13) % 256
            if modo == "RGBA":
                pixels[x, y] = (val, val, val, 128)
            else:
                pixels[x, y] = (val, (val + 80) % 256, (val + 160) % 256)
    buf = io.BytesIO()
    img.save(buf, format=formato)
    return buf.getvalue()


def test_processar_imagem_valida_e_dhash():
    bruto = _gerar_bytes_imagem_xadrez("JPEG", "RGB", (2400, 1800))
    proc = imagens.processar(bruto)
    # Deve ter redimensionado para no máximo LADO_MAX (1920)
    assert proc.largura == 1920
    assert proc.altura == 1440
    assert proc.hash_perceptual is not None
    assert len(proc.jpeg) > 0


def test_processar_png_transparente_sem_fundo_preto():
    bruto = _gerar_bytes_imagem_xadrez("PNG", "RGBA", (300, 300))
    proc = imagens.processar(bruto)
    assert proc.largura == 300 and proc.altura == 300


def test_rejeitar_arquivo_invalido_ou_vazio():
    with pytest.raises(imagens.ImagemInvalida):
        imagens.processar(b"")
    with pytest.raises(imagens.ImagemInvalida):
        imagens.processar(b"isto_nao_eh_uma_imagem_jpeg")


# =====================================================================
# 4. Testes do Serviço YOLO com Mock (servico_yolo.py)
# =====================================================================
def test_analisar_imagem_yolo_confirmada_e_pior_gravidade():
    jpeg_bytes = _gerar_bytes_imagem_xadrez("JPEG", "RGB", (640, 640))

    # Simula uma caixa detectada pelo YOLO ocupando 10% da imagem (0.5 * 0.2 = 0.10 -> 'grave')
    caixa_mock = MagicMock()
    caixa_mock.xyxyn = [MagicMock(tolist=lambda: [0.2, 0.3, 0.7, 0.5])]
    caixa_mock.conf = [MagicMock(item=lambda: 0.82)]

    resultado_mock = MagicMock()
    resultado_mock.boxes = [caixa_mock]

    modelo_falso = MagicMock()
    modelo_falso.predict.return_value = [resultado_mock]

    with patch("app.servico_yolo.carregar_modelo", return_value=modelo_falso):
        res = servico_yolo.analisar_imagem(jpeg_bytes)

    assert res["veredito"] == "confirmada"
    assert res["melhor_confianca"] == pytest.approx(0.82)
    assert res["pior_gravidade"] == "grave"
    assert len(res["caixas"]) == 1
    assert res["caixas"][0]["area_relativa"] == pytest.approx(0.10)