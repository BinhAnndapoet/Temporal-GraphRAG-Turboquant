#!/usr/bin/env python3
"""Summarize TG_RAG_USAGE_LOG token usage JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def get_usage_number(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize token usage from TG_RAG_USAGE_LOG.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--usage_log", required=True)
    args = parser.parse_args()

    path = Path(args.usage_log)
    if not path.exists():
        raise SystemExit(f"Usage log does not exist: {path}")

    total = {
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    by_model: dict[str, dict[str, int]] = {}

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            usage = row.get("usage", {})
            model = f"{row.get('provider', '')}:{row.get('model', '')}"
            prompt = get_usage_number(
                usage,
                "prompt_tokens",
                "prompt_token_count",
                "prompt_eval_count",
            )
            completion = get_usage_number(
                usage,
                "completion_tokens",
                "candidates_token_count",
                "completion_token_count",
                "eval_count",
            )
            all_tokens = get_usage_number(usage, "total_tokens", "total_token_count")
            if all_tokens == 0:
                all_tokens = prompt + completion

            total["calls"] += 1
            total["prompt_tokens"] += prompt
            total["completion_tokens"] += completion
            total["total_tokens"] += all_tokens

            model_total = by_model.setdefault(
                model,
                {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )
            model_total["calls"] += 1
            model_total["prompt_tokens"] += prompt
            model_total["completion_tokens"] += completion
            model_total["total_tokens"] += all_tokens

    print(json.dumps({"total": total, "by_model": by_model}, indent=2))


if __name__ == "__main__":
    main()
