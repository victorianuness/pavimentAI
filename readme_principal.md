# PavimentAI — Zeladoria Urbana Inteligente com Visão Computacional

Plataforma colaborativa multi-município para mapeamento, validação automática por Inteligência Artificial (**YOLO11n**) e gestão pública de patologias asfálticas (buracos na via) e problemas de acessibilidade urbana.

---

## Arquitetura do Repositório

```text
PavimentAI/
├── api/                        # Backend FastAPI + PostgreSQL/PostGIS + Antifraude
│   ├── app/                    # Núcleo da API, Routers, Segurança Argon2/JWT e Serviço YOLO
│   ├── scripts/                # Scripts CLI (migrações, malha IBGE, admin DB e Active Learning)
│   ├── sql/                    # Schema base (banco.sql), migrações v2..v10 e limites municipais
│   └── tests/                  # Suíte de testes automatizados (pytest)
├── ml/                         # Visão Computacional, Treinamento e MLOps
│   ├── inference/              # Script de teste em vídeos/fotos com ByteTrack
│   ├── oitavotreino - joao/    # Pesos exportados (best.onnx, best.tflite), métricas e matrizes
│   ├── checar_vazamento.py     # Auditoria de Data Leakage (dHash de 64 bits)
│   └── coletar_mapillary.py    # Coletor de imagens públicas de ruas (Mapillary API CC-BY-SA)
├── web/                        # Aplicação Web Single-Page (SPA) Mobile-First
│   └── index.html              # Mapa Leaflet, câmera c/ compressão Canvas, Painel Gestor e Admin
├── Dockerfile                  # Imagem de produção (Python 3.12-slim + OpenCV Headless)
└── docker-compose.yml          # Orquestração PostgreSQL 16/PostGIS 3.4 + API
```

## Principais Diferenciais Técnicos

1. **Validação em Duas Etapas (IA + Triagem Humana):**
   O modelo YOLO11n (`mAP@50` de $89,1\%$ na validação e $84,9\%$ no conjunto de teste inédito) analisa cada foto enviada pelo cidadão:
   * **Confiança $\ge 50\%$ (Câmera no local):** Ocorrência confirmada automaticamente no mapa público e gravidade (leve, moderado, grave) calculada pela área relativa da *bounding box*.
   * **Confiança entre $25\%$ e $50\%$ (ou Galeria):** Encaminhada para a Fila de Triagem do Gestor, que visualiza as caixas da IA sobre a foto para aprovar ou recusar.
   * **Confiança $< 25\%$:** Foto recusada imediatamente com orientação de enquadramento.

2. **Retroalimentação Contínua (Active Learning):**
   O script `api/scripts/exportar_triagem_yolo.py` converte as decisões humanas dos gestores na Fila de Triagem em um novo dataset anotado no formato YOLO (incluindo *background samples* das fotos recusadas para eliminar falsos positivos em sombras, bueiros e remendos).

3. **Antifraude Geográfico e Fotográfico + LGPD:**
   Cerca geográfica oficial via malhas do IBGE (PostGIS), validação de distância/tempo do GPS, bloqueio de fotos repetidas ou visualmente similares (*dHash* de 64 bits com `bit_count` no banco), remoção automática de metadados EXIF ao salvar a imagem e anonimização irreversível de conta (`DELETE /auth/me`).

## Início Rápido

Consulte os guias específicos em:
* [Documentação da API e Banco de Dados (`api/README.md`)](api/README.md)
* [Documentação de Machine Learning e Avaliação de Campo (`ml/README.md`)](ml/README.md)

---

### Projeto 100% Refatorado!
Todos os **7 Blocos** foram concluídos de ponta a ponta. Se quiser testar algum fluxo específico, ajustar algum detalhe visual do `web/index.html` ou preparar um roteiro de demonstração para apresentação do projeto, é só avisar!