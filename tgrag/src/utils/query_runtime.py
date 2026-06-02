"""Helpers for query-time runtime resolution.

These helpers let CLI and demo entrypoints share the same rules when
combining explicit overrides, config defaults, and optional build manifests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def is_local_base_url(base_url: str | None) -> bool:
    return bool(base_url) and ("localhost" in base_url or "127.0.0.1" in base_url)


def load_build_manifest(working_dir: str | None) -> dict[str, Any]:
    if not working_dir:
        return {}
    manifest_path = Path(working_dir) / "build_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_manifest_path(working_dir: str | None) -> str | None:
    if not working_dir:
        return None
    return str(Path(working_dir) / "build_manifest.json")


def _pick_first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _looks_like_nomic_model(model_name: str | None) -> bool:
    if not model_name:
        return False
    return "nomic" in model_name.lower()


def resolve_query_embedding_runtime(
    *,
    explicit: Mapping[str, Any],
    config_defaults: Mapping[str, Any] | None = None,
    manifest: Mapping[str, Any] | None = None,
    default_provider: str | None = None,
    default_base_url: str | None = None,
) -> dict[str, Any]:
    config_defaults = config_defaults or {}
    manifest = manifest or {}

    provider = _pick_first(
        explicit.get("embedding_provider"),
        manifest.get("embedding_provider"),
        config_defaults.get("embedding_provider"),
        default_provider,
    )
    model = _pick_first(
        explicit.get("embedding_model"),
        manifest.get("embedding_model"),
        config_defaults.get("embedding_model"),
    )
    dim = _pick_first(
        explicit.get("embedding_dim"),
        manifest.get("embedding_dim"),
        config_defaults.get("embedding_dim"),
    )
    device = _pick_first(
        explicit.get("embedding_device"),
        manifest.get("embedding_device"),
        config_defaults.get("embedding_device"),
    )
    batch_size = _pick_first(
        explicit.get("embedding_batch_size"),
        manifest.get("embedding_batch_size"),
        config_defaults.get("embedding_batch_size"),
    )
    max_tokens = _pick_first(
        explicit.get("embedding_max_tokens"),
        manifest.get("embedding_max_tokens"),
        config_defaults.get("embedding_max_tokens"),
    )

    explicit_prefix = explicit.get("embedding_prefix")
    if explicit_prefix is not None:
        prefix = explicit_prefix
    elif provider == "huggingface" and (
        model is None or _looks_like_nomic_model(model)
    ):
        prefix = "search_query: "
    else:
        prefix = _pick_first(
            manifest.get("embedding_prefix"),
            config_defaults.get("embedding_prefix"),
        )

    if provider == "huggingface":
        base_url = None
    else:
        base_url = _pick_first(
            explicit.get("embedding_base_url"),
            manifest.get("embedding_base_url"),
            config_defaults.get("embedding_base_url"),
            default_base_url,
        )

    return {
        "embedding_provider": provider,
        "embedding_model": model,
        "embedding_dim": dim,
        "embedding_device": device,
        "embedding_batch_size": batch_size,
        "embedding_max_tokens": max_tokens,
        "embedding_prefix": prefix,
        "embedding_base_url": base_url,
    }


def infer_runtime_warnings(
    *,
    working_dir: str | None,
    manifest: Mapping[str, Any] | None,
    config_defaults: Mapping[str, Any] | None,
    resolved_embedding: Mapping[str, Any],
    local_llm_backend: str | None,
) -> list[str]:
    warnings: list[str] = []
    manifest = manifest or {}
    config_defaults = config_defaults or {}

    if working_dir and not manifest:
        warnings.append(
            "No build_manifest.json found in working_dir. Query runtime can only "
            "follow explicit CLI/UI overrides or config defaults."
        )

    if (
        local_llm_backend == "turboquant"
        and not manifest
        and config_defaults.get("embedding_provider") == "ollama"
        and resolved_embedding.get("embedding_provider") == "ollama"
    ):
        warnings.append(
            "Embedding runtime resolved to ollama from config defaults. If this "
            "graph was built with HuggingFace embeddings, pass "
            "--embedding_provider huggingface and the matching embedding args."
        )

    if (
        resolved_embedding.get("embedding_provider") == "huggingface"
        and (
            resolved_embedding.get("embedding_model") is None
            or _looks_like_nomic_model(resolved_embedding.get("embedding_model"))
        )
        and resolved_embedding.get("embedding_prefix") == "search_query: "
    ):
        warnings.append(
            "Using query-time HuggingFace Nomic prefix 'search_query: '. Build-time "
            "document prefix should remain 'search_document: '."
        )

    return warnings
