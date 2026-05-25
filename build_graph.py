#!/usr/bin/env python3
"""
Build Temporal GraphRAG knowledge graph from documents.

This script:
1. Loads documents from various sources (ECT-QA corpus, text files, or directories)
2. Creates TemporalGraphRAG from config.yaml (uses tgrag.create_temporal_graphrag_from_config)
3. Builds the temporal knowledge graph
4. Saves everything to the output directory

Usage:
    # Set API keys (provider-specific)
    export OPENAI_API_KEY="your-key-here"      # For OpenAI provider
    export GEMINI_API_KEY="your-key-here"      # For Gemini provider
    # etc.
    
    # Run with default config (from tgrag/configs/config.yaml)
    python build_graph.py --output_dir ./graph_output --num_docs 3
    
    # Build from a single text file
    python build_graph.py --output_dir ./graph_output --corpus_path ./my_document.txt
    
    # Build from a directory of text files
    python build_graph.py --output_dir ./graph_output --corpus_path ./my_documents/
    
    # Override config values
    python build_graph.py --output_dir ./graph_output --num_docs 3 --chunk_size 1000
"""

import os
import sys
import json
import gzip
import argparse
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import urllib.request


def xac_nhan_turboquant(base_url: str = None, strict: bool = False) -> bool:
    # Lấy thông tin URL từ file .env hoặc CLI runtime
    base_url = base_url or os.getenv("OPENAI_BASE_URL", "http://localhost:8080/v1")
    
    # Chuyển đổi sang endpoint kiểm tra thuộc tính của llama-server
    props_url = base_url.replace("/v1", "").rstrip("/") + "/props"
    
    try:
        # Gửi request kiểm tra tới server
        with urllib.request.urlopen(props_url, timeout=3) as response:
            if response.status == 200:
                response.read()
                
                print("\n" + "═"*65)
                print("🚀 [TURBOQUANT+ VALIDATION] KẾT NỐI SERVER THÀNH CÔNG!")
                print(f" 🔹 API Endpoint  : {base_url}")
                print(" 🔹 Wire protocol : OpenAI-compatible local /v1")
                print(f" 🔹 Nhân xử lý    : Llama-Server C++ (Tích hợp tối ưu TurboQuant+)")
                print(" 🔹 Trạng thái KV : Đang tự động nén trực tiếp trên VRAM GPU")
                print(" ═" + "═"*63 + "\n")
                return True
            else:
                print(f"⚠️ Cảnh báo: Kết nối tới server nhưng trả về mã lỗi: {response.status}")
    except Exception as exc:
        print("\n❌ [LỖI KẾT NỐI] KHÔNG THỂ TÌM THẤY SERVER CỦA TURBOQUANT!")
        print(f"   Vui lòng chắc chắn rằng bạn đã chạy lệnh khởi động `./build/bin/llama-server` tại cổng {base_url} trước.\n")
        if strict:
            raise RuntimeError(f"TurboQuant healthcheck failed: {base_url}") from exc
    return False

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

# Load environment variables from .env file if present
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import from tgrag package (simplified API)
from tgrag import create_temporal_graphrag_from_config


def format_seconds(seconds: float) -> str:
    """Format elapsed seconds for human-readable progress logs."""
    return f"{seconds:.2f}s"


class PhaseTimer:
    """Small wall-clock timer for script-level build phases."""

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


def _is_local_base_url(base_url: str) -> bool:
    return bool(base_url) and ("localhost" in base_url or "127.0.0.1" in base_url)


def apply_runtime_overrides(args, override_config: Dict) -> Dict:
    """Apply CLI runtime overrides without mutating config files."""
    if args.local_llm_backend == "turboquant":
        provider = "openai"
        model = args.model or "qwen2.5-7b-instruct-q8-turbo3"
        llm_base_url = args.base_url or "http://localhost:8080/v1"
        embedding_provider = args.embedding_provider or "ollama"
        embedding_base_url = args.embedding_base_url or "http://localhost:11434"
        llm_max_async = args.llm_max_async or 1
        llm_timeout = args.llm_timeout or 600.0
        api_key = os.getenv("OPENAI_API_KEY") or "sk-local"
        wire_protocol = "openai-compatible-local"
    elif args.local_llm_backend == "ollama":
        provider = "ollama"
        model = args.model or "qwen3:14b"
        llm_base_url = args.base_url or "http://localhost:11434"
        embedding_provider = args.embedding_provider or "ollama"
        embedding_base_url = args.embedding_base_url or "http://localhost:11434"
        llm_max_async = args.llm_max_async
        llm_timeout = args.llm_timeout
        api_key = None
        wire_protocol = "ollama-native"
    else:
        provider = args.provider
        model = args.model
        llm_base_url = args.base_url
        embedding_provider = args.embedding_provider
        embedding_base_url = args.embedding_base_url
        llm_max_async = args.llm_max_async
        llm_timeout = args.llm_timeout
        api_key = None
        wire_protocol = provider or "config"
        if provider == "openai" and _is_local_base_url(llm_base_url):
            api_key = os.getenv("OPENAI_API_KEY") or "sk-local"
            wire_protocol = "openai-compatible-local"
        elif provider == "ollama":
            wire_protocol = "ollama-native"

    embedding_model = args.embedding_model
    embedding_dim = args.embedding_dim
    embedding_max_tokens = args.embedding_max_tokens
    embedding_max_chars = args.embedding_max_chars
    embedding_device = args.embedding_device
    embedding_batch_size = args.embedding_batch_size
    embedding_batch_num = args.embedding_batch_num
    embedding_max_async = args.embedding_max_async
    embedding_prefix = args.embedding_prefix
    entity_extraction_timeout = args.entity_extraction_timeout
    if embedding_provider == "huggingface":
        embedding_base_url = None

    if provider:
        override_config["provider"] = provider
    if model:
        override_config["model"] = model
    if embedding_provider:
        override_config["embedding_provider"] = embedding_provider
    if embedding_model:
        override_config["embedding_model"] = embedding_model
    if embedding_dim:
        override_config["embedding_dim"] = embedding_dim
    if embedding_max_tokens:
        override_config["embedding_max_tokens"] = embedding_max_tokens
    if embedding_max_chars:
        override_config["embedding_max_chars"] = embedding_max_chars
    if embedding_device:
        override_config["embedding_device"] = embedding_device
    if embedding_batch_size:
        override_config["embedding_batch_size"] = embedding_batch_size
    if embedding_batch_num:
        override_config["embedding_batch_num"] = embedding_batch_num
    if embedding_max_async:
        override_config["embedding_func_max_async"] = embedding_max_async
    if embedding_prefix is not None:
        override_config["embedding_prefix"] = embedding_prefix
    if llm_max_async:
        override_config["best_model_max_async"] = llm_max_async
        override_config["cheap_model_max_async"] = llm_max_async
    if llm_timeout:
        override_config["llm_timeout"] = llm_timeout
    if entity_extraction_timeout is not None:
        override_config["entity_extraction_timeout"] = entity_extraction_timeout

    if not any([
        provider,
        model,
        llm_base_url,
        embedding_provider,
        embedding_base_url,
        embedding_model,
        embedding_dim,
        embedding_max_tokens,
        embedding_max_chars,
        embedding_device,
        embedding_batch_size,
        embedding_batch_num,
        embedding_max_async,
        embedding_prefix,
        llm_max_async,
        llm_timeout,
        entity_extraction_timeout is not None,
    ]):
        return {}

    return {
        "local_llm_backend": args.local_llm_backend or "provider_override",
        "provider": provider or "config",
        "model": model or "config",
        "llm_base_url": llm_base_url,
        "embedding_provider": embedding_provider or "config",
        "embedding_base_url": embedding_base_url,
        "embedding_model": embedding_model,
        "embedding_dim": embedding_dim,
        "embedding_max_tokens": embedding_max_tokens,
        "embedding_max_chars": embedding_max_chars,
        "embedding_device": embedding_device,
        "embedding_batch_size": embedding_batch_size,
        "embedding_batch_num": embedding_batch_num,
        "embedding_max_async": embedding_max_async,
        "embedding_prefix": embedding_prefix,
        "llm_max_async": llm_max_async,
        "llm_timeout": llm_timeout,
        "entity_extraction_timeout": entity_extraction_timeout,
        "wire_protocol": wire_protocol,
        "api_key": api_key,
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
        f"[runtime] llm_max_async={runtime_config.get('llm_max_async')} "
        f"llm_timeout={runtime_config.get('llm_timeout')} "
        f"entity_extraction_timeout={runtime_config.get('entity_extraction_timeout')}"
    )
    print(
        f"[runtime] embedding_provider={runtime_config['embedding_provider']} "
        f"embedding_base_url={runtime_config['embedding_base_url']}"
    )
    embedding_details = {
        "embedding_model": runtime_config.get("embedding_model"),
        "embedding_dim": runtime_config.get("embedding_dim"),
        "embedding_max_tokens": runtime_config.get("embedding_max_tokens"),
        "embedding_max_chars": runtime_config.get("embedding_max_chars"),
        "embedding_device": runtime_config.get("embedding_device"),
        "embedding_batch_size": runtime_config.get("embedding_batch_size"),
        "embedding_batch_num": runtime_config.get("embedding_batch_num"),
        "embedding_max_async": runtime_config.get("embedding_max_async"),
        "embedding_prefix": runtime_config.get("embedding_prefix"),
    }
    enabled_embedding_details = {
        key: value for key, value in embedding_details.items() if value is not None
    }
    if enabled_embedding_details:
        print(
            "[runtime] "
            + " ".join(f"{key}={value}" for key, value in enabled_embedding_details.items())
        )
    usage_log = os.getenv("TG_RAG_USAGE_LOG")
    if usage_log:
        print(f"[runtime] usage_log={usage_log}")


def load_documents_from_corpus(
    corpus_path: Path,
    num_docs: int = 3,
    doc_start: int = 0,
    doc_end: Optional[int] = None,
) -> List[Dict]:
    """
    Load documents from the ECT-QA corpus.
    
    Args:
        corpus_path: Path to the corpus file (base.jsonl.gz)
        num_docs: Number of documents to load when doc_end is not set
        doc_start: Zero-based corpus index to start loading from
        doc_end: Exclusive zero-based corpus index to stop loading at
        
    Returns:
        List of document dictionaries
    """
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus_path}")
    if doc_start < 0:
        raise ValueError(f"doc_start must be >= 0, got {doc_start}")
    if doc_end is not None and doc_end <= doc_start:
        raise ValueError(f"doc_end must be > doc_start, got {doc_end} <= {doc_start}")

    effective_end = doc_end if doc_end is not None else doc_start + num_docs
    
    documents = []
    try:
        with gzip.open(corpus_path, 'rt', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i < doc_start:
                    continue
                if i >= effective_end:
                    break
                doc = json.loads(line)
                doc["_corpus_index"] = i
                documents.append(doc)
        print(
            f"✅ Loaded {len(documents)} documents from corpus "
            f"(doc_start={doc_start}, doc_end={effective_end})"
        )
        return documents
    except Exception as e:
        raise RuntimeError(f"Error loading corpus: {e}")


def _write_resume_manifest_event(
    manifest_path: Optional[str],
    *,
    run_id: str,
    status: str,
    stage: str,
    args: argparse.Namespace,
    runtime_config: Dict[str, Any],
    error: Optional[str] = None,
) -> None:
    """Append/update a lightweight JSON manifest entry for resumable runs."""
    if not manifest_path:
        return

    path = Path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    else:
        manifest = {}

    runs = manifest.setdefault("runs", [])
    event = {
        "run_id": run_id,
        "status": status,
        "stage": stage,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": args.output_dir,
        "corpus_path": args.corpus_path,
        "num_docs": args.num_docs,
        "doc_start": args.doc_start,
        "doc_end": args.doc_end,
        "skip_community_reports": args.skip_community_reports,
        "rebuild_communities_only": args.rebuild_communities_only,
        "enable_chunk_extraction_cache": args.enable_chunk_extraction_cache,
        "chunk_extraction_cache_path": args.chunk_extraction_cache_path,
        "model": runtime_config.get("model"),
        "local_llm_backend": runtime_config.get("local_llm_backend"),
        "embedding_provider": runtime_config.get("embedding_provider"),
        "embedding_model": runtime_config.get("embedding_model"),
    }
    if error:
        event["error"] = error

    for idx, existing in enumerate(runs):
        if existing.get("run_id") == run_id:
            runs[idx] = {**existing, **event}
            break
    else:
        runs.append(event)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)


def load_documents_from_txt_file(txt_path: Path) -> List[Dict]:
    """
    Load a single text file as a document.
    Supports common text formats: .txt, .md, .rst, .text, .log, and files without extensions.
    
    Args:
        txt_path: Path to the text file
        
    Returns:
        List containing a single document dictionary
    """
    if not txt_path.exists():
        raise FileNotFoundError(f"Text file not found: {txt_path}")
    
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        if not content:
            print(f"⚠️  Warning: File {txt_path} is empty, skipping")
            return []
        
        # Use filename (without extension) as title
        title = txt_path.stem if txt_path.suffix else txt_path.name
        
        return [{
            'title': title,
            'doc': content
        }]
    except UnicodeDecodeError:
        raise RuntimeError(f"File {txt_path} is not a valid text file (binary?)")
    except Exception as e:
        raise RuntimeError(f"Error loading text file {txt_path}: {e}")


def load_documents_from_txt_directory(txt_dir: Path) -> List[Dict]:
    """
    Load all text-based files from a directory as documents.
    Supports common text formats: .txt, .md, .rst, .text, .log, and files without extensions.
    Other file types are ignored.
    
    Args:
        txt_dir: Path to the directory containing text files
        
    Returns:
        List of document dictionaries
    """
    if not txt_dir.exists():
        raise FileNotFoundError(f"Directory not found: {txt_dir}")
    
    if not txt_dir.is_dir():
        raise ValueError(f"Path is not a directory: {txt_dir}")
    
    # Supported text file extensions
    TEXT_EXTENSIONS = {'.txt', '.md', '.rst', '.text', '.log', ''}
    
    # Find all text files recursively
    all_files = list(txt_dir.rglob("*"))
    text_files = [
        f for f in all_files 
        if f.is_file() and (f.suffix.lower() in TEXT_EXTENSIONS or f.suffix == '')
    ]
    
    if not text_files:
        # Check if there are any files at all to provide a helpful error message
        non_dir_files = [f for f in all_files if f.is_file()]
        if non_dir_files:
            file_extensions = {f.suffix for f in non_dir_files if f.suffix}
            raise ValueError(
                f"No supported text files found in directory: {txt_dir}\n"
                f"Found {len(non_dir_files)} file(s) with extension(s): {', '.join(sorted(file_extensions)) or 'none'}\n"
                f"Supported extensions: {', '.join(sorted(TEXT_EXTENSIONS - {''})) or 'none'} (and files without extensions)"
            )
        else:
            raise ValueError(f"No text files found in directory: {txt_dir}")
    
    # Count non-text files for informational message
    non_text_files = [f for f in all_files if f.is_file() and f.suffix.lower() not in TEXT_EXTENSIONS and f.suffix != '']
    if non_text_files:
        print(f"ℹ️  Found {len(non_text_files)} non-text file(s) in directory (ignored)")
    
    documents = []
    for text_file in sorted(text_files):
        try:
            with open(text_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                print(f"⚠️  Warning: File {text_file} is empty, skipping")
                continue
            
            # Use relative path from txt_dir as title (preserves subdirectory structure)
            rel_path = text_file.relative_to(txt_dir)
            # Remove extension for title, but keep the path structure
            title = str(rel_path.with_suffix('')) if rel_path.suffix else str(rel_path)
            
            documents.append({
                'title': title,
                'doc': content
            })
        except UnicodeDecodeError:
            print(f"⚠️  Warning: File {text_file} is not a valid text file (binary?), skipping")
            continue
        except Exception as e:
            print(f"⚠️  Warning: Error loading {text_file}: {e}, skipping")
            continue
    
    print(f"✅ Loaded {len(documents)} documents from {len(text_files)} text files")
    return documents


def prepare_documents_for_insertion(documents: List[Dict]) -> List[Dict]:
    """
    Convert documents to the format expected by TemporalGraphRAG.insert().
    Automatically detects the document format and processes accordingly.
    
    Args:
        documents: List of documents (either from corpus or txt files)
        
    Returns:
        List of documents in format {"title": str, "doc": str}
    """
    if not documents:
        return []
    
    # Auto-detect format: check if first document has 'title' and 'doc' keys (text format)
    # or 'cleaned_content'/'raw_content' keys (corpus format)
    first_doc = documents[0]
    is_corpus_format = 'cleaned_content' in first_doc or 'raw_content' in first_doc
    
    if not is_corpus_format:
        # Already in the correct format (from txt files)
        # Just validate and return
        for doc in documents:
            if 'title' not in doc or 'doc' not in doc:
                raise ValueError(f"Document missing required keys 'title' or 'doc': {list(doc.keys())}")
        return documents
    
    # Process corpus format documents
    prepared_docs = []
    for doc in documents:
        content = doc.get('cleaned_content', doc.get('raw_content', ''))
        if not content:
            print(f"⚠️  Warning: Document {doc.get('company_name', 'Unknown')} has no content, skipping")
            continue
        
        # Create a descriptive title
        company = doc.get('company_name', 'Unknown')
        year = doc.get('year', '')
        quarter = doc.get('quarter', '')
        if year and quarter:
            title = f"{company} {year} Q{quarter.upper()}"
        elif year:
            title = f"{company} {year}"
        else:
            title = company
        
        prepared_docs.append({
            'title': title,
            'doc': content
        })
    
    return prepared_docs




def main():
    """Main function to build the graph."""
    timer = PhaseTimer()
    parser = argparse.ArgumentParser(
        description="Build Temporal GraphRAG knowledge graph from documents (ECT-QA corpus, text files, or directories) using config.yaml",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--config',
        type=str,
        default='tgrag/configs/config.yaml',
        help='Path to configuration file (default: tgrag/configs/config.yaml)'
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        default=None,
        help='Output directory for graph storage (overrides config.working_dir if set)'
    )
    parser.add_argument(
        '--num_docs',
        type=int,
        default=3,
        help='Number of documents to process from the corpus'
    )
    parser.add_argument(
        '--doc_start',
        type=int,
        default=0,
        help='Zero-based corpus document index to start from when loading .jsonl.gz corpus'
    )
    parser.add_argument(
        '--doc_end',
        type=int,
        default=None,
        help='Exclusive zero-based corpus document index to stop at. Overrides --num_docs range end when set'
    )
    parser.add_argument(
        '--corpus_path',
        type=str,
        default='ect-qa/corpus/base.jsonl.gz',
        help='Path to the corpus file (.jsonl.gz), text file (.txt/.md/.rst/.text/.log), or directory of text files (overrides config.corpus_path if set)'
    )
    parser.add_argument(
        '--chunk_size',
        type=int,
        default=None,
        help='Override chunk size from config'
    )
    parser.add_argument(
        '--chunk_overlap',
        type=int,
        default=None,
        help='Override chunk overlap from config'
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
        '--embedding_base_url',
        type=str,
        default=None,
        help='Embedding base URL, e.g. http://localhost:11434 for Ollama embeddings'
    )
    parser.add_argument(
        '--embedding_model',
        type=str,
        default=None,
        help='Override embedding model, e.g. nomic-ai/nomic-embed-text-v1.5 for HuggingFace'
    )
    parser.add_argument(
        '--embedding_dim',
        type=int,
        default=None,
        help='Override embedding vector dimension, e.g. 768 for Nomic or 1024 for BGE-M3'
    )
    parser.add_argument(
        '--embedding_max_tokens',
        type=int,
        default=None,
        help='Override embedding model max token length'
    )
    parser.add_argument(
        '--embedding_max_chars',
        type=int,
        default=None,
        help='Truncate embedding input content above this many characters before embedding'
    )
    parser.add_argument(
        '--embedding_device',
        type=str,
        default=None,
        help='HuggingFace embedding device, e.g. cpu, cuda, or cuda:0'
    )
    parser.add_argument(
        '--embedding_batch_size',
        type=int,
        default=None,
        help='Provider internal embedding encode batch size'
    )
    parser.add_argument(
        '--embedding_batch_num',
        type=int,
        default=None,
        help='Vector store embedding batch size'
    )
    parser.add_argument(
        '--embedding_max_async',
        type=int,
        default=None,
        help='Maximum concurrent embedding batch calls'
    )
    parser.add_argument(
        '--embedding_prefix',
        type=str,
        default=None,
        help='Prefix added to HuggingFace document embeddings, e.g. "search_document: " for Nomic'
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
    parser.add_argument(
        '--entity_extraction_timeout',
        type=float,
        default=None,
        help='Timeout in seconds for the full entity extraction stage. Use 0 to disable the stage timeout.'
    )
    parser.add_argument(
        '--skip_community_reports',
        action='store_true',
        help='Skip community report generation during insert. Useful for resumable staged builds.'
    )
    parser.add_argument(
        '--rebuild_communities_only',
        action='store_true',
        help='Load existing graph/hierarchy from --output_dir and rebuild community reports only.'
    )
    parser.add_argument(
        '--resume_manifest',
        type=str,
        default=None,
        help='Optional JSON manifest path to record resumable run status.'
    )
    parser.add_argument(
        '--enable_chunk_extraction_cache',
        action='store_true',
        help='Persist parsed chunk extraction results so reruns can skip LLM extraction for cached chunks.'
    )
    parser.add_argument(
        '--chunk_extraction_cache_path',
        type=str,
        default=None,
        help='Optional path for chunk extraction cache JSON. Defaults to <output_dir>/kv_store_chunk_extractions.json.'
    )
    
    args = parser.parse_args()
    
    # Prepare override config
    override_config = {}
    if args.corpus_path:
        override_config['corpus_path'] = args.corpus_path
    if args.chunk_size:
        override_config['chunk_size'] = args.chunk_size
    if args.chunk_overlap:
        override_config['chunk_overlap'] = args.chunk_overlap
    if args.output_dir:
        override_config['working_dir'] = args.output_dir
    if args.skip_community_reports:
        override_config['enable_community_summary'] = False
    if args.enable_chunk_extraction_cache:
        override_config['enable_chunk_extraction_cache'] = True
    if args.chunk_extraction_cache_path:
        override_config['chunk_extraction_cache_path'] = args.chunk_extraction_cache_path
    if args.model:
        override_config['llm_model_name'] = args.model
    runtime_config = apply_runtime_overrides(args, override_config)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create TemporalGraphRAG from config (simplified!)
    print("="*60)
    print("Loading Configuration and Initializing TemporalGraphRAG")
    print("="*60)
    print(f"Config file: {args.config}")
    if override_config:
        print(f"Overrides: {override_config}")
    print_runtime(runtime_config)
    if args.resume_manifest:
        print(f"[runtime] resume_manifest={args.resume_manifest}")
    if args.doc_start or args.doc_end is not None:
        print(f"[runtime] doc_start={args.doc_start} doc_end={args.doc_end}")
    if args.skip_community_reports:
        print("[runtime] skip_community_reports=true")
    if args.rebuild_communities_only:
        print("[runtime] rebuild_communities_only=true")
    if args.enable_chunk_extraction_cache:
        print(
            "[runtime] enable_chunk_extraction_cache=true "
            f"chunk_extraction_cache_path={args.chunk_extraction_cache_path or '<output_dir>/kv_store_chunk_extractions.json'}"
        )
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
            config_type="building",
            override_config=override_config if override_config else None,
            api_key=runtime_config.get("api_key") if runtime_config else None,
            base_url=runtime_config.get("llm_base_url") if runtime_config else None,
            embedding_base_url=runtime_config.get("embedding_base_url") if runtime_config else None,
        )
        print("✅ TemporalGraphRAG initialized from config")
        print(f"   Working directory: {graph_rag.working_dir}")
        print(f"   Chunk size: {graph_rag.chunk_token_size} tokens")
        print(f"   Chunk overlap: {graph_rag.chunk_overlap_token_size} tokens")
        print(f"   Entity summarization: {'Disabled' if graph_rag.disable_entity_summarization else 'Enabled'}")
        print(f"   Community summary: {'Enabled' if graph_rag.enable_community_summary else 'Disabled'}")
        timer.mark("initialize TemporalGraphRAG")
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error initializing TemporalGraphRAG: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if args.rebuild_communities_only:
        _write_resume_manifest_event(
            args.resume_manifest,
            run_id=run_id,
            status="running",
            stage="community-only",
            args=args,
            runtime_config=runtime_config,
        )
        try:
            print("\n" + "="*60)
            print("Rebuilding community reports only...")
            print("="*60)
            graph_rag.rebuild_community_reports()
            print("\n✅ Community reports rebuilt successfully!")
            timer.mark("rebuild community reports only")
            _write_resume_manifest_event(
                args.resume_manifest,
                run_id=run_id,
                status="completed",
                stage="community-only",
                args=args,
                runtime_config=runtime_config,
            )
        except Exception as e:
            _write_resume_manifest_event(
                args.resume_manifest,
                run_id=run_id,
                status="failed",
                stage="community-only",
                args=args,
                runtime_config=runtime_config,
                error=str(e),
            )
            print(f"\n❌ Error during community-only rebuild: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            try:
                from tgrag.src.llm.client import get_client_manager
                import asyncio
                client_manager = get_client_manager()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(client_manager.close_clients())
                loop.close()
            except Exception:
                pass

        print("\n" + "="*60)
        print("BUILD SUMMARY")
        print("="*60)
        print("✅ Mode: community-only rebuild")
        print(f"✅ Graph stored in: {Path(graph_rag.working_dir).absolute()}")
        print(f"✅ Working directory: {graph_rag.working_dir}")
        print(f"✅ Configuration: {args.config}")
        print(f"✅ Total elapsed: {format_seconds(timer.total())}")
        print("="*60)
        return
    
    # Load documents from corpus path (use config or override)
    from tgrag.src.config.config_loader import ConfigLoader
    config_loader = ConfigLoader(config_path=args.config)
    config = config_loader.get_config("building", override_args=override_config if override_config else None)
    corpus_path = Path(config.get('corpus_path', args.corpus_path))
    
    # Detect input type and load accordingly
    try:
        if corpus_path.is_file():
            if corpus_path.suffix == '.gz' or corpus_path.suffixes[-2:] == ['.jsonl', '.gz']:
                # JSONL.gz corpus file (e.g., ECT-QA)
                print(f"📚 Loading from corpus file: {corpus_path}")
                documents = load_documents_from_corpus(
                    corpus_path,
                    args.num_docs,
                    doc_start=args.doc_start,
                    doc_end=args.doc_end,
                )
            elif corpus_path.suffix.lower() in {'.txt', '.md', '.rst', '.text', '.log'} or corpus_path.suffix == '':
                # Single text file
                print(f"📄 Loading from text file: {corpus_path}")
                documents = load_documents_from_txt_file(corpus_path)
            else:
                raise ValueError(
                    f"Unsupported file type: {corpus_path.suffix}\n"
                    f"Supported: .jsonl.gz (corpus), .txt/.md/.rst/.text/.log (text files), or files without extensions"
                )
        elif corpus_path.is_dir():
            # Directory of text files
            print(f"📁 Loading from directory: {corpus_path}")
            documents = load_documents_from_txt_directory(corpus_path)
        else:
            raise FileNotFoundError(f"Path not found: {corpus_path}")
        
        if not documents:
            print("❌ No documents loaded")
            sys.exit(1)
        timer.mark(f"load documents ({len(documents)} docs)")
    except Exception as e:
        print(f"❌ Error loading documents: {e}")
        sys.exit(1)
    
    # Prepare documents (auto-detects format)
    prepared_docs = prepare_documents_for_insertion(documents)
    print(f"✅ Prepared {len(prepared_docs)} documents for insertion")
    timer.mark(f"prepare documents ({len(prepared_docs)} docs)")
    
    # Insert documents
    print("\n" + "="*60)
    print("Inserting documents and building graph...")
    print("="*60)
    print(f"Processing {len(prepared_docs)} documents...")
    print("This may take minutes to hours depending on document size and LLM response time.")
    print()
    
    try:
        print("[timer] build graph started")
        _write_resume_manifest_event(
            args.resume_manifest,
            run_id=run_id,
            status="running",
            stage="insert",
            args=args,
            runtime_config=runtime_config,
        )
        graph_rag.insert(prepared_docs)
        print("\n✅ Graph building completed successfully!")
        timer.mark("insert documents and build graph")
        _write_resume_manifest_event(
            args.resume_manifest,
            run_id=run_id,
            status="completed",
            stage="insert",
            args=args,
            runtime_config=runtime_config,
        )
    except Exception as e:
        _write_resume_manifest_event(
            args.resume_manifest,
            run_id=run_id,
            status="failed",
            stage="insert",
            args=args,
            runtime_config=runtime_config,
            error=str(e),
        )
        print(f"\n❌ Error during graph building: {e}")
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
    
    # Summary
    print("\n" + "="*60)
    print("BUILD SUMMARY")
    print("="*60)
    print(f"✅ Documents processed: {len(prepared_docs)}")
    print(f"✅ Graph stored in: {Path(graph_rag.working_dir).absolute()}")
    print(f"✅ Working directory: {graph_rag.working_dir}")
    print(f"✅ Configuration: {args.config}")
    print(f"✅ Total elapsed: {format_seconds(timer.total())}")
    print("="*60)


if __name__ == "__main__":
    main()
