FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

# Dependências mínimas de sistema para OpenCV Headless / Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Instala as dependências Python da API
COPY api/requirements.txt /workspace/api/requirements.txt
RUN pip install --upgrade pip && pip install -r /workspace/api/requirements.txt pytest httpx

# Copia os módulos do projeto (api, ml com pesos e web)
COPY api /workspace/api
COPY ml /workspace/ml
COPY web /workspace/web

WORKDIR /workspace/api

# Cria diretório persistente de uploads com permissões adequadas
RUN mkdir -p /workspace/api/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]