-- =====================================================================
-- PavimentAI - migração v12: alertas automáticos de cluster
-- Quando surge um cluster de novas ocorrências numa região, a API avisa
-- a secretaria da cidade por e-mail (WhatsApp fica para uma próxima etapa).
-- Pode rodar mais de uma vez sem estragar nada.
-- =====================================================================
BEGIN;

-- 1) Quem recebe os alertas de cada cidade (a secretaria).
--    canal 'whatsapp' já é aceito pelo banco, mas a API ainda só envia por e-mail.
CREATE TABLE IF NOT EXISTS public.contatos_alerta (
    id_contato         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_area            integer      NOT NULL REFERENCES public.areas_atendimento (id_area) ON DELETE CASCADE,
    canal              varchar(10)  NOT NULL DEFAULT 'email' CHECK (canal IN ('email', 'whatsapp')),
    destino            varchar(254) NOT NULL,
    rotulo             varchar(80),
    id_usuario_criador bigint REFERENCES public.usuarios (id_usuario) ON DELETE SET NULL,
    criado_em          timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT uq_contatos_alerta UNIQUE (id_area, canal, destino)
);

-- 2) Histórico de alertas gerados. Serve para duas coisas:
--    mostrar o histórico ao gestor e NÃO avisar de novo o mesmo cluster sem motivo.
CREATE TABLE IF NOT EXISTS public.alertas_cluster (
    id_alerta              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_area                integer          NOT NULL REFERENCES public.areas_atendimento (id_area),
    referencia_espacial    varchar(80)      NOT NULL,  -- mesma referência da célula em GET /ocorrencias/clusters
    tamanho_celula_m       integer          NOT NULL CHECK (tamanho_celula_m > 0),
    latitude               double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude              double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    total_ocorrencias      integer          NOT NULL CHECK (total_ocorrencias > 0),
    nivel                  varchar(10)      NOT NULL CHECK (nivel IN ('normal', 'moderada', 'alta')),
    janela_horas           integer          NOT NULL CHECK (janela_horas > 0),
    motivo                 varchar(15)      NOT NULL CHECK (motivo IN ('novo', 'escalada', 'crescimento')),
    resumo                 jsonb            NOT NULL DEFAULT '{}'::jsonb,
    status                 varchar(10)      NOT NULL DEFAULT 'pendente'
                           CHECK (status IN ('pendente', 'enviado', 'parcial', 'falhou', 'simulado')),
    destinatarios_total    integer          NOT NULL DEFAULT 0 CHECK (destinatarios_total >= 0),
    destinatarios_enviados integer          NOT NULL DEFAULT 0 CHECK (destinatarios_enviados >= 0),
    criado_em              timestamptz      NOT NULL DEFAULT now(),
    enviado_em             timestamptz
);

CREATE INDEX IF NOT EXISTS ix_alertas_cluster_celula
    ON public.alertas_cluster (id_area, referencia_espacial, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_alertas_cluster_area
    ON public.alertas_cluster (id_area, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_contatos_alerta_area
    ON public.contatos_alerta (id_area);

-- 3) Menor privilégio
REVOKE ALL ON public.contatos_alerta FROM PUBLIC;
REVOKE ALL ON public.alertas_cluster FROM PUBLIC;

-- Contatos: a API lista, cadastra e apaga (e-mail de servidor público é dado pessoal: dá para remover).
GRANT SELECT, INSERT, DELETE ON public.contatos_alerta TO pavimentai_app;

-- Alertas: a API cria e depois só atualiza o resultado do envio. Nunca apaga.
GRANT SELECT, INSERT ON public.alertas_cluster TO pavimentai_app;
GRANT UPDATE (status, destinatarios_enviados, enviado_em) ON public.alertas_cluster TO pavimentai_app;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO pavimentai_app;

COMMIT;

-- Conferência: deve voltar 1 linha com as duas colunas "true"
SELECT to_regclass('public.contatos_alerta') IS NOT NULL AS tabela_contatos,
       to_regclass('public.alertas_cluster') IS NOT NULL AS tabela_alertas;
