#!/usr/bin/env python3
"""Compute token F1 and ROUGE-L for specific ECT-QA predictions."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[A-Za-z0-9.$%+-]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(str(text).lower())


def token_f1(prediction: str, reference: str) -> float:
    pred_tokens = tokenize(prediction)
    ref_tokens = tokenize(reference)
    if not pred_tokens or not ref_tokens:
        return 0.0

    common = sum((Counter(pred_tokens) & Counter(ref_tokens)).values())
    if common == 0:
        return 0.0

    precision = common / len(pred_tokens)
    recall = common / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)


def lcs_length(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for token_a in a:
        curr = [0] * (len(b) + 1)
        for j, token_b in enumerate(b, start=1):
            if token_a == token_b:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev = curr
    return prev[-1]


def rouge_l_f1(prediction: str, reference: str) -> float:
    pred_tokens = tokenize(prediction)
    ref_tokens = tokenize(reference)
    if not pred_tokens or not ref_tokens:
        return 0.0
    lcs = lcs_length(ref_tokens, pred_tokens)
    if lcs == 0:
        return 0.0
    precision = lcs / len(pred_tokens)
    recall = lcs / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute non-LLM metrics for prediction JSONL.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", default=None, help="Optional JSON file for detailed scores")
    parser.add_argument("--include_unanswerable", action="store_true")
    args = parser.parse_args()

    rows = load_jsonl(Path(args.predictions))
    scored: list[dict[str, Any]] = []

    for row in rows:
        answer = str(row.get("answer", ""))
        if not args.include_unanswerable and (not answer or answer.lower() == "unanswerable"):
            continue
        prediction = str(row.get("prediction", ""))
        f1 = token_f1(prediction, answer)
        rouge_l = rouge_l_f1(prediction, answer)
        scored.append(
            {
                "index": row.get("index"),
                "question": row.get("question"),
                "answer": answer,
                "prediction": prediction,
                "f1": f1,
                "rouge_l": rouge_l,
            }
        )

    f1_scores = [row["f1"] for row in scored]
    rouge_scores = [row["rouge_l"] for row in scored]
    summary = {
        "predictions": args.predictions,
        "num_rows": len(rows),
        "num_scored": len(scored),
        "f1": mean(f1_scores),
        "rouge_l": mean(rouge_scores),
    }

    print(json.dumps(summary, indent=2))
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps({"summary": summary, "items": scored}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[saved] {output_path}")


if __name__ == "__main__":
    main()
