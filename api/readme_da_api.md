# PavimentAI — API Backend & Geoprocessamento

Plataforma inteligente para zeladoria urbana colaborativa (detecção de buracos na via com Visão Computacional e problemas de acessibilidade), multi-município, com isolamento geográfico oficial via IBGE/PostGIS e trilha de auditoria imutável.

**Tecnologias:** Python 3.11 / 3.12, FastAPI, PostgreSQL + PostGIS, Psycopg 3 (Connection Pool), Pillow, Ultralytics YOLO11, Argon2 (`pwdlib`) e PyJWT.

## Perfis de Acesso

| Perfil | Permissões e Funcionalidades |
| :--- | :--- |
| **Cidadão** | Cria conta verificada por e-mail, informa CEP de residência, registra ocorrências geolocalizadas com foto validada por IA (YOLO11n) e sinaliza ocorrências de terceiros. |
| **Gestor** | Vinculado a **um** município específico. Visualiza indicadores, fila priorizada por gravidade/IA, aprova ou recusa fotos na Fila de Triagem da IA, altera status e analisa sinalizações. |
| **Admin** | Cadastra municípios baixando a malha oficial do IBGE, define se a cidade exige residência local, gerencia o catálogo de tipos de ocorrência e promove gestores usando conexão de banco segregada (`pavimentai_admin`). |

## Como executar localmente

Dentro da pasta `api`, com o ambiente virtual ativo:

```bash
pip install -r requirements.txt
cp .env.example .env            # configure as senhas do banco e o JWT_SECRET

# Aplicação das migrações do banco de dados e funções geoespaciais
python scripts/aplicar_sql.py sql/banco.sql sql/migracao_pavimentai_v2.sql sql/migracao_pavimentai_v3.sql sql/migracao_pavimentai_v4.sql sql/migracao_pavimentai_v5.sql sql/migracao_pavimentai_v6.sql sql/migracao_pavimentai_v7.sql sql/migracao_pavimentai_v8.sql sql/migracao_pavimentai_v9.sql sql/migracao_pavimentai_v10.sql

# Inserção de limites geográficos de exemplo
python scripts/aplicar_sql.py sql/limite_ribeirao_pires.sql
python scripts/criar_papel_admin_db.py

# Inicialização do servidor
python -m uvicorn app.main:app --reload
```

- **Documentação Interativa (Swagger UI):** `http://127.0.0.1:8000/docs`
- **Healthcheck (Banco + PostGIS):** `http://127.0.0.1:8000/saude`
- **Aplicação Web Integrada (SPA):** `http://127.0.0.1:8000/web/`

## Scripts Utilitários (`api/scripts/`)

| Script | Finalidade |
| :--- | :--- |
| `aplicar_sql.py` | Aplica scripts `.sql` em ordem numérica natural e com transação atômica por arquivo. |
| `baixar_limite.py` | Baixa a malha municipal oficial do IBGE e gera o `.sql` idempotente (`sql/limite_<cidade>.sql`). |
| `criar_papel_admin_db.py` | Cria e configura a role restrita `pavimentai_admin` para as rotas `/admin/*`. |
| `definir_papel.py` | Promove usuários (`cidadao`, `gestor`, `admin`) via CLI registrando na auditoria. |
| `ver_usuarios.py` | Lista usuários, status da conta, papéis e municípios vinculados. |
| `exportar_triagem_yolo.py` | Exporta as fotos aprovadas/recusadas pelos gestores para um dataset no formato YOLO (Active Learning). |

## Camadas de Segurança e Antifraude Implementadas

1. **Cerca Geográfica PostGIS:** Só aceita ocorrências dentro do polígono oficial (`ST_DWithin` com tolerância configurável de divisa) de municípios ativos.
2. **Antifraude Fotográfico e LGPD:** Exige foto recente e próxima ao local (`ST_Distance`), bloqueia fotos duplicadas (SHA-256) ou visualmente similares em outras ocorrências (*dHash* perceptual de 64 bits via `bit_count` no PostgreSQL), corrige orientação e remove todos os metadados EXIF ao regravar a imagem.
3. **Triagem Inteligente com YOLO11n:** Fotos da câmera com confiança $\ge 50\%$ são confirmadas automaticamente e preenchem a severidade estimada pela área da *bounding box*; fotos entre $25\%$ e $50\%$ (ou vindas da galeria) vão para a Fila de Triagem do Gestor; fotos $< 25\%$ são recusadas na hora.
4. **Segregação de Privilégios no PostgreSQL:** A conexão pública (`pavimentai_app`) não tem permissão de `DELETE` nem de alterar papéis ou áreas; a conexão administrativa (`pavimentai_admin`) só altera colunas específicas e nunca lê hashes de senha.
5. **Conformidade LGPD (`DELETE /auth/me`):** Anonimização irreversível de dados pessoais de cidadãos via `SECURITY DEFINER` preservando o histórico estatístico da zeladoria urbana.