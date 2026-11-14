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
cp .env.example .env            # configure as senhas do banco e gere um JWT_SECRET novo

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

## Clusters regionais do mapa

`GET /ocorrencias/clusters` agrupa ocorrências visíveis ao usuário em células quadradas métricas, calculadas no PostGIS. Foi escolhida uma grade regular (em vez de DBSCAN) porque fornece células estáveis, fáceis de resumir e adequadas ao mapa existente. A consulta escolhe a zona UTM pelo centro da área consultada, transforma os pontos para essa projeção apenas para formar as células e devolve o centro de cada célula em longitude/latitude (EPSG:4326). O filtro espacial continua aplicado à coluna `geography` indexada, sem transformá-la.

Exemplo:

```text
/ocorrencias/clusters?lat_min=-23.72&lat_max=-23.62&lon_min=-46.51&lon_max=-46.41&tamanho_celula_m=250&minimo_ocorrencias=3&dias=30
```

Parâmetros:

| Parâmetro | Padrão | Limites / comportamento |
| :--- | :--- | :--- |
| `lat_min`, `lat_max`, `lon_min`, `lon_max` | Obrigatórios | Limites da área visível; máximo de 2 graus em cada eixo para limitar o custo da agregação. |
| `tamanho_celula_m` | 250 | 50 a 1.000 metros. |
| `minimo_ocorrencias` | 3 | 2 a 100 por célula. |
| `dias` | 30 | Janela de 1 a 3.650 dias. |
| `limite` | 500 | Máximo de features retornadas, entre 1 e 2.000; `truncado` indica se há mais resultados. |
| `tipo` | Todos | Código de tipo do catálogo, por exemplo `buraco`. |
| `categorias` | Todas | Pode ser repetido; ex.: `categorias=travessia&categorias=piso_tatil`. |
| `status` | `aberta` | Pode ser repetido para incluir status como `resolvida`. |
| `id_area` | Todas | Limita os resultados a uma área. |
| `verificacao` | `verificadas` | `todas` exige gestão; gestores veem somente a própria área. |

A resposta é um `FeatureCollection` GeoJSON. Cada `Feature` contém o centro da célula e `properties` com referência espacial, total, totais por tipo/categoria, gravidade e status, além de `nivel_concentracao`. Os níveis usam limites configuráveis em `CLUSTER_ALERTA_MODERADO_MIN` e `CLUSTER_ALERTA_ALTO_MIN` (padrões 5 e 10). São heurísticas de concentração de relatos; não são limites científicos, previsão de acidentes ou classificação de perigo. Gravidades não comparáveis, como as de ocorrências de acessibilidade, são contabilizadas como `sem_classificacao`.

Exemplo reduzido de resposta:

```json
{
  "type": "FeatureCollection",
  "tamanho_celula_m": 250,
  "minimo_ocorrencias": 3,
  "periodo_dias": 30,
  "srid_metrico": 32723,
  "limite_clusters": 500,
  "truncado": false,
  "features": [{
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-46.42, -23.70]},
    "properties": {
      "referencia_espacial": "epsg:32723:250:-186:258",
      "total_ocorrencias": 3,
      "nivel_concentracao": "normal",
      "por_tipo": [{"tipo": "acessibilidade", "total": 3, "categorias": {"travessia": 3}}],
      "por_gravidade": {"sem_classificacao": 3},
      "por_status": {"aberta": 3}
    }
  }]
}
```

A regra de visibilidade segue o mapa existente: ocorrências verificadas são públicas; `verificacao=todas` inclui registros não verificados somente para gestão. O endpoint não expõe dados pessoais, fotos ou detecções como linhas independentes. A grade não é um agrupamento por distância: pontos em lados opostos da borda de uma célula podem ficar separados; a posição do marcador é o centro da célula, não o centroide dos relatos. O cálculo UTM é limitado à faixa entre 80°S e 84°N. Não há migração adicional; o índice GiST existente na localização é usado no filtro da área.

Para validar a implementação, rode `pytest tests/test_api.py.py tests/test_contrato_dia1.py` dentro de `api`. Os testes de rota exigem o banco de integração PostGIS descrito em `tests/conftest.py`; sem `TEST_ADMIN_DSN` ou sem um banco cujo nome termine em `_teste`, eles serão ignorados e não contarão como validação de integração.

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
3. **Triagem Inteligente com YOLO11n:** Fotos da câmera com confiança $\ge 60\%$ são confirmadas automaticamente e preenchem a severidade estimada pela área da *bounding box*; fotos entre $25\%$ e $60\%$ (ou vindas da galeria) vão para a Fila de Triagem do Gestor; fotos $< 25\%$ são recusadas na hora.
4. **Segregação de Privilégios no PostgreSQL:** A conexão pública (`pavimentai_app`) não tem permissão de `DELETE` nem de alterar papéis ou áreas; a conexão administrativa (`pavimentai_admin`) só altera colunas específicas e nunca lê hashes de senha.
5. **Conformidade LGPD (`DELETE /auth/me`):** Anonimização irreversível de dados pessoais de cidadãos via `SECURITY DEFINER` preservando o histórico estatístico da zeladoria urbana.