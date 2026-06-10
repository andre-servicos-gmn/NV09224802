-- Migration 003: Personalidade por tenant
-- Adiciona campos pra customização do system prompt do supervisor (Fase 3).
-- Aplicação: rodar manualmente no Supabase SQL Editor (não há tooling
-- automático de migrations neste projeto).

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS brand_voice TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS store_policies_summary TEXT DEFAULT NULL;

COMMENT ON COLUMN tenants.brand_voice IS
'Tom e voz da marca em texto livre. Ex: "Tom direto e bem humorado, gírias paulistanas ok, evita formalidade". NULL = usa default profissional brasileiro.';

COMMENT ON COLUMN tenants.store_policies_summary IS
'Resumo curto das políticas da loja (frete grátis, troca, prazo de entrega). Usado pelo supervisor antes do KB real estar populado. NULL = supervisor responde que precisa verificar.';
