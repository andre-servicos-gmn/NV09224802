-- Migration: Add webhook_secret column to tenants table
-- This column stores the HMAC secret for validating webhooks from platforms

ALTER TABLE tenants 
ADD COLUMN IF NOT EXISTS webhook_secret TEXT;

COMMENT ON COLUMN tenants.webhook_secret IS 'Secret key for validating webhook signatures from e-commerce platforms (Shopify, WooCommerce, etc.)';
