FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

# Bibliotecas de sistema que o OpenCV (headless) e o Pillow precisam
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# PyTorch só para CPU: a versão padrão do pip traz CUDA e a imagem passa de 5 GB
RUN pip install --upgrade pip && \
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Dependências da API (httpx2 é exigido pelo TestClient do FastAPI nos testes)
COPY api/requirements.txt /workspace/api/requirements.txt
RUN pip install -r /workspace/api/requirements.txt pytest pytest-cov httpx httpx2

# O .env NÃO entra na imagem (veja .dockerignore): o compose injeta as variáveis
COPY api /workspace/api
COPY ml /workspace/ml
COPY web /workspace/web

WORKDIR /workspace/api
RUN mkdir -p /workspace/api/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
