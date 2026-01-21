#!/usr/bin/env python
"""
CLI script to sync products from e-commerce platforms to RAG vector store.

Usage:
    # Sync all products for a tenant
    python scripts/sync_products.py --tenant demo
    
    # Sync with debug output
    python scripts/sync_products.py --tenant demo --debug
    
    # Sync a specific product
    python scripts/sync_products.py --tenant demo --product-id 12345678
"""

import argparse
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.tenancy import TenantRegistry
from app.sync.sync_service import SyncService


def main():
    parser = argparse.ArgumentParser(description="Sync products to RAG vector store")
    parser.add_argument("--tenant", required=True, help="Tenant ID or slug")
    parser.add_argument("--product-id", help="Sync specific product only")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    if args.debug:
        os.environ["DEBUG"] = "true"
    
    # Get tenant config
    print(f"Loading tenant: {args.tenant}")
    registry = TenantRegistry()
    
    try:
        tenant = registry.get(args.tenant)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    print(f"Tenant: {tenant.name} ({tenant.tenant_id})")
    print(f"Platform: shopify")
    print(f"Store: {tenant.store_domain}")
    print()
    
    # Initialize sync service
    sync = SyncService()
    
    credentials = {
        "store_domain": tenant.store_domain,
        "access_token": tenant.shopify_access_token,
        "api_version": tenant.shopify_api_version,
    }
    
    if args.product_id:
        # Sync single product
        print(f"Syncing product: {args.product_id}")
        result = sync.sync_single_product(
            tenant_id=tenant.uuid,
            platform="shopify",
            credentials=credentials,
            product_id=args.product_id,
        )
        
        if result:
            print(f"✓ Synced: {result.get('title', 'Unknown')}")
        else:
            print(f"✗ Product not found: {args.product_id}")
    else:
        # Full catalog sync
        print("Starting full catalog sync...")
        print("-" * 50)
        
        result = sync.sync_full_catalog(
            tenant_id=tenant.uuid,
            platform="shopify",
            credentials=credentials,
        )
        
        print("-" * 50)
        print("Sync Complete!")
        print(f"  Total products: {result['total_products']}")
        print(f"  Synced: {result['synced']}")
        print(f"  Errors: {result['errors']}")
        print(f"  Duration: {result['duration_seconds']:.1f}s")


if __name__ == "__main__":
    main()
