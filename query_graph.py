#!/usr/bin/env python3
"""
Query Temporal GraphRAG knowledge graph.

This script:
1. Loads configuration from tgrag/configs/config.yaml
2. Creates TemporalGraphRAG from config (uses tgrag.create_temporal_graphrag_from_config)
3. Loads the graph from the working directory
4. Queries the graph with a question
5. Displays the response

Usage:
    # Set API keys (provider-specific)
    export OPENAI_API_KEY="your-key-here"      # For OpenAI provider
    export GEMINI_API_KEY="your-key-here"      # For Gemini provider
    # etc.
    
    # Query with a question
    python query_graph.py --question "What happened in Q1 2020?"
    
    # Specify working directory (overrides config)
    python query_graph.py --question "What happened in Q1 2020?" --working_dir ./graph_output
    
    # Use custom config
    python query_graph.py --question "What happened?" --config ./my_config.yaml
"""

import os
import sys
import argparse
import logging
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Configure logging - default to ERROR to reduce noise, but allow DEBUG via environment variable
debug_mode = os.getenv("TG_RAG_DEBUG", "false").lower() == "true"
log_level = logging.DEBUG if debug_mode else logging.ERROR

logging.basicConfig(
    level=log_level,
    format='%(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

if debug_mode:
    print("🔍 Debug mode enabled - verbose logging active")

# Load environment variables from .env file if present (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import from tgrag package (simplified API)
from tgrag import create_temporal_graphrag_from_config


def format_seconds(seconds: float) -> str:
    """Format elapsed seconds for human-readable progress logs."""
    return f"{seconds:.2f}s"


class PhaseTimer:
    """Small wall-clock timer for script-level query phases."""

    def __init__(self) -> None:
        self.total_start = time.perf_counter()
        self.phase_start = self.total_start

    def mark(self, label: str) -> None:
        now = time.perf_counter()
        phase_elapsed = now - self.phase_start
        total_elapsed = now - self.total_start
        print(
            f"[timer] {label}: {format_seconds(phase_elapsed)} "
            f"(total {format_seconds(total_elapsed)})"
        )
        self.phase_start = now

    def total(self) -> float:
        return time.perf_counter() - self.total_start


def main():
    """Main function to query the graph."""
    timer = PhaseTimer()
    parser = argparse.ArgumentParser(
        description="Query Temporal GraphRAG knowledge graph using config.yaml",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--config',
        type=str,
        default='tgrag/configs/config.yaml',
        help='Path to configuration file (default: tgrag/configs/config.yaml)'
    )
    parser.add_argument(
        '--working_dir',
        type=str,
        default=None,
        help='Working directory where graph is stored (overrides config.working_dir if set)'
    )
    parser.add_argument(
        '--question',
        type=str,
        required=True,
        help='Question to ask the graph'
    )
    parser.add_argument(
        '--mode',
        type=str,
        choices=['local', 'global', 'naive'],
        default=None,
        help='Query mode: local, global, or naive (overrides config if specified)'
    )
    parser.add_argument(
        '--show_retrieval',
        action='store_true',
        help='Print retrieval details when local mode returns them'
    )
    
    args = parser.parse_args()
    
    # Prepare override config
    override_config = {}
    if args.working_dir:
        override_config['working_dir'] = args.working_dir
    
    # Create TemporalGraphRAG from config (simplified!)
    print("="*60)
    print("Loading Configuration and Initializing TemporalGraphRAG")
    print("="*60)
    print(f"Config file: {args.config}")
    if override_config:
        print(f"Overrides: {override_config}")
    print()
    
    try:
        graph_rag = create_temporal_graphrag_from_config(
            config_path=args.config,
            config_type="querying",
            override_config=override_config if override_config else None
        )
        print("✅ TemporalGraphRAG initialized from config")
        print(f"   Working directory: {graph_rag.working_dir}")
        
        # Verify working directory exists
        working_dir_path = Path(graph_rag.working_dir)
        if not working_dir_path.exists():
            print(f"\n❌ Error: Working directory does not exist: {graph_rag.working_dir}")
            print("   Please make sure you've built the graph first using build_graph.py")
            sys.exit(1)
        timer.mark("initialize TemporalGraphRAG")
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error initializing TemporalGraphRAG: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Get query parameters from config or command line
    from tgrag.src.core.types import QueryParam
    from tgrag.src.config.config_loader import ConfigLoader
    
    config_loader = ConfigLoader(config_path=args.config)
    raw_config = config_loader.get_config(config_type="querying", override_args=override_config if override_config else None)
    
    # Get query mode (command line override takes precedence)
    query_mode = args.mode or raw_config.get('mode', 'global')
    
    # Get token limits from config (use defaults if not specified)
    local_max_token_for_text_unit = raw_config.get('local_max_token_for_text_unit', 4000)
    local_max_token_for_local_context = raw_config.get('local_max_token_for_local_context', 6000)
    local_max_token_for_community_report = raw_config.get('local_max_token_for_community_report', 2000)
    global_max_token_for_community_report = raw_config.get('global_max_token_for_community_report', 16384)
    naive_max_token_for_text_unit = raw_config.get('naive_max_token_for_text_unit', 12000)
    top_k = raw_config.get('top_k', 20)
    enable_subgraph = raw_config.get('enable_subgraph', False)
    enable_mixed_relationship = raw_config.get('enable_mixed_relationship', False)
    seed_node_method = raw_config.get('seed_node_method', 'entities')
    
    # Create QueryParam with all settings
    query_param = QueryParam(
        mode=query_mode,
        top_k=top_k,
        seed_node_method=seed_node_method,
        local_max_token_for_text_unit=local_max_token_for_text_unit,
        local_max_token_for_local_context=local_max_token_for_local_context,
        local_max_token_for_community_report=local_max_token_for_community_report,
        global_max_token_for_community_report=global_max_token_for_community_report,
        naive_max_token_for_text_unit=naive_max_token_for_text_unit,
        sub_graph=enable_subgraph,
        mix_relation=enable_mixed_relationship,
    )
    timer.mark("load query parameters")
    
    # Query the graph
    print("\n" + "="*60)
    print("Querying Graph")
    print("="*60)
    print(f"Question: {args.question}")
    print(f"Mode: {query_mode}")
    print()
    print("Processing query... This may take a moment.")
    print()
    
    try:
        print("[timer] query started")
        response = graph_rag.query(args.question, param=query_param)
        timer.mark("run query")
        retrieval_detail = None
        if isinstance(response, tuple) and len(response) == 2:
            response, retrieval_detail = response
        print("="*60)
        print("RESPONSE")
        print("="*60)
        print(response)
        if args.show_retrieval and retrieval_detail is not None:
            print("="*60)
            print("RETRIEVAL DETAIL")
            print("="*60)
            print(json.dumps(retrieval_detail, indent=2, ensure_ascii=False, default=str))
        print("="*60)
        print(f"[timer] total: {format_seconds(timer.total())}")
    except Exception as e:
        print(f"\n❌ Error during query: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Clean up HTTP clients to avoid unclosed session warnings
        try:
            from tgrag.src.llm.client import get_client_manager
            import asyncio
            client_manager = get_client_manager()
            # Create event loop if needed and close clients
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, schedule cleanup
                    asyncio.create_task(client_manager.close_clients())
                else:
                    # If loop is not running, run cleanup
                    loop.run_until_complete(client_manager.close_clients())
            except RuntimeError:
                # No event loop, create one temporarily
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(client_manager.close_clients())
                loop.close()
        except Exception:
            # Ignore cleanup errors
            pass


if __name__ == "__main__":
    main()
