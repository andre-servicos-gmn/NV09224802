#!/usr/bin/env python
"""CLI script to index the knowledge base with embeddings.

Usage:
    python scripts/index_knowledge_base.py [--validate-only] [--debug]

This script follows AGENT.md architecture:
    INTENT → STATE → STRATEGY → ACTION → RESPONSE
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description="Index knowledge base with embeddings")
    parser.add_argument("--validate-only", action="store_true", help="Only validate, don't index")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--loop", action="store_true", help="Keep running until all indexed")
    args = parser.parse_args()
    
    # Load environment
    load_dotenv()
    
    if args.debug:
        os.environ["DEBUG"] = "true"
    
    from app.graphs.kb_indexer_graph import run_kb_indexer, validate_indexer
    
    if args.validate_only:
        print("\n[Validation Mode]\n")
        result = validate_indexer()
        print(f"Total active records: {result['total_active']}")
        print(f"With embedding: {result['total_with_embedding']}")
        print(f"Pending: {result['pending']}")
        print(f"Status: {'✓ All indexed' if result['success'] else '✗ Incomplete'}")
        return 0 if result['success'] else 1
    
    # Run indexer
    if args.loop:
        print("[Loop Mode] Will run until all records are indexed\n")
        
        total_processed = 0
        iteration = 0
        
        while True:
            iteration += 1
            print(f"\n--- Iteration {iteration} ---\n")
            
            state = run_kb_indexer()
            total_processed += state.processed_count
            
            print(f"\n>>> {state.response_message}")
            
            # Check if done
            if state.last_strategy == "noop_done":
                break
            
            if state.last_strategy == "error_stop":
                print("\n[Stopping due to error]")
                break
        
        print(f"\n{'='*50}")
        print(f"Total processed: {total_processed}")
        
        # Final validation
        result = validate_indexer()
        print(f"Pending: {result['pending']}")
        print(f"Status: {'✓ Complete' if result['success'] else '✗ Incomplete'}")
        
    else:
        # Single run
        state = run_kb_indexer()
        print(f"\n>>> {state.response_message}\n")
        
        # Validation
        result = validate_indexer()
        print(f"[Validation] Active: {result['total_active']}, With embedding: {result['total_with_embedding']}, Pending: {result['pending']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
