-- =====================================================================
-- PavimentAI - Esquema Base Inicial (v1)
-- Rodar como superusuário (postgres) no banco 'pavimentai'.
-- Idempotente: pode ser executado mais de uma vez sem erro.
-- =====================================================================
BEGIN;

-- 1) Extensões obrigatórias
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2) Papel de aplicação (Princípio do Menor Privilégio)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pavimentai_app') THEN
        CREATE ROLE pavimentai_app LOGIN PASSWORD 'trocar_no_env';
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO pavimentai_app;

-- 3) Tabela de Usuários
CREATE TABLE IF NOT EXISTS public.usuarios (
    id_usuario               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome                     varchar(120) NOT NULL,
    email                    varchar(254) NOT NULL UNIQUE,
    telefone                 varchar(20)  NOT NULL UNIQUE,
    hash_senha               text         NOT NULL,
    papel                    varchar(20)  NOT NULL DEFAULT 'cidadao'
                             CHECK (papel IN ('cidadao', 'gestor', 'admin')),
    status_conta             varchar(20)  NOT NULL DEFAULT 'pendente'
                             CHECK (status_conta IN ('pendente', 'ativa', 'suspensa', 'desativada')),
    email_verificado         boolean      NOT NULL DEFAULT false,
    email_verificado_em      timestamptz,
    telefone_verificado      boolean      NOT NULL DEFAULT false,
    telefone_verificado_em   timestamptz,
    criado_em                timestamptz  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_email_lower ON public.usuarios (lower(email));

-- 4) Verificações de Contato (E-mail / SMS)
CREATE TABLE IF NOT EXISTS public.verificacoes_contato (
    id_verificacao bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_usuario     bigint      NOT NULL REFERENCES public.usuarios (id_usuario) ON DELETE CASCADE,
    canal          varchar(10) NOT NULL CHECK (canal IN ('email', 'sms')),
    token_hash     text        NOT NULL,
    tentativas     integer     NOT NULL DEFAULT 0 CHECK (tentativas >= 0),
    criado_em      timestamptz NOT NULL DEFAULT now(),
    expira_em      timestamptz NOT NULL,
    usado_em       timestamptz
);

CREATE INDEX IF NOT EXISTS ix_verificacoes_usuario
    ON public.verificacoes_contato (id_usuario, canal, criado_em DESC);

-- 5) Ocorrências (com coluna geográfica gerada automaticamente a partir de lat/lon)
CREATE TABLE IF NOT EXISTS public.ocorrencias (
    id_ocorrencia           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo                    varchar(20)      NOT NULL,
    categoria               varchar(40),
    descricao               text,
    gravidade_cidadao       varchar(15)      CHECK (gravidade_cidadao IN ('leve', 'moderado', 'grave')),
    gravidade_verificada    varchar(15)      CHECK (gravidade_verificada IN ('leve', 'moderado', 'grave')),
    latitude                double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude               double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    localizacao             geography(Point, 4326) GENERATED ALWAYS AS (
                                ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
                            ) STORED,
    status                  varchar(15)      NOT NULL DEFAULT 'aberta'
                            CHECK (status IN ('aberta', 'resolvida', 'descartada', 'duplicada')),
    canal_registro          varchar(20)      NOT NULL DEFAULT 'app_cidadao',
    id_usuario_criador      bigint           REFERENCES public.usuarios (id_usuario),
    id_gestor_verificador   bigint           REFERENCES public.usuarios (id_usuario),
    id_ocorrencia_principal bigint           REFERENCES public.ocorrencias (id_ocorrencia),
    criado_em               timestamptz      NOT NULL DEFAULT now(),
    verificada_em           timestamptz
);

CREATE INDEX IF NOT EXISTS idx_ocorrencias_localizacao ON public.ocorrencias USING gist (localizacao);
CREATE INDEX IF NOT EXISTS idx_ocorrencias_criador ON public.ocorrencias (id_usuario_criador, criado_em DESC);

-- 6) Mídias (Fotos enviadas)
CREATE TABLE IF NOT EXISTS public.midias (
    id_midia         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    caminho_arquivo  text         NOT NULL,
    nome_arquivo     varchar(255) NOT NULL,
    tipo_mime        varchar(50)  NOT NULL DEFAULT 'image/jpeg',
    origem           varchar(20)  NOT NULL CHECK (origem IN ('foto_cidadao', 'foto_gestao')),
    hash_arquivo     char(64)     NOT NULL,
    largura_pixels   integer,
    altura_pixels    integer,
    capturada_em     timestamptz,
    id_usuario_envio bigint       REFERENCES public.usuarios (id_usuario),
    enviada_em       timestamptz  NOT NULL DEFAULT now()
);

-- 7) Ligação N:N entre Ocorrências e Mídias
CREATE TABLE IF NOT EXISTS public.ocorrencia_midias (
    id_ocorrencia bigint      NOT NULL REFERENCES public.ocorrencias (id_ocorrencia) ON DELETE CASCADE,
    id_midia      bigint      NOT NULL REFERENCES public.midias (id_midia) ON DELETE CASCADE,
    finalidade    varchar(20) NOT NULL DEFAULT 'evidencia' CHECK (finalidade IN ('evidencia', 'revisao')),
    PRIMARY KEY (id_ocorrencia, id_midia)
);

-- 8) Detecções da IA (YOLO)
CREATE TABLE IF NOT EXISTS public.deteccoes_ia (
    id_deteccao        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_midia           bigint           NOT NULL REFERENCES public.midias (id_midia) ON DELETE CASCADE,
    id_ocorrencia      bigint           NOT NULL REFERENCES public.ocorrencias (id_ocorrencia) ON DELETE CASCADE,
    classe_detectada   varchar(30)      NOT NULL,
    confianca          double precision NOT NULL CHECK (confianca BETWEEN 0 AND 1),
    bbox_x             double precision NOT NULL,
    bbox_y             double precision NOT NULL,
    bbox_largura       double precision NOT NULL,
    bbox_altura        double precision NOT NULL,
    gravidade_estimada varchar(15)      CHECK (gravidade_estimada IN ('leve', 'moderado', 'grave')),
    metodo_estimativa  varchar(30),
    caracteristicas    jsonb,
    versao_modelo      varchar(60),
    processada_em      timestamptz      NOT NULL DEFAULT now()
);

-- 9) Histórico de Status da Ocorrência
CREATE TABLE IF NOT EXISTS public.historico_status (
    id_historico    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_ocorrencia   bigint      NOT NULL REFERENCES public.ocorrencias (id_ocorrencia) ON DELETE CASCADE,
    id_usuario      bigint      REFERENCES public.usuarios (id_usuario),
    status_anterior varchar(15),
    status_novo     varchar(15) NOT NULL,
    justificativa   text,
    alterado_em     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_historico_ocorrencia ON public.historico_status (id_ocorrencia, alterado_em DESC);

-- 10) Sinalizações de Cidadãos
CREATE TABLE IF NOT EXISTS public.sinalizacoes (
    id_sinalizacao         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_ocorrencia          bigint      NOT NULL REFERENCES public.ocorrencias (id_ocorrencia) ON DELETE CASCADE,
    id_usuario             bigint      NOT NULL REFERENCES public.usuarios (id_usuario),
    motivo                 varchar(30) NOT NULL
                           CHECK (motivo IN ('duplicidade', 'localizacao_incorreta', 'informacao_incorreta', 'nao_e_um_problema', 'outro')),
    descricao              varchar(500),
    id_ocorrencia_original bigint      REFERENCES public.ocorrencias (id_ocorrencia),
    status_analise         varchar(15) NOT NULL DEFAULT 'pendente'
                           CHECK (status_analise IN ('pendente', 'aceita', 'rejeitada')),
    id_gestor_analista     bigint      REFERENCES public.usuarios (id_usuario),
    criada_em              timestamptz NOT NULL DEFAULT now(),
    analisada_em           timestamptz
);

-- 11) Trilha de Auditoria Imutável (Append-Only para a API)
CREATE TABLE IF NOT EXISTS public.auditoria (
    id_auditoria        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_usuario          bigint      REFERENCES public.usuarios (id_usuario),
    acao                varchar(60) NOT NULL,
    entidade_afetada    varchar(40),
    id_registro_afetado bigint,
    detalhes            jsonb,
    criado_em           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_auditoria_usuario_acao
    ON public.auditoria (id_usuario, acao, criado_em DESC);

-- 12) Permissões da API (pavimentai_app)
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;

-- O REVOKE acima também tira a leitura da tabela de sistemas de coordenadas do PostGIS,
-- que as funções ST_* consultam. Sem este GRANT, toda rota com mapa/GPS dá erro 500.
GRANT SELECT ON public.spatial_ref_sys TO pavimentai_app;

GRANT SELECT, INSERT ON public.usuarios TO pavimentai_app;
GRANT UPDATE (nome, telefone, hash_senha, email_verificado, email_verificado_em, status_conta)
    ON public.usuarios TO pavimentai_app;

GRANT SELECT, INSERT, UPDATE (tentativas, usado_em) ON public.verificacoes_contato TO pavimentai_app;
GRANT SELECT, INSERT, UPDATE (status, id_ocorrencia_principal, gravidade_cidadao, gravidade_verificada, id_gestor_verificador, verificada_em)
    ON public.ocorrencias TO pavimentai_app;
GRANT SELECT, INSERT ON public.midias, public.ocorrencia_midias, public.deteccoes_ia, public.historico_status TO pavimentai_app;
GRANT SELECT, INSERT, UPDATE (status_analise, id_gestor_analista, analisada_em) ON public.sinalizacoes TO pavimentai_app;
GRANT SELECT, INSERT ON public.auditoria TO pavimentai_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO pavimentai_app;

COMMIT;