-- ============================================================
-- SISTEMA FINANCEIRO — Schema SQL para Supabase
-- Execute no SQL Editor do seu projeto Supabase
-- ============================================================

-- Habilita extensão para geração de UUIDs
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- TABELA: categorias
-- ============================================================
CREATE TABLE IF NOT EXISTS public.categorias (
    id          SERIAL PRIMARY KEY,
    nome        TEXT NOT NULL,
    tipo        TEXT NOT NULL DEFAULT 'ambos'
                CHECK (tipo IN ('despesa', 'receita', 'ambos')),
    escopo      TEXT NOT NULL DEFAULT 'ambos'
                CHECK (escopo IN ('pessoal', 'familiar', 'ambos')),
    icone       TEXT NOT NULL DEFAULT 'tag',
    cor         TEXT NOT NULL DEFAULT '#6366f1',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT categorias_nome_unique UNIQUE (nome)
);

-- ============================================================
-- TABELA: emprestimos
-- ============================================================
CREATE TABLE IF NOT EXISTS public.emprestimos (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    descricao        TEXT NOT NULL,
    valor_total      NUMERIC(12,2) NOT NULL CHECK (valor_total > 0),
    taxa_juros       NUMERIC(8,6) NOT NULL DEFAULT 0.0
                    CHECK (taxa_juros >= 0),
    total_parcelas   INTEGER NOT NULL CHECK (total_parcelas > 0),
    valor_parcela    NUMERIC(12,2) NOT NULL CHECK (valor_parcela > 0),
    data_inicio      DATE NOT NULL,
    recorrencia_dia  INTEGER NOT NULL DEFAULT 1
                    CHECK (recorrencia_dia BETWEEN 1 AND 28),
    escopo           TEXT NOT NULL CHECK (escopo IN ('pessoal', 'familiar')),
    categoria_id     INTEGER REFERENCES public.categorias(id)
                    ON DELETE SET NULL ON UPDATE CASCADE,
    status           TEXT NOT NULL DEFAULT 'ativo'
                    CHECK (status IN ('ativo', 'quitado', 'cancelado')),
    observacoes      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABELA: parcelas
-- ============================================================
CREATE TABLE IF NOT EXISTS public.parcelas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    emprestimo_id    UUID NOT NULL
                    REFERENCES public.emprestimos(id)
                    ON DELETE CASCADE ON UPDATE CASCADE,
    numero_parcela   INTEGER NOT NULL CHECK (numero_parcela > 0),
    valor            NUMERIC(12,2) NOT NULL CHECK (valor > 0),
    data_vencimento  DATE NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pendente'
                    CHECK (status IN ('pendente', 'paga', 'atrasada')),
    data_pagamento   DATE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT parcelas_emprestimo_numero_unique
        UNIQUE (emprestimo_id, numero_parcela)
);

-- ============================================================
-- TABELA: transacoes
-- ============================================================
CREATE TABLE IF NOT EXISTS public.transacoes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    descricao    TEXT NOT NULL,
    valor        NUMERIC(12,2) NOT NULL CHECK (valor > 0),
    tipo         TEXT NOT NULL CHECK (tipo IN ('entrada', 'saida')),
    escopo       TEXT NOT NULL CHECK (escopo IN ('pessoal', 'familiar')),
    categoria_id INTEGER REFERENCES public.categorias(id)
                ON DELETE SET NULL ON UPDATE CASCADE,
    data         DATE NOT NULL,
    observacoes  TEXT,
    parcela_id   UUID REFERENCES public.parcelas(id)
                ON DELETE SET NULL ON UPDATE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- ÍNDICES DE PERFORMANCE
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_transacoes_escopo_data
    ON public.transacoes (escopo, data DESC);

CREATE INDEX IF NOT EXISTS idx_transacoes_tipo_data
    ON public.transacoes (tipo, data DESC);

CREATE INDEX IF NOT EXISTS idx_transacoes_categoria
    ON public.transacoes (categoria_id);

CREATE INDEX IF NOT EXISTS idx_transacoes_parcela
    ON public.transacoes (parcela_id);

CREATE INDEX IF NOT EXISTS idx_parcelas_emprestimo
    ON public.parcelas (emprestimo_id);

CREATE INDEX IF NOT EXISTS idx_parcelas_vencimento_status
    ON public.parcelas (data_vencimento, status);

CREATE INDEX IF NOT EXISTS idx_emprestimos_escopo_status
    ON public.emprestimos (escopo, status);

-- ============================================================
-- FUNÇÃO: Gerar parcelas automaticamente (amortização linear)
-- ============================================================
CREATE OR REPLACE FUNCTION public.fn_gerar_parcelas()
RETURNS TRIGGER AS $$
DECLARE
    i INTEGER;
    dt_vencimento DATE;
BEGIN
    FOR i IN 1..NEW.total_parcelas LOOP
        dt_vencimento := (
            DATE_TRUNC('month', NEW.data_inicio) +
            ((i - 1) || ' months')::INTERVAL +
            ((NEW.recorrencia_dia - 1) || ' days')::INTERVAL
        )::DATE;

        INSERT INTO public.parcelas (
            emprestimo_id,
            numero_parcela,
            valor,
            data_vencimento,
            status
        ) VALUES (
            NEW.id,
            i,
            NEW.valor_parcela,
            dt_vencimento,
            'pendente'
        );
    END LOOP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_gerar_parcelas ON public.emprestimos;
CREATE TRIGGER trg_gerar_parcelas
    AFTER INSERT ON public.emprestimos
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_gerar_parcelas();

-- ============================================================
-- FUNÇÃO: Atualizar status de parcelas vencidas (pode ser agendada)
-- ============================================================
CREATE OR REPLACE FUNCTION public.fn_atualizar_parcelas_atrasadas()
RETURNS INTEGER AS $$
DECLARE
    qtd INTEGER;
BEGIN
    UPDATE public.parcelas
    SET status = 'atrasada'
    WHERE status = 'pendente'
      AND data_vencimento < CURRENT_DATE;

    GET DIAGNOSTICS qtd = ROW_COUNT;
    RETURN qtd;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNÇÃO: Resumo financeiro mensal por escopo
-- ============================================================
CREATE OR REPLACE FUNCTION public.fn_resumo_mensal(
    p_escopo TEXT,
    p_ano    INTEGER,
    p_mes    INTEGER
)
RETURNS TABLE (
    total_entradas NUMERIC,
    total_saidas   NUMERIC,
    saldo          NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN valor ELSE 0 END), 0) AS total_entradas,
        COALESCE(SUM(CASE WHEN tipo = 'saida'   THEN valor ELSE 0 END), 0) AS total_saidas,
        COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN valor ELSE -valor END), 0) AS saldo
    FROM public.transacoes
    WHERE (p_escopo = 'consolidado' OR escopo = p_escopo)
      AND EXTRACT(YEAR  FROM data) = p_ano
      AND EXTRACT(MONTH FROM data) = p_mes;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- SEED: Categorias padrão
-- ============================================================
INSERT INTO public.categorias (nome, tipo, escopo, icone, cor) VALUES
    ('Salário',           'receita', 'ambos',     'briefcase',   '#22c55e'),
    ('Freelance',         'receita', 'pessoal',   'laptop',      '#10b981'),
    ('Investimentos',     'receita', 'ambos',     'trending-up', '#06b6d4'),
    ('Pensão/Benefício',  'receita', 'ambos',     'heart',       '#84cc16'),
    ('Outros Ingressos',  'receita', 'ambos',     'plus-circle', '#a3e635'),
    ('Moradia',           'despesa', 'familiar',  'home',        '#f59e0b'),
    ('Alimentação',       'despesa', 'familiar',  'shopping-cart','#f97316'),
    ('Saúde',             'despesa', 'familiar',  'heart-pulse',  '#ef4444'),
    ('Educação',          'despesa', 'familiar',  'book-open',   '#8b5cf6'),
    ('Transporte',        'despesa', 'ambos',     'car',         '#3b82f6'),
    ('Lazer Família',     'despesa', 'familiar',  'users',       '#ec4899'),
    ('Serviços',          'despesa', 'familiar',  'wrench',      '#6366f1'),
    ('Vestuário',         'despesa', 'ambos',     'shirt',       '#14b8a6'),
    ('Lazer Pessoal',     'despesa', 'pessoal',   'smile',       '#a855f7'),
    ('Estudos',           'despesa', 'pessoal',   'graduation-cap','#7c3aed'),
    ('Assinaturas',       'despesa', 'pessoal',   'repeat',      '#0ea5e9'),
    ('Cuidados Pessoais', 'despesa', 'pessoal',   'sparkles',    '#f43f5e'),
    ('Academia',          'despesa', 'pessoal',   'dumbbell',    '#fb923c'),
    ('Pets',              'despesa', 'pessoal',   'dog',         '#fbbf24'),
    ('Financiamento',     'despesa', 'ambos',     'landmark',    '#64748b'),
    ('Empréstimo',        'despesa', 'ambos',     'hand-coins',  '#78716c'),
    ('Outros',            'ambos',   'ambos',     'tag',         '#94a3b8')
ON CONFLICT (nome) DO NOTHING;
