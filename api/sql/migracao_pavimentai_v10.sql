-- =====================================================================
-- PavimentAI - migração v10: recuperação de senha e anonimização LGPD
-- Pode rodar mais de uma vez sem estragar nada.
-- =====================================================================
BEGIN;

-- 1) Códigos de recuperação de senha (guardamos só o hash HMAC-SHA256, nunca o código)
CREATE TABLE IF NOT EXISTS public.recuperacoes_senha (
    id_recuperacao bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_usuario     bigint NOT NULL REFERENCES public.usuarios (id_usuario) ON DELETE CASCADE,
    hash_codigo    text   NOT NULL,
    tentativas     integer NOT NULL DEFAULT 0 CHECK (tentativas >= 0),
    criado_em      timestamptz NOT NULL DEFAULT now(),
    expira_em      timestamptz NOT NULL,
    usado_em       timestamptz,
    CONSTRAINT ck_recuperacoes_expira_apos_criacao CHECK (expira_em > criado_em)
);

CREATE INDEX IF NOT EXISTS ix_recuperacoes_senha_usuario
    ON public.recuperacoes_senha (id_usuario, criado_em DESC);

CREATE INDEX IF NOT EXISTS ix_recuperacoes_senha_ativas
    ON public.recuperacoes_senha (id_usuario, criado_em DESC)
    WHERE usado_em IS NULL;

-- Menor privilégio: a API lê, cria e só atualiza 'tentativas' e 'usado_em'.
REVOKE ALL ON public.recuperacoes_senha FROM PUBLIC;
GRANT SELECT, INSERT ON public.recuperacoes_senha TO pavimentai_app;
GRANT UPDATE (tentativas, usado_em) ON public.recuperacoes_senha TO pavimentai_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO pavimentai_app;

-- 2) Função de encerramento e anonimização de conta (LGPD)
CREATE OR REPLACE FUNCTION public.anonimizar_usuario(p_id bigint, p_hash_senha text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_papel text;
BEGIN
    SELECT papel INTO v_papel FROM public.usuarios WHERE id_usuario = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'usuario inexistente';
    END IF;
    IF v_papel <> 'cidadao' THEN
        RAISE EXCEPTION 'apenas contas de cidadao podem ser anonimizadas por aqui';
    END IF;

    UPDATE public.usuarios SET
        nome = 'Conta removida',
        email = 'anonimizado-' || id_usuario || '@anonimizado.invalid',
        telefone = 'anon' || id_usuario,
        hash_senha = p_hash_senha,
        email_verificado = false, email_verificado_em = NULL,
        telefone_verificado = false, telefone_verificado_em = NULL,
        status_conta = 'desativada',
        cep = NULL, codigo_ibge_residencia = NULL, municipio_residencia = NULL,
        uf_residencia = NULL, id_area_residencia = NULL, residencia_atualizada_em = NULL
    WHERE id_usuario = p_id;

    DELETE FROM public.verificacoes_contato WHERE id_usuario = p_id;
    DELETE FROM public.recuperacoes_senha WHERE id_usuario = p_id;
END $$;

REVOKE ALL ON FUNCTION public.anonimizar_usuario(bigint, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.anonimizar_usuario(bigint, text) TO pavimentai_app;

COMMIT;

-- 3) Conferência: deve voltar 1 linha com as duas colunas "true"
SELECT to_regclass('public.recuperacoes_senha') IS NOT NULL AS tabela_recuperacao,
       EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'anonimizar_usuario') AS funcao_anonimizar;