# PavimentAI — Módulo de Visão Computacional & MLOps (`ml`)

Pipeline de treinamento, validação, coleta aberta e inferência do modelo de detecção de patologias asfálticas (**YOLO11n**, classe única `buraco`) em fotos e vídeos reais.

## Estrutura da Pasta

- `oitavotreino - joao/weights/` — Pesos treinados e exportados para produção e borda (`best.onnx`, `best.tflite`).
- `inference/testar_modelo.py` — Executa inferência e rastreamento (*ByteTrack*) em vídeos, imagens ou pastas de fotos.
- `checar_vazamento.py` — Audita *data leakage* (imagens duplicadas ou espelhadas) entre `train`, `val` e `test` via *dHash* de 64 bits.
- `coletar_mapillary.py` — Coleta imagens públicas e abertas (CC-BY-SA) de ruas do ABC Paulista via Mapillary API v4, com opção de pré-rotulagem automática (*Pseudo-Labeling*).
- `avaliacao/planilha_avaliacao_campo.csv` — Planilha com fórmulas automáticas de Precisão, Recall e Falsos Alarmes/km para validação em campo.

## Métricas Oficiais do Modelo (`YOLO11n` — 200 Épocas)

O treinamento foi conduzido por 200 épocas em GPU NVIDIA Tesla T4 (`imgsz=640`, otimizador `AdamW`, *Cosine LR*):

| Conjunto Avaliado | Época / Split | Precisão (Box P) | Recall (Box R) | mAP@50 | mAP@50-95 | Latência (T4) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Validação (Melhor Checkpoint `best.pt`)** | Época 173 | **87,25%** | **81,53%** | **89,11%** | **56,03%** | ~5,1 ms/img |
| **Validação (Final após `close_mosaic`)** | Época 200 | 87,54% | 80,32% | 88,57% | 55,36% | ~5,1 ms/img |
| **Teste Inédito (247 imgs / 914 buracos)** | `split=test` | **83,15%** | **79,43%** | **84,90%** | **52,72%** | **5,1 ms/img** |

> **Nota Metodológica sobre a Matriz de Confusão:** No protocolo COCO/Ultralytics, o cálculo oficial do `mAP@50` (`0.8490` no teste) integra toda a curva Precision-Recall com limiar base `conf=0.001`. Para inspeção visual da Matriz de Confusão no ponto de operação da API (`conf=0.25`), o notebook `matrizes.ipynb` gera uma visualização filtrada onde predições abaixo de `0.25` são descartadas.

## Como testar o modelo em vídeos ou fotos reais

```bash
python inference/testar_modelo.py minha_rua_maua.mp4
python inference/testar_modelo.py pasta_com_fotos/
python inference/testar_modelo.py minha_rua.mp4 --conf 0.40 --salvar-frames 10
```

Os resultados são gerados em `resultados/<nome_do_arquivo>/`: `video_anotado.mp4`, `deteccoes.csv`, `resumo.txt` e `frames_deteccao/`.

## Fontes de Dados Públicas e Active Learning (Sem violar Termos do Google Maps)

1. **Coleta Aberta via Mapillary (CC-BY-SA):**

```bash
python coletar_mapillary.py --cidade maua --limite 100 --auto-rotular
python coletar_mapillary.py --cidade ribeirao_pires --limite 100 --auto-rotular
```

2. **Retroalimentação Contínua (Active Learning via Triagem do Gestor):**
   O script `api/scripts/exportar_triagem_yolo.py` exporta diretamente do banco PostgreSQL as fotos reais enviadas pelos cidadãos e validadas pelos gestores municipais (convertendo ocorrências aprovadas em *labels* positivos e ocorrências recusadas na triagem em *background samples* para eliminar falsos alarmes em tampas de bueiro, sombras e remendos).

3. **Auditoria contra Vazamento de Dados (Data Leakage):**

```bash
python checar_vazamento.py caminho/para/dataset_unificado
```