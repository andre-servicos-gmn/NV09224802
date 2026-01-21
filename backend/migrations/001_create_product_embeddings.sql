-- ============================================================================
-- NOUVARIS RAG: Product Embeddings Table Migration
-- ============================================================================
-- Run this in Supabase SQL Editor to create the product_embeddings table
-- This enables semantic product search using pgvector
-- ============================================================================

-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create product embeddings table
CREATE TABLE IF NOT EXISTS product_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Platform identity
    platform TEXT NOT NULL,  -- 'shopify', 'woocommerce', 'vtex', 'nuvemshop'
    external_id TEXT NOT NULL,  -- ID in the original platform
    
    -- Product data
    title TEXT NOT NULL,
    description TEXT,
    price NUMERIC(10, 2),
    currency TEXT DEFAULT 'BRL',
    tags TEXT[],
    categories TEXT[],
    product_type TEXT,
    vendor TEXT,
    
    -- Media and availability
    image_url TEXT,
    url TEXT,
    in_stock BOOLEAN DEFAULT TRUE,
    variants_count INTEGER DEFAULT 1,
    
    -- Vector embedding (1536 dimensions for OpenAI text-embedding-3-small)
    embedding vector(1536),
    
    -- Raw platform data for debugging/fallback
    raw_data JSONB,
    
    -- Sync tracking
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Unique constraint per tenant and platform product
    UNIQUE (tenant_id, platform, external_id)
);

-- Create index for vector similarity search (IVFFlat for < 100K products)
CREATE INDEX IF NOT EXISTS idx_product_embeddings_vector 
ON product_embeddings 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create index for tenant filtering (most common filter)
CREATE INDEX IF NOT EXISTS idx_product_embeddings_tenant 
ON product_embeddings (tenant_id);

-- Create index for platform filtering
CREATE INDEX IF NOT EXISTS idx_product_embeddings_platform 
ON product_embeddings (tenant_id, platform);

-- Create index for in_stock filtering
CREATE INDEX IF NOT EXISTS idx_product_embeddings_stock
ON product_embeddings (tenant_id, in_stock) WHERE in_stock = TRUE;

-- Trigger for updated_at (uses existing function if available)
DROP TRIGGER IF EXISTS update_product_embeddings_updated_at ON product_embeddings;

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_product_embeddings_updated_at
    BEFORE UPDATE ON product_embeddings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- RPC FUNCTION: Semantic Product Search
-- ============================================================================
-- Call this from Python: supabase.rpc("search_products_by_embedding", {...})

CREATE OR REPLACE FUNCTION search_products_by_embedding(
    query_embedding vector(1536),
    tenant_uuid UUID,
    match_count INT DEFAULT 10,
    only_in_stock BOOLEAN DEFAULT FALSE
)
RETURNS TABLE (
    id UUID,
    title TEXT,
    description TEXT,
    price NUMERIC,
    currency TEXT,
    image_url TEXT,
    url TEXT,
    in_stock BOOLEAN,
    platform TEXT,
    external_id TEXT,
    tags TEXT[],
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        pe.id,
        pe.title,
        pe.description,
        pe.price,
        pe.currency,
        pe.image_url,
        pe.url,
        pe.in_stock,
        pe.platform,
        pe.external_id,
        pe.tags,
        1 - (pe.embedding <=> query_embedding) AS similarity
    FROM product_embeddings pe
    WHERE pe.tenant_id = tenant_uuid
      AND (NOT only_in_stock OR pe.in_stock = TRUE)
    ORDER BY pe.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ============================================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================================
-- Ensures tenants can only access their own products

ALTER TABLE product_embeddings ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if any
DROP POLICY IF EXISTS tenant_isolation_select ON product_embeddings;
DROP POLICY IF EXISTS tenant_isolation_insert ON product_embeddings;
DROP POLICY IF EXISTS tenant_isolation_update ON product_embeddings;
DROP POLICY IF EXISTS tenant_isolation_delete ON product_embeddings;

-- Service role can do everything (for backend sync jobs)
CREATE POLICY service_role_all ON product_embeddings
    FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================================
-- VERIFICATION
-- ============================================================================
-- Run these to verify the migration worked:

-- SELECT COUNT(*) FROM product_embeddings;
-- SELECT * FROM product_embeddings LIMIT 1;

-- Test vector search (after inserting data):
-- SELECT * FROM search_products_by_embedding(
--     '[0.1, 0.2, ...]'::vector(1536),  -- query embedding
--     'your-tenant-uuid',
--     5,  -- limit
--     FALSE  -- only_in_stock
-- );
