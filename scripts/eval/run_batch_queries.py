#!/usr/bin/env python3
"""Run Temporal-GraphRAG queries from an ECT-QA question file."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from tgrag import create_temporal_graphrag_from_config  # noqa: E402
from tgrag.src.config.config_loader import ConfigLoader  # noqa: E402
from tgrag.src.core.types import QueryParam  # noqa: E402


def log(message: str) -> None:
    print(message, flush=True)


def format_seconds(seconds: float) -> str:
    return f"{seconds:.2f}s"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_done_questions(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                done.add(json.loads(line).get("question", ""))
            except json.JSONDecodeError:
                continue
    return done




def apply_local_llm_runtime(args, override_config: dict[str, Any]) -> dict[str, Any]:
    if not args.local_llm_backend:
        provider = args.provider
        model = args.model or args.llm_model
        llm_base_url = args.base_url or args.llm_base_url
        embedding_provider = args.embedding_provider
        embedding_base_url = args.embedding_base_url
        embedding_model = args.embedding_model
        embedding_dim = args.embedding_dim

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
        if args.llm_max_async:
            override_config["best_model_max_async"] = args.llm_max_async
            override_config["cheap_model_max_async"] = args.llm_max_async
        if args.llm_timeout:
            override_config["llm_timeout"] = args.llm_timeout

        if not any([
            provider,
            model,
            llm_base_url,
            embedding_provider,
            embedding_base_url,
            embedding_model,
            embedding_dim,
        ]):
            return {}

        wire_protocol = provider or "config"
        if provider == "ollama":
            wire_protocol = "ollama-native"
        elif provider == "openai" and llm_base_url:
            is_local = "localhost" in llm_base_url or "127.0.0.1" in llm_base_url
            wire_protocol = "openai-compatible-local" if is_local else "openai-compatible"

        api_key = None
        if provider == "openai" and llm_base_url:
            is_local = "localhost" in llm_base_url or "127.0.0.1" in llm_base_url
            api_key = (os.getenv("OPENAI_API_KEY") or "sk-local") if is_local else os.getenv("OPENAI_API_KEY")

        return {
            "local_llm_backend": "provider_override",
            "provider": provider or "config",
            "model": model or "config",
            "llm_base_url": llm_base_url,
            "embedding_provider": embedding_provider or "config",
            "embedding_model": embedding_model or "config",
            "embedding_dim": embedding_dim,
            "embedding_base_url": embedding_base_url,
            "wire_protocol": wire_protocol,
            "api_key": api_key,
        }

    if args.local_llm_backend == "normal":
        provider = "ollama"
        model = args.llm_model or args.model or "qwen3:14b"
        llm_base_url = args.llm_base_url or args.base_url or "http://localhost:11434"
        wire_protocol = "ollama-native"
        api_key = None
    else:
        provider = "openai"
        model = args.llm_model or args.model or "qwen3-14b-instruct"
        llm_base_url = args.llm_base_url or args.base_url or "http://localhost:8080/v1"
        wire_protocol = "openai-compatible-local"
        api_key = os.getenv("OPENAI_API_KEY") or "sk-local"

    embedding_provider = args.embedding_provider or "ollama"
    embedding_model = args.embedding_model or "nomic-embed-text"
    embedding_dim = args.embedding_dim or 768
    embedding_base_url = args.embedding_base_url or "http://localhost:11434"
    override_config.update({
        "provider": provider,
        "model": model,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_dim": embedding_dim,
    })
    if args.local_llm_backend == "turboquant":
        # Local llama-server has finite KV cache; keep build/query LLM calls serial by default.
        llm_max_async = args.llm_max_async or 1
        override_config["best_model_max_async"] = llm_max_async
        override_config["cheap_model_max_async"] = llm_max_async
        override_config["llm_timeout"] = args.llm_timeout or 600
    elif args.llm_max_async:
        override_config["best_model_max_async"] = args.llm_max_async
        override_config["cheap_model_max_async"] = args.llm_max_async
    if args.llm_timeout:
        override_config["llm_timeout"] = args.llm_timeout
    return {
        "local_llm_backend": args.local_llm_backend,
        "provider": provider,
        "model": model,
        "llm_base_url": llm_base_url,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_dim": embedding_dim,
        "embedding_base_url": embedding_base_url,
        "wire_protocol": wire_protocol,
        "api_key": api_key,
    }


def apply_query_overrides(args, override_config: dict[str, Any]) -> None:
    for name in (
        "top_k",
        "local_max_token_for_text_unit",
        "local_max_token_for_local_context",
        "local_max_token_for_community_report",
        "global_max_token_for_community_report",
        "naive_max_token_for_text_unit",
    ):
        value = getattr(args, name)
        if value is not None:
            override_config[name] = value


def runtime_public_fields(runtime_config: dict[str, Any]) -> dict[str, Any]:
    if not runtime_config:
        return {}
    return {
        "local_llm_backend": runtime_config["local_llm_backend"],
        "llm_model": runtime_config["model"],
        "llm_base_url": runtime_config["llm_base_url"],
        "embedding_provider": runtime_config["embedding_provider"],
        "embedding_model": runtime_config.get("embedding_model"),
        "embedding_dim": runtime_config.get("embedding_dim"),
        "embedding_base_url": runtime_config["embedding_base_url"],
        "wire_protocol": runtime_config["wire_protocol"],
    }


def check_turboquant(base_url: str, strict: bool = False) -> bool:
    props_url = base_url.replace("/v1", "").rstrip("/") + "/props"
    try:
        with urllib.request.urlopen(props_url, timeout=3) as response:
            if response.status == 200:
                response.read()
                log(f"[runtime] turboquant_healthcheck=ok props_url={props_url}")
                return True
            log(f"[runtime] turboquant_healthcheck=warn status={response.status} props_url={props_url}")
    except Exception as exc:
        log(f"[runtime] turboquant_healthcheck=failed props_url={props_url}")
        if strict:
            raise RuntimeError(f"TurboQuant healthcheck failed: {props_url}") from exc
    return False


def build_query_param(raw_config: dict[str, Any], mode: str) -> QueryParam:
    return QueryParam(
        mode=mode,
        top_k=raw_config.get("top_k", 20),
        seed_node_method=raw_config.get("seed_node_method", "entities"),
        local_max_token_for_text_unit=raw_config.get("local_max_token_for_text_unit", 4000),
        local_max_token_for_local_context=raw_config.get("local_max_token_for_local_context", 6000),
        local_max_token_for_community_report=raw_config.get("local_max_token_for_community_report", 2000),
        global_max_token_for_community_report=raw_config.get("global_max_token_for_community_report", 16384),
        naive_max_token_for_text_unit=raw_config.get("naive_max_token_for_text_unit", 12000),
        sub_graph=raw_config.get("enable_subgraph", False),
        mix_relation=raw_config.get("enable_mixed_relationship", False),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run batch queries and save predictions as JSONL.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", default="tgrag/configs/config.yaml")
    parser.add_argument("--working_dir", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=["local", "global", "naive"], required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--resume", action="store_true", help="Skip questions already present in output")
    parser.add_argument("--no_retrieval_detail", action="store_true", help="Do not save local retrieval detail")
    parser.add_argument(
        "--provider",
        choices=["openai", "azure", "bedrock", "gemini", "ollama"],
        default=None,
        help="Override LLM provider from config without using local backend mode",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override LLM model from config without using local backend mode",
    )
    parser.add_argument(
        "--base_url",
        default=None,
        help="Override LLM base URL from config/env without using local backend mode",
    )
    parser.add_argument(
        "--embedding_provider",
        choices=["openai", "azure", "bedrock", "ollama"],
        default=None,
        help="Override embedding provider from config",
    )
    parser.add_argument(
        "--local_llm_backend",
        choices=["normal", "turboquant"],
        default=None,
        help="Local Qwen backend override: normal=Ollama native API, turboquant=local llama-server OpenAI-compatible API",
    )
    parser.add_argument(
        "--llm_model",
        default=None,
        help="Local LLM model name/alias. Defaults: qwen3:14b for normal, qwen3-14b-instruct for turboquant",
    )
    parser.add_argument(
        "--llm_base_url",
        default=None,
        help="Local LLM base URL. Defaults: http://localhost:11434 for normal, http://localhost:8080/v1 for turboquant",
    )
    parser.add_argument(
        "--embedding_base_url",
        default=None,
        help="Ollama embedding base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--embedding_model",
        default=None,
        help="Embedding model name for Ollama embeddings. Default: nomic-embed-text",
    )
    parser.add_argument(
        "--embedding_dim",
        type=int,
        default=None,
        help="Embedding vector dimension. Default: 768 for nomic-embed-text; use 1024 for bge-m3.",
    )
    parser.add_argument(
        "--llm_max_async",
        type=int,
        default=None,
        help="Override max concurrent LLM requests. Defaults to 1 for turboquant; config/default for normal.",
    )
    parser.add_argument(
        "--llm_timeout",
        type=float,
        default=None,
        help="Override LLM request timeout in seconds. Defaults to 600 for turboquant; provider fallback otherwise.",
    )
    parser.add_argument(
        "--turboquant_healthcheck",
        action="store_true",
        help="When using --local_llm_backend turboquant, fail if llama-server /props is unavailable",
    )
    parser.add_argument(
        "--skip_turboquant_healthcheck",
        action="store_true",
        help="Skip llama-server /props check even when using --local_llm_backend turboquant",
    )
    parser.add_argument("--top_k", type=int, default=None, help="Override query top_k")
    parser.add_argument("--local_max_token_for_text_unit", type=int, default=None, help="Override local text-unit context token budget")
    parser.add_argument("--local_max_token_for_local_context", type=int, default=None, help="Override local entities/relations context token budget")
    parser.add_argument("--local_max_token_for_community_report", type=int, default=None, help="Override local community report token budget")
    parser.add_argument("--global_max_token_for_community_report", type=int, default=None, help="Override global community report token budget")
    parser.add_argument("--naive_max_token_for_text_unit", type=int, default=None, help="Override naive text-unit token budget")
    args = parser.parse_args()

    batch_total_start = time.perf_counter()
    questions_path = Path(args.questions)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    load_start = time.perf_counter()
    questions = load_jsonl(questions_path)
    log(f"[batch-detail] load questions: {format_seconds(time.perf_counter() - load_start)} rows={len(questions)}")
    slice_start = time.perf_counter()
    if args.start:
        questions = questions[args.start :]
    if args.limit is not None:
        questions = questions[: args.limit]
    log(f"[batch-detail] apply start/limit: {format_seconds(time.perf_counter() - slice_start)} selected={len(questions)}")

    resume_start = time.perf_counter()
    done_questions = load_done_questions(output_path) if args.resume else set()
    log(f"[batch-detail] load resume state: {format_seconds(time.perf_counter() - resume_start)} done={len(done_questions)}")
    open_mode = "a" if args.resume else "w"

    override_config = {"working_dir": args.working_dir}
    runtime_config = apply_local_llm_runtime(args, override_config)
    apply_query_overrides(args, override_config)
    log(f"[setup] graph: {args.working_dir}")
    log(f"[setup] questions: {questions_path} ({len(questions)} selected)")
    log(f"[setup] output: {output_path}")
    log(f"[setup] mode: {args.mode}")
    if runtime_config:
        log(
            f"[runtime] local_llm_backend={runtime_config['local_llm_backend']} "
            f"provider={runtime_config['provider']} model={runtime_config['model']} "
            f"wire_protocol={runtime_config['wire_protocol']}"
        )
        log(f"[runtime] llm_base_url={runtime_config['llm_base_url']}")
        log(
            f"[runtime] embedding_provider={runtime_config['embedding_provider']} "
            f"embedding_model={runtime_config.get('embedding_model')} "
            f"embedding_dim={runtime_config.get('embedding_dim')} "
            f"embedding_base_url={runtime_config['embedding_base_url']}"
        )
    if (
        runtime_config.get("local_llm_backend") == "turboquant"
        and not args.skip_turboquant_healthcheck
    ):
        try:
            check_turboquant(
                runtime_config["llm_base_url"],
                strict=args.turboquant_healthcheck,
            )
        except RuntimeError as exc:
            log(f"[setup] ERROR: {exc}")
            sys.exit(1)

    setup_start = time.perf_counter()
    log("[setup] loading graph/vector stores... this can take a few minutes for large output_ollama")
    graph_rag = create_temporal_graphrag_from_config(
        config_path=args.config,
        config_type="querying",
        override_config=override_config,
        api_key=runtime_config.get("api_key") if runtime_config else None,
        base_url=runtime_config.get("llm_base_url") if runtime_config else None,
        embedding_base_url=runtime_config.get("embedding_base_url") if runtime_config else None,
    )
    log(f"[timer] load graph/vector stores: {format_seconds(time.perf_counter() - setup_start)}")
    config_loader = ConfigLoader(config_path=args.config)
    raw_config = config_loader.get_config("querying", override_args=override_config)
    query_param = build_query_param(raw_config, args.mode)
    log(f"[timer] initialize graph/query params: {format_seconds(time.perf_counter() - setup_start)}")

    total_start = time.perf_counter()
    processed = 0
    skipped = 0
    failed = 0

    with output_path.open(open_mode, encoding="utf-8") as out:
        log(f"[run] writing predictions to {output_path}")
        for offset, item in enumerate(questions, start=1):
            original_index = args.start + offset
            question = item["question"]
            if question in done_questions:
                skipped += 1
                continue

            one_start = time.perf_counter()
            selected_total = len(questions)
            log(f"[{offset}/{selected_total}] start: {question[:100]}")
            query_call_start = time.perf_counter()
            try:
                raw_response = graph_rag.query(question, param=query_param)
                query_call_elapsed = time.perf_counter() - query_call_start
                retrieval_detail = None
                if isinstance(raw_response, tuple) and len(raw_response) == 2:
                    prediction, retrieval_detail = raw_response
                else:
                    prediction = raw_response

                status = "ok"
            except Exception as exc:
                query_call_elapsed = time.perf_counter() - query_call_start
                prediction = f"ERROR: {exc}"
                retrieval_detail = None
                status = "error"
                failed += 1

            result_start = time.perf_counter()
            elapsed = time.perf_counter() - one_start
            processed += 1
            avg = (time.perf_counter() - total_start) / max(processed, 1)
            remaining = max(selected_total - offset, 0)

            result = {
                "source_file": str(questions_path),
                "index": original_index,
                "mode": args.mode,
                "status": status,
                "elapsed_seconds": round(elapsed, 3),
                "query_call_seconds": round(query_call_elapsed, 3),
                "question": question,
                "answer": item.get("answer", ""),
                "evidence_list": item.get("evidence_list", []),
                "reasoning_type": item.get("reasoning_type", ""),
                "question_type": item.get("question_type", item.get("type", "")),
                "role": item.get("role", ""),
                "prediction": prediction,
            }
            result.update(runtime_public_fields(runtime_config))
            if isinstance(retrieval_detail, dict):
                result["context_chars"] = retrieval_detail.get("context_chars", 0)
                result["context_chunks"] = retrieval_detail.get("text_units", 0)
                result["total_evidence"] = retrieval_detail.get("total_evidence", 0)
            if retrieval_detail is not None and not args.no_retrieval_detail:
                result["retrieval_detail"] = retrieval_detail

            result_build_elapsed = time.perf_counter() - result_start
            write_start = time.perf_counter()
            out.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            out.flush()
            write_elapsed = time.perf_counter() - write_start
            retrieval_summary = ""
            if isinstance(retrieval_detail, dict):
                retrieval_summary = (
                    f" ctx_chunks={retrieval_detail.get('text_units', 0)}"
                    f" ctx_chars={retrieval_detail.get('context_chars', 0)}"
                    f" evidence={retrieval_detail.get('total_evidence', 0)}"
                )
            log(
                f"[timer] query={format_seconds(elapsed)} "
                f"query_call={format_seconds(query_call_elapsed)} "
                f"result_build={format_seconds(result_build_elapsed)} "
                f"write={format_seconds(write_elapsed)} "
                f"avg={format_seconds(avg)} eta={format_seconds(avg * remaining)} "
                f"status={status}{retrieval_summary}"
            )

    total_elapsed = time.perf_counter() - total_start
    log("[summary]")
    log(f"  processed: {processed}")
    log(f"  skipped: {skipped}")
    log(f"  failed: {failed}")
    log(f"  total_seconds: {total_elapsed:.3f}")
    log(f"  wall_seconds_including_setup: {time.perf_counter() - batch_total_start:.3f}")
    log(f"  output: {output_path}")


if __name__ == "__main__":
    main()
