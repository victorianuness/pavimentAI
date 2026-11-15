-- Limite distribuído por IP para autenticação e envio de códigos.
BEGIN;

CREATE TABLE IF NOT EXISTS public.limites_requisicoes_ip (
    chave          text PRIMARY KEY,
    janela_inicio  timestamptz NOT NULL,
    contagem       integer NOT NULL CHECK (contagem > 0),
    atualizado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_limites_requisicoes_ip_atualizado
    ON public.limites_requisicoes_ip (atualizado_em);

REVOKE ALL ON public.limites_requisicoes_ip FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON public.limites_requisicoes_ip TO pavimentai_app;
REVOKE UPDATE ON public.limites_requisicoes_ip FROM pavimentai_app;
GRANT UPDATE (janela_inicio, contagem, atualizado_em)
    ON public.limites_requisicoes_ip TO pavimentai_app;

-- Refresh tokens são armazenados apenas como hash; access tokens apontam para id_sessao.
CREATE TABLE IF NOT EXISTS public.sessoes (
    id_sessao          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_usuario         bigint NOT NULL REFERENCES public.usuarios (id_usuario) ON DELETE CASCADE,
    refresh_token_hash char(64) NOT NULL UNIQUE,
    criado_em          timestamptz NOT NULL DEFAULT now(),
    expira_em          timestamptz NOT NULL,
    revogada_em        timestamptz,
    CONSTRAINT ck_sessoes_expira_apos_criacao CHECK (expira_em > criado_em)
);

CREATE INDEX IF NOT EXISTS ix_sessoes_usuario_ativas
    ON public.sessoes (id_usuario, expira_em)
    WHERE revogada_em IS NULL;

REVOKE ALL ON public.sessoes FROM PUBLIC;
GRANT SELECT, INSERT ON public.sessoes TO pavimentai_app;
GRANT UPDATE (refresh_token_hash, expira_em, revogada_em) ON public.sessoes TO pavimentai_app;

COMMIT;

SELECT to_regclass('public.limites_requisicoes_ip') IS NOT NULL AS tabela_limite_ip,
       to_regclass('public.sessoes') IS NOT NULL AS tabela_sessoes;
