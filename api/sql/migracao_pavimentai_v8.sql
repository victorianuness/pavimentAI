-- =====================================================================
-- PavimentAI - migração v8 (catálogo dinâmico de tipos de ocorrência)
-- =====================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS public.tipos_ocorrencia (
    id_tipo       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo        varchar(20) NOT NULL UNIQUE CHECK (codigo ~ '^[a-z][a-z0-9_]{1,19}$'),
    nome          varchar(60) NOT NULL,
    usa_ia        boolean NOT NULL DEFAULT false,
    usa_gravidade boolean NOT NULL DEFAULT false,
    categorias    text[]  NOT NULL DEFAULT '{}',
    ativo         boolean NOT NULL DEFAULT true,
    ordem         integer NOT NULL DEFAULT 100,
    criado_em     timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.tipos_ocorrencia (codigo, nome, usa_ia, usa_gravidade, categorias, ordem) VALUES
    ('buraco', 'Buraco na via', true, true, '{}', 10),
    ('acessibilidade', 'Acessibilidade', false, false,
     ARRAY['calcada_danificada','ausencia_rampa','piso_tatil','travessia','obstaculo','outro'], 20)
ON CONFLICT (codigo) DO NOTHING;

-- Sai a lista fixa de tipos; entra a chave estrangeira para o catálogo
ALTER TABLE public.ocorrencias DROP CONSTRAINT IF EXISTS ocorrencias_tipo_check;
ALTER TABLE public.ocorrencias DROP CONSTRAINT IF EXISTS ck_categoria_tipo;
ALTER TABLE public.ocorrencias DROP CONSTRAINT IF EXISTS ck_gravidade_apenas_buraco;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ocorrencias_tipo') THEN
        ALTER TABLE public.ocorrencias ADD CONSTRAINT fk_ocorrencias_tipo
            FOREIGN KEY (tipo) REFERENCES public.tipos_ocorrencia (codigo);
    END IF;
END $$;

-- As mesmas regras das três CHECKs antigas, agora lendo o catálogo
CREATE OR REPLACE FUNCTION public.fn_validar_tipo_ocorrencia() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    t public.tipos_ocorrencia%ROWTYPE;
BEGIN
    SELECT * INTO t FROM public.tipos_ocorrencia WHERE codigo = NEW.tipo;
    IF cardinality(t.categorias) > 0 THEN
        IF NEW.categoria IS NULL OR NOT (NEW.categoria = ANY (t.categorias)) THEN
            RAISE EXCEPTION 'categoria invalida para o tipo %', NEW.tipo
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.categoria IS NOT NULL THEN
        RAISE EXCEPTION 'o tipo % nao tem categoria', NEW.tipo
            USING ERRCODE = 'check_violation';
    END IF;
    IF NOT t.usa_gravidade
       AND (NEW.gravidade_cidadao IS NOT NULL OR NEW.gravidade_verificada IS NOT NULL) THEN
        RAISE EXCEPTION 'gravidade nao se aplica ao tipo %', NEW.tipo
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_validar_tipo_ocorrencia ON public.ocorrencias;
CREATE TRIGGER trg_validar_tipo_ocorrencia
    BEFORE INSERT OR UPDATE OF tipo, categoria, gravidade_cidadao, gravidade_verificada
    ON public.ocorrencias
    FOR EACH ROW EXECUTE FUNCTION public.fn_validar_tipo_ocorrencia();

REVOKE ALL ON public.tipos_ocorrencia FROM PUBLIC;
GRANT SELECT ON public.tipos_ocorrencia TO pavimentai_app;

-- Concede permissões ao pavimentai_admin caso o papel já tenha sido criado
DO $$
DECLARE
    v_seq text;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pavimentai_admin') THEN
        GRANT SELECT, INSERT ON public.tipos_ocorrencia TO pavimentai_admin;
        GRANT UPDATE (nome, ativo, ordem, categorias) ON public.tipos_ocorrencia TO pavimentai_admin;
        v_seq := pg_get_serial_sequence('public.tipos_ocorrencia', 'id_tipo');
        IF v_seq IS NOT NULL THEN
            EXECUTE format('GRANT USAGE ON SEQUENCE %s TO pavimentai_admin', v_seq);
        END IF;
    END IF;
END $$;

COMMIT;