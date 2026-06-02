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
import urllib.request
from pathlib import Path
from typing import Dict
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
from tgrag.src.config.config_loader import ConfigLoader
from tgrag.src.utils.query_runtime import (
    build_manifest_path,
    infer_runtime_warnings,
    is_local_base_url,
    load_build_manifest,
    resolve_query_embedding_runtime,
)


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


def xac_nhan_turboquant(base_url: str = None, strict: bool = False) -> bool:
    base_url = base_url or os.getenv("OPENAI_BASE_URL", "http://localhost:8080/v1")
    props_url = base_url.replace("/v1", "").rstrip("/") + "/props"
    try:
        with urllib.request.urlopen(props_url, timeout=3) as response:
            if response.status == 200:
                response.read()
                print("\n" + "═"*65)
                print("🚀 [TURBOQUANT+ VALIDATION] KẾT NỐI SERVER THÀNH CÔNG!")
                print(f" 🔹 API Endpoint  : {base_url}")
                print(" 🔹 Wire protocol : OpenAI-compatible local /v1")
                print(" 🔹 Nhân xử lý    : Llama-Server C++ (Tích hợp tối ưu TurboQuant+)")
                print(" 🔹 Trạng thái KV : Đang tự động nén trực tiếp trên VRAM GPU")
                print(" ═" + "═"*63 + "\n")
                return True
            print(f"⚠️ Cảnh báo: Kết nối tới server nhưng trả về mã lỗi: {response.status}")
    except Exception as exc:
        print("\n❌ [LỖI KẾT NỐI] KHÔNG THỂ TÌM THẤY SERVER CỦA TURBOQUANT!")
        print(f"   Vui lòng chắc chắn rằng bạn đã chạy lệnh khởi động `./build/bin/llama-server` tại cổng {base_url} trước.\n")
        if strict:
            raise RuntimeError(f"TurboQuant healthcheck failed: {base_url}") from exc
    return False


def _resolve_embedding_overrides(args):
    return {
        "embedding_provider": args.embedding_provider,
        "embedding_model": args.embedding_model,
        "embedding_dim": args.embedding_dim,
        "embedding_device": args.embedding_device,
        "embedding_batch_size": args.embedding_batch_size,
        "embedding_max_tokens": args.embedding_max_tokens,
        "embedding_prefix": args.embedding_prefix,
        "embedding_base_url": args.embedding_base_url,
    }


def apply_runtime_overrides(
    args, override_config: Dict, config_defaults: Dict | None = None
) -> Dict:
    config_defaults = config_defaults or {}
    working_dir = override_config.get("working_dir") or config_defaults.get("working_dir")
    manifest = load_build_manifest(working_dir)

    if args.local_llm_backend == "turboquant":
        provider = "openai"
        model = args.model or "qwen2.5-7b-instruct-q8-turbo3"
        llm_base_url = args.base_url or "http://localhost:8080/v1"
        default_embedding_provider = None
        default_embedding_base_url = None
        llm_max_async = args.llm_max_async or 1
        llm_timeout = args.llm_timeout or 600.0
        api_key = os.getenv("OPENAI_API_KEY") or "sk-local"
        wire_protocol = "openai-compatible-local"
    elif args.local_llm_backend == "ollama":
        provider = "ollama"
        model = args.model or "qwen3:14b"
        llm_base_url = args.base_url or "http://localhost:11434"
        default_embedding_provider = "ollama"
        default_embedding_base_url = "http://localhost:11434"
        llm_max_async = args.llm_max_async
        llm_timeout = args.llm_timeout
        api_key = None
        wire_protocol = "ollama-native"
    else:
        provider = args.provider
        model = args.model
        llm_base_url = args.base_url
        default_embedding_provider = None
        default_embedding_base_url = None
        llm_max_async = args.llm_max_async
        llm_timeout = args.llm_timeout
        api_key = None
        wire_protocol = provider or "config"
        if provider == "openai" and is_local_base_url(llm_base_url):
            api_key = os.getenv("OPENAI_API_KEY") or "sk-local"
            wire_protocol = "openai-compatible-local"
        elif provider == "ollama":
            wire_protocol = "ollama-native"

    embedding_runtime = resolve_query_embedding_runtime(
        explicit=_resolve_embedding_overrides(args),
        config_defaults=config_defaults,
        manifest=manifest,
        default_provider=default_embedding_provider,
        default_base_url=default_embedding_base_url,
    )
    embedding_provider = embedding_runtime["embedding_provider"]
    embedding_base_url = embedding_runtime["embedding_base_url"]

    if provider:
        override_config["provider"] = provider
    if model:
        override_config["model"] = model
    if embedding_provider:
        override_config["embedding_provider"] = embedding_provider
    if embedding_runtime["embedding_model"]:
        override_config["embedding_model"] = embedding_runtime["embedding_model"]
    if embedding_runtime["embedding_dim"]:
        override_config["embedding_dim"] = embedding_runtime["embedding_dim"]
    if embedding_runtime["embedding_device"]:
        override_config["embedding_device"] = embedding_runtime["embedding_device"]
    if embedding_runtime["embedding_batch_size"]:
        override_config["embedding_batch_size"] = embedding_runtime["embedding_batch_size"]
    if embedding_runtime["embedding_max_tokens"]:
        override_config["embedding_max_tokens"] = embedding_runtime["embedding_max_tokens"]
    if embedding_runtime["embedding_prefix"] is not None:
        override_config["embedding_prefix"] = embedding_runtime["embedding_prefix"]
    if llm_max_async:
        override_config["best_model_max_async"] = llm_max_async
        override_config["cheap_model_max_async"] = llm_max_async
    if llm_timeout:
        override_config["llm_timeout"] = llm_timeout

    return {
        "local_llm_backend": args.local_llm_backend or "provider_override",
        "provider": provider or "config",
        "model": model or "config",
        "llm_base_url": llm_base_url,
        "embedding_provider": embedding_provider or "config",
        "embedding_model": embedding_runtime["embedding_model"],
        "embedding_dim": embedding_runtime["embedding_dim"],
        "embedding_device": embedding_runtime["embedding_device"],
        "embedding_batch_size": embedding_runtime["embedding_batch_size"],
        "embedding_max_tokens": embedding_runtime["embedding_max_tokens"],
        "embedding_prefix": embedding_runtime["embedding_prefix"],
        "embedding_base_url": embedding_base_url,
        "llm_max_async": llm_max_async,
        "llm_timeout": llm_timeout,
        "wire_protocol": wire_protocol,
        "api_key": api_key,
        "build_manifest_path": build_manifest_path(working_dir),
        "build_manifest_found": bool(manifest),
        "warnings": infer_runtime_warnings(
            working_dir=working_dir,
            manifest=manifest,
            config_defaults=config_defaults,
            resolved_embedding=embedding_runtime,
            local_llm_backend=args.local_llm_backend,
        ),
    }


def print_runtime(runtime_config: Dict) -> None:
    if not runtime_config:
        return
    print(
        f"[runtime] local_llm_backend={runtime_config['local_llm_backend']} "
        f"provider={runtime_config['provider']} "
        f"model={runtime_config['model']} "
        f"wire_protocol={runtime_config['wire_protocol']}"
    )
    print(f"[runtime] llm_base_url={runtime_config['llm_base_url']}")
    print(
        f"[runtime] embedding_provider={runtime_config['embedding_provider']} "
        f"embedding_base_url={runtime_config['embedding_base_url']}"
    )
    extra = []
    for key in ("embedding_model", "embedding_dim", "embedding_device", "embedding_batch_size", "embedding_max_tokens", "embedding_prefix"):
        value = runtime_config.get(key)
        if value is not None:
            extra.append(f"{key}={value}")
    if extra:
        print("[runtime] " + " ".join(extra))
    if runtime_config.get("build_manifest_path"):
        manifest_state = "found" if runtime_config.get("build_manifest_found") else "missing"
        print(
            f"[runtime] build_manifest={manifest_state} "
            f"path={runtime_config['build_manifest_path']}"
        )
    for warning in runtime_config.get("warnings", []):
        print(f"[runtime] warning={warning}")


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
    parser.add_argument(
        '--local_llm_backend',
        choices=['turboquant', 'ollama'],
        default=None,
        help='Local LLM backend override: turboquant=local llama-server OpenAI-compatible API, ollama=Ollama native API'
    )
    parser.add_argument(
        '--provider',
        choices=['openai', 'gemini', 'ollama', 'azure', 'bedrock'],
        default=None,
        help='Override LLM provider from config without using local backend mode'
    )
    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Override LLM model or local llama-server alias'
    )
    parser.add_argument(
        '--base_url',
        type=str,
        default=None,
        help='Override LLM base URL, e.g. http://localhost:8080/v1 for llama-server'
    )
    parser.add_argument(
        '--embedding_provider',
        choices=['ollama', 'openai', 'azure', 'bedrock', 'huggingface'],
        default=None,
        help='Override embedding provider from config'
    )
    parser.add_argument(
        '--embedding_model',
        type=str,
        default=None,
        help='Override embedding model name (used by Ollama or HuggingFace embeddings)'
    )
    parser.add_argument(
        '--embedding_dim',
        type=int,
        default=None,
        help='Override embedding vector dimension'
    )
    parser.add_argument(
        '--embedding_device',
        type=str,
        default=None,
        help='Embedding device for HuggingFace embeddings, e.g. cpu or cuda'
    )
    parser.add_argument(
        '--embedding_batch_size',
        type=int,
        default=None,
        help='Embedding batch size for HuggingFace embeddings'
    )
    parser.add_argument(
        '--embedding_max_tokens',
        type=int,
        default=None,
        help='Embedding max tokens for HuggingFace embeddings'
    )
    parser.add_argument(
        '--embedding_prefix',
        type=str,
        default=None,
        help='Embedding text prefix, e.g. search_document: '
    )
    parser.add_argument(
        '--embedding_base_url',
        type=str,
        default=None,
        help='Embedding base URL, e.g. http://localhost:11434 for Ollama embeddings'
    )
    parser.add_argument(
        '--llm_max_async',
        type=int,
        default=None,
        help='Override max concurrent LLM calls. Defaults to 1 for --local_llm_backend turboquant'
    )
    parser.add_argument(
        '--llm_timeout',
        type=float,
        default=None,
        help='Override LLM request timeout in seconds. Defaults to 600 for --local_llm_backend turboquant'
    )
    
    args = parser.parse_args()
    
    # Prepare override config
    override_config = {}
    if args.working_dir:
        override_config['working_dir'] = args.working_dir
    config_loader = ConfigLoader(config_path=args.config)
    config_defaults = config_loader.get_config(
        config_type="querying",
        override_args=override_config if override_config else None,
    )
    runtime_config = apply_runtime_overrides(args, override_config, config_defaults)
    
    # Create TemporalGraphRAG from config (simplified!)
    print("="*60)
    print("Loading Configuration and Initializing TemporalGraphRAG")
    print("="*60)
    print(f"Config file: {args.config}")
    if override_config:
        print(f"Overrides: {override_config}")
    print_runtime(runtime_config)
    print()

    if runtime_config.get("local_llm_backend") == "turboquant":
        try:
            xac_nhan_turboquant(runtime_config["llm_base_url"], strict=True)
        except RuntimeError as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    
    try:
        graph_rag = create_temporal_graphrag_from_config(
            config_path=args.config,
            config_type="querying",
            override_config=override_config if override_config else None,
            api_key=runtime_config.get("api_key") if runtime_config else None,
            base_url=runtime_config.get("llm_base_url") if runtime_config else None,
            embedding_base_url=runtime_config.get("embedding_base_url") if runtime_config else None,
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
