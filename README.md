# PavimentAI

Sistema para registrar e acompanhar buracos nas ruas (e problemas de acessibilidade) por município.
O cidadão manda a foto e a localização, um modelo YOLO11n confere se a foto mostra um buraco, e a
prefeitura acompanha tudo num painel com mapa, fila de triagem e alertas.

Projeto escolar. Back-end e contrato da API: Rebeca. Front: João e Victoria.

## Como subir tudo (Docker)

Precisa só do Docker com o Compose. Na raiz do projeto:

```bash
# 1) senha do superusuário do banco (arquivo .env na raiz)
cp .env.example .env

# 2) configuração da API
cp api/.env.example api/.env
```

Abra o `api/.env` e preencha:

- `DB_PASSWORD`: senha que o usuário `pavimentai_app` vai usar (é obrigatória);
- `DB_ADMIN_PASSWORD`: senha do usuário `pavimentai_admin` (rotas `/admin`), com 10 caracteres ou mais;
- `JWT_SECRET`: gere um novo com `python -c "import secrets; print(secrets.token_hex(32))"`.
  O valor que vem no exemplo é público, não use em produção.

Depois:

```bash
docker compose up --build
```

Isso sobe o banco (PostgreSQL + PostGIS), cria as tabelas e aplica as migrações v2 a v12
(serviço `migracoes`, roda uma vez e termina) e inicia a API. Quando acabar:

| O quê | Endereço |
| :--- | :--- |
| Site (front) | http://localhost:8000/web/ |
| Documentação da API (Swagger) | http://localhost:8000/docs |
| Teste rápido de saúde (API, banco e PostGIS) | http://localhost:8000/saude |

A cidade de exemplo (Ribeirão Pires) já vem cadastrada. Para não inserir, ponha `SEMEAR_CIDADE=0` no `api/.env`.

### Comandos úteis

```bash
docker compose logs -f api                              # ver os logs da API
docker compose down                                     # parar (os dados ficam guardados)
docker compose down -v                                  # parar e apagar banco e uploads
docker compose run --rm migracoes                       # reaplicar as migrações depois de puxar código novo
```

Para rodar sem Docker, veja `api/readme_da_api.md`.

## Estrutura

```text
pavimentAI/
├── api/                 # back-end FastAPI + PostgreSQL/PostGIS
│   ├── app/             # rotas, segurança, serviço do YOLO, alertas
│   ├── scripts/         # inicializar_banco.py, criação de admin, malha do IBGE, exportação para treino
│   ├── sql/             # banco.sql, migrações v2..v12 e limite da cidade de exemplo
│   └── tests/           # testes (pytest)
├── ml/                  # modelo de visão computacional
│   ├── dados_treinamento/   # métricas, curvas e matrizes do treino
│   ├── models/yolo11n/      # coloque aqui o best.pt (fora do Git)
│   ├── inference/           # testa o modelo em fotos e vídeos
│   ├── checar_vazamento.py  # confere repetição de imagens entre treino, validação e teste
│   └── coletar_mapillary.py # baixa fotos de ruas abertas (Mapillary)
├── web/                 # front em HTML/JS (veja web/README.md)
├── Dockerfile
└── docker-compose.yaml  # banco + migrações + API
```

## Como o sistema decide se uma foto é um buraco

O modelo (YOLO11n, mAP@50 de 89,1% na validação e 84,9% no conjunto de teste) devolve uma confiança por foto:

- 60% ou mais, com foto tirada na hora: ocorrência confirmada no mapa. A gravidade (leve, moderado ou grave) vem do tamanho da caixa na imagem.
- Entre 25% e 60%, ou foto da galeria: vai para a fila de triagem, onde o gestor aprova ou recusa.
- Abaixo de 25%: a foto é recusada na hora, com dica de enquadramento.

As decisões do gestor na triagem podem virar dataset de treino com `api/scripts/exportar_triagem_yolo.py`.

## Segurança e privacidade

- Só aceita ocorrência dentro do limite oficial do município (malha do IBGE no PostGIS).
- Confere a distância e o horário da foto, e recusa foto repetida ou muito parecida com outra já enviada.
- Remove os metadados EXIF das imagens ao salvar.
- Limite de requisições por IP em login, cadastro, reenvio de código e recuperação de senha.
- Sessões com refresh token (guardado só como hash) e logout que revoga a sessão.
- A conta pode ser excluída (`DELETE /auth/me`): os dados pessoais são anonimizados e o histórico das ocorrências fica.

## Mais documentação

- [API e banco de dados](api/readme_da_api.md)
- [Modelo de visão computacional](ml/readme_de_machine_learning.md)
- [Front-end](web/README.md)
