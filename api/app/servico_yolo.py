import threading
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from ultralytics import YOLO

from .config import settings

LIMIAR_MINIMO = 0.25
LIMIAR_CONFIRMA = 0.50
VERSAO_MODELO = "yolo11n-dataset-v3"

# Gravidade estimada pela área da caixa relativa à imagem
AREA_MODERADO = 0.02
AREA_GRAVE = 0.06

_modelo = None
_lock_modelo = threading.Lock()


def _descobrir_caminho_modelo() -> Path:
    if settings.yolo_model_path and Path(settings.yolo_model_path).is_file():
        return Path(settings.yolo_model_path)

    raiz = Path(__file__).resolve().parents[2]  # pasta raiz pavimentAI
    candidatos = [
        raiz / "ml" / "models" / "yolo11n" / "best.pt",
        raiz / "ml" / "oitavotreino - joao" / "weights" / "best.onnx",
        raiz / "ml" / "oitavotreino - joao" / "weights" / "best.pt",
        raiz / "ml" / "inference" / "weights" / "best.pt",
    ]
    for c in candidatos:
        if c.is_file():
            return c
    # Fallback padrão (lançará FileNotFoundError informativo se nenhum existir)
    return raiz / "ml" / "models" / "yolo11n" / "best.pt"


def carregar_modelo():
    global _modelo
    if _modelo is None:
        with _lock_modelo:
            if _modelo is None:
                caminho = _descobrir_caminho_modelo()
                if not caminho.is_file():
                    raise FileNotFoundError(
                        f"Modelo YOLO não encontrado em {caminho}. "
                        "Coloque o arquivo best.pt ou best.onnx na pasta correta ou aponte YOLO_MODEL_PATH no .env."
                    )
                _modelo = YOLO(str(caminho))
    return _modelo


def _entre_0_e_1(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _gravidade(area: float) -> str:
    if area >= AREA_GRAVE:
        return "grave"
    if area >= AREA_MODERADO:
        return "moderado"
    return "leve"


def analisar_imagem(dados_jpeg: bytes) -> dict:
    try:
        img_raw = Image.open(BytesIO(dados_jpeg))
        imagem = ImageOps.exif_transpose(img_raw).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Arquivo de imagem inválido ou corrompido para análise da IA.") from exc

    modelo = carregar_modelo()
    with _lock_modelo:
        r = modelo.predict(imagem, imgsz=640, conf=LIMIAR_MINIMO, verbose=False)[0]

    caixas = []
    for b in r.boxes:
        x1, y1, x2, y2 = (_entre_0_e_1(v) for v in b.xyxyn[0].tolist())
        area = (x2 - x1) * (y2 - y1)
        caixas.append({
            "confianca": _entre_0_e_1(b.conf[0].item()),
            "x": x1,
            "y": y1,
            "largura": x2 - x1,
            "altura": y2 - y1,
            "area_relativa": area,
            "gravidade": _gravidade(area),
        })

    melhor = max((c["confianca"] for c in caixas), default=0.0)
    
    if melhor >= LIMIAR_CONFIRMA:
        veredito = "confirmada"
    elif melhor >= LIMIAR_MINIMO:
        veredito = "triagem"
    else:
        veredito = "recusada"

    # Determina a pior gravidade entre as caixas detectadas para consolidar a ocorrência
    pior_gravidade = None
    if caixas:
        ordem_gravidade = {"grave": 3, "moderado": 2, "leve": 1}
        pior_gravidade = max((c["gravidade"] for c in caixas), key=lambda g: ordem_gravidade.get(g, 0))

    return {
        "veredito": veredito,
        "melhor_confianca": melhor,
        "pior_gravidade": pior_gravidade,
        "caixas": caixas,
    }


def analisar_foto(caminho: str) -> dict:
    """Versão para testes no terminal (usada pelo testar_modelo.py)."""
    return analisar_imagem(Path(caminho).read_bytes())