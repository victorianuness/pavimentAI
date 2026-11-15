from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Lê as variáveis do arquivo api/.env independentemente de onde o comando uvicorn for executado
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "pavimentai"
    db_user: str = "pavimentai_app"
    db_password: str  # obrigatória: sem ela a API nem sobe

    jwt_secret: str = Field(min_length=32)  # obrigatória, mínimo 32 caracteres
    jwt_expira_minutos: int = 60
    ambiente: str = "dev"  # "dev" ou "prod"

    raio_duplicidade_m: int = 15  # ocorrência aberta a menos de X metros = possível duplicada
    limite_ocorrencias_hora: int = 20  # máximo de registros por usuário por hora

    # Cerca geográfica: tolerância (erro do GPS perto da divisa do município)
    tolerancia_area_m: int = 30

    # Front-end: endereços de sites que podem chamar a API pelo navegador (CORS),
    # separados por vírgula. O endereço do seu site publicado entra aqui (CORS_ORIGENS no .env).
    cors_origens: str = (
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )
    # Se esta pasta existir, a API também entrega o front em /web (mesmo endereço da API)
    web_dir: Path = Path(__file__).resolve().parents[2] / "web"

    # Proteção do login: depois de X senhas erradas seguidas, a conta espera um tempo
    max_falhas_login: int = 5
    bloqueio_login_min: int = 15

    # Limites por IP dos endpoints que geram custo, e-mail ou tentativa de autenticação.
    limite_ip_login: int = 20
    janela_ip_login_min: int = 15
    limite_ip_cadastro: int = 5
    janela_ip_cadastro_h: int = 1
    limite_ip_reenvio_codigo: int = 5
    janela_ip_reenvio_codigo_h: int = 1
    limite_ip_esqueci_senha: int = 5
    janela_ip_esqueci_senha_h: int = 1
    # Só preencha com IPs de proxies sob seu controle. Nunca confie cegamente no header.
    proxies_confiaveis: str = ""

    # Conexão separada, só do painel de admin (cadastrar cidades e mudar papéis).
    # Criada com: python scripts/criar_papel_admin_db.py
    db_admin_user: str | None = None
    db_admin_password: str | None = None
    ibge_api_url: str = "https://servicodados.ibge.gov.br/api"

    # Consulta de CEP (ViaCEP com fallback automático para BrasilAPI)
    cep_api_url: str = "https://viacep.com.br/ws"
    cep_timeout_s: int = 4
    dias_troca_residencia: int = 30  # o cidadão só pode trocar a cidade de residência a cada X dias

    # Antifraude das fotos de cidadãos
    janela_foto_min: int = 15  # a foto só vale até X minutos depois de registrar a ocorrência
    raio_foto_m: int = 100     # o aparelho precisa estar a menos de X metros da ocorrência

    # Clusters do mapa. Estes limites descrevem concentração de relatos, não risco.
    cluster_alerta_moderado_min: int = Field(default=5, ge=3, le=10000)
    cluster_alerta_alto_min: int = Field(default=10, ge=3, le=10000)

    # Pasta onde as fotos ficam guardadas (por padrão: api/uploads).
    uploads_dir: Path = Path(__file__).resolve().parents[1] / "uploads"

    # Caminho opcional do modelo YOLO (.pt ou .onnx). Se vazio, servico_yolo.py descobre automaticamente.
    yolo_model_path: Path | None = None

    # Token opcional da API Pública do Mapillary (CC-BY-SA) para coleta de imagens de ruas abertas
    mapillary_token: str | None = None

    # E-mail (opcional). Sem SMTP_HOST nenhum e-mail é enviado de verdade (aparece no terminal em dev)
    smtp_host: str | None = None
    smtp_porta: int = 587
    smtp_usuario: str | None = None
    smtp_senha: str | None = None
    smtp_remetente: str | None = None

    @model_validator(mode="after")
    def validar_limites_de_cluster(self):
        if self.cluster_alerta_moderado_min >= self.cluster_alerta_alto_min:
            raise ValueError(
                "CLUSTER_ALERTA_MODERADO_MIN precisa ser menor que CLUSTER_ALERTA_ALTO_MIN"
            )
        return self


settings = Settings()