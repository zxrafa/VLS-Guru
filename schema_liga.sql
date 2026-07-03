-- ==============================================================================
-- SCHEMA DA LIGA VLS - CRIAÇÃO DE TABELAS E POLÍTICAS DE SEGURANÇA (RLS)
-- Cole este script no SQL Editor do seu console Supabase para configurar a base.
-- ==============================================================================

-- 1. TABELA DE CAMPEONATOS
CREATE TABLE IF NOT EXISTS public.campeonatos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome TEXT NOT NULL,
    logo_url TEXT,
    ativo BOOLEAN DEFAULT true,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. TABELA DE PARTIDAS
CREATE TABLE IF NOT EXISTS public.partidas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campeonato_id UUID REFERENCES public.campeonatos(id) ON DELETE CASCADE,
    rodada TEXT NOT NULL, -- Ex: "Rodada 1", "Quartas de Final", "Semifinal", "Final"
    time_casa TEXT NOT NULL,
    time_fora TEXT NOT NULL,
    gols_casa INTEGER,
    gols_fora INTEGER,
    encerrada BOOLEAN DEFAULT false,
    video_url TEXT, -- Link da gravação no YouTube ou Twitch
    data_jogo TIMESTAMP WITH TIME ZONE,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. TABELA DE NOTÍCIAS
CREATE TABLE IF NOT EXISTS public.noticias (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    titulo TEXT NOT NULL,
    subtitulo TEXT,
    conteudo TEXT NOT NULL,
    imagem_url TEXT,
    data_publicacao TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- ==============================================================================
-- CONFIGURAÇÕES DE SEGURANÇA MÁXIMA (OWASP / RLS POLICIES)
-- ==============================================================================

-- Ativar segurança de linha (RLS) em todas as tabelas (Impede acesso não autorizado)
ALTER TABLE public.campeonatos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partidas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.noticias ENABLE ROW LEVEL SECURITY;

-- Remover políticas antigas para evitar conflitos se rodar o script novamente
DROP POLICY IF EXISTS "Leitura publica de campeonatos" ON public.campeonatos;
DROP POLICY IF EXISTS "Escrita restrita para campeonatos" ON public.campeonatos;
DROP POLICY IF EXISTS "Leitura publica de partidas" ON public.partidas;
DROP POLICY IF EXISTS "Escrita restrita para partidas" ON public.partidas;
DROP POLICY IF EXISTS "Leitura publica de noticias" ON public.noticias;
DROP POLICY IF EXISTS "Escrita restrita para noticias" ON public.noticias;

-- POLÍTICAS: LEITURA PÚBLICA (Qualquer usuário do site ou robô pode visualizar)
CREATE POLICY "Leitura publica de campeonatos" ON public.campeonatos FOR SELECT USING (true);
CREATE POLICY "Leitura publica de partidas" ON public.partidas FOR SELECT USING (true);
CREATE POLICY "Leitura publica de noticias" ON public.noticias FOR SELECT USING (true);

-- POLÍTICAS: ESCRITA RESTRITA (Apenas o servidor do Bot com a service_role_key pode alterar)
CREATE POLICY "Escrita restrita para campeonatos" ON public.campeonatos FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Escrita restrita para partidas" ON public.partidas FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Escrita restrita para noticias" ON public.noticias FOR ALL TO service_role USING (true) WITH CHECK (true);

-- 4. TABELA DE JOGADORES DA LIGA (ESTATÍSTICAS)
CREATE TABLE IF NOT EXISTS public.jogadores_liga (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campeonato_id UUID REFERENCES public.campeonatos(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    time TEXT NOT NULL,
    gols INTEGER DEFAULT 0,
    assistencias INTEGER DEFAULT 0,
    nota_media NUMERIC(4, 2) DEFAULT 0.00,
    jogos INTEGER DEFAULT 0,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.jogadores_liga ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Leitura publica de jogadores_liga" ON public.jogadores_liga;
DROP POLICY IF EXISTS "Escrita restrita para jogadores_liga" ON public.jogadores_liga;
CREATE POLICY "Leitura publica de jogadores_liga" ON public.jogadores_liga FOR SELECT USING (true);
CREATE POLICY "Escrita restrita para jogadores_liga" ON public.jogadores_liga FOR ALL TO service_role USING (true) WITH CHECK (true);
