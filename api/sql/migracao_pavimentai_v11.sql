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

COMMIT;

SELECT to_regclass('public.limites_requisicoes_ip') IS NOT NULL AS tabela_limite_ip;
