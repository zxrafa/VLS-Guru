-- ==========================================
-- SCHEMA SQL PARA CONFIGURAR O SUPABASE
-- Cole este script no SQL Editor do Supabase
-- ==========================================

-- 1. Cria a tabela principal de documentos (jogadores, perfis, coleções, etc.)
CREATE TABLE IF NOT EXISTS jogadores (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL
);

-- 2. Desabilita a segurança RLS para permitir leitura e escrita livre com a anon key
ALTER TABLE jogadores DISABLE ROW LEVEL SECURITY;

-- 3. Opcional: Cria um índice para acelerar buscas por ID e prefixos
CREATE INDEX IF NOT EXISTS idx_jogadores_id ON jogadores (id);
