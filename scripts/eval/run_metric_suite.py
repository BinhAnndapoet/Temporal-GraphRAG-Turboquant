#!/usr/bin/env python3
"""Run post-query metric summaries for Temporal-GraphRAG predictions.

This utility standardizes the metric layer after query generation. It does not
build graphs or run the model; instead, it reads one or more prediction JSONL
files, computes non-LLM metrics, and writes reproducible artifacts for later
inspection.

The script is intentionally conservative:

- It computes token-level F1 and ROUGE-L against the reference answer.
- It preserves a detailed per-question JSONL file for auditability.
- It optionally compares two prediction files on their overlapping questions.
- It records a manifest and a human-readable log file so runs can be compared
  later without re-running the queries.

External judge-based scoring (for example Gemini or OpenAI) is intentionally
left to the existing dedicated judge scripts. This keeps this runner usable in
offline environments and avoids mixing evaluation logic with remote API calls.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-z0-9.$%+-]+")


def configure_logging(log_path: Path) -> logging.Logger:
    """Create a logger that mirrors messages to stdout and to ``log_path``."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("metric_suite")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file into memory and return the parsed rows."""

    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def tokenize(text: str) -> list[str]:
    """Tokenize text into a small normalized token stream for overlap metrics."""

    return TOKEN_RE.findall(str(text).lower())


def token_f1(prediction: str, reference: str) -> float:
    """Compute token-level F1 between a prediction and a reference answer."""

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
    """Return the length of the longest common subsequence between two token lists."""

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
    """Compute ROUGE-L F1 using the longest common subsequence heuristic."""

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


def scored_rows(
    rows: list[dict[str, Any]], include_unanswerable: bool
) -> list[dict[str, Any]]:
    """Attach non-LLM metric scores to each scored prediction row."""

    scored: list[dict[str, Any]] = []
    for row in rows:
        answer = str(row.get("answer", ""))
        if not include_unanswerable and (
            not answer or answer.lower() == "unanswerable"
        ):
            continue

        prediction = str(row.get("prediction", ""))
        scored.append(
            {
                "index": row.get("index"),
                "question": row.get("question"),
                "answer": answer,
                "prediction": prediction,
                "f1": token_f1(prediction, answer),
                "rouge_l": rouge_l_f1(prediction, answer),
            }
        )
    return scored


def summarize_scored_rows(
    rows: list[dict[str, Any]], predictions_path: Path, include_unanswerable: bool
) -> dict[str, Any]:
    """Summarize a single prediction file and return the metric payload."""

    scored = scored_rows(rows, include_unanswerable=include_unanswerable)
    f1_scores = [row["f1"] for row in scored]
    rouge_scores = [row["rouge_l"] for row in scored]
    summary = {
        "predictions": str(predictions_path),
        "num_rows": len(rows),
        "num_scored": len(scored),
        "f1": statistics.fmean(f1_scores) if f1_scores else 0.0,
        "rouge_l": statistics.fmean(rouge_scores) if rouge_scores else 0.0,
        "include_unanswerable": include_unanswerable,
    }
    return {"summary": summary, "items": scored}


def compare_prediction_files(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    include_unanswerable: bool,
) -> dict[str, Any]:
    """Compare two prediction files on their overlapping questions."""

    scored_a = scored_rows(rows_a, include_unanswerable=include_unanswerable)
    scored_b = scored_rows(rows_b, include_unanswerable=include_unanswerable)
    map_a = {row["question"]: row for row in scored_a if row.get("question")}
    map_b = {row["question"]: row for row in scored_b if row.get("question")}
    overlap_questions = sorted(set(map_a) & set(map_b))

    detail_rows: list[dict[str, Any]] = []
    f1_deltas: list[float] = []
    rouge_deltas: list[float] = []
    same_prediction = 0
    better_a = 0
    better_b = 0

    for question in overlap_questions:
        row_a = map_a[question]
        row_b = map_b[question]
        delta_f1 = float(row_a["f1"]) - float(row_b["f1"])
        delta_rouge = float(row_a["rouge_l"]) - float(row_b["rouge_l"])
        f1_deltas.append(delta_f1)
        rouge_deltas.append(delta_rouge)
        if row_a.get("prediction", "") == row_b.get("prediction", ""):
            same_prediction += 1
        if delta_f1 > 0:
            better_a += 1
        elif delta_f1 < 0:
            better_b += 1

        detail_rows.append(
            {
                "question": question,
                "answer": row_a.get("answer", ""),
                "prediction_a": row_a.get("prediction", ""),
                "prediction_b": row_b.get("prediction", ""),
                "f1_a": row_a.get("f1", 0.0),
                "f1_b": row_b.get("f1", 0.0),
                "rouge_l_a": row_a.get("rouge_l", 0.0),
                "rouge_l_b": row_b.get("rouge_l", 0.0),
                "delta_f1": delta_f1,
                "delta_rouge_l": delta_rouge,
                "same_prediction": row_a.get("prediction", "")
                == row_b.get("prediction", ""),
            }
        )

    summary = {
        "num_overlap_questions": len(overlap_questions),
        "same_prediction_count": same_prediction,
        "better_a_count_f1": better_a,
        "better_b_count_f1": better_b,
        "mean_delta_f1": statistics.fmean(f1_deltas) if f1_deltas else 0.0,
        "mean_delta_rouge_l": statistics.fmean(rouge_deltas) if rouge_deltas else 0.0,
        "question_overlap_ratio_a": len(overlap_questions) / max(len(scored_a), 1),
        "question_overlap_ratio_b": len(overlap_questions) / max(len(scored_b), 1),
    }
    return {"summary": summary, "items": detail_rows}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON payload to disk with pretty formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a list of dictionaries as JSONL for detailed inspection."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def slugify(text: str) -> str:
    """Convert a label into a filesystem-friendly slug."""

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip())
    return slug.strip("-") or "run"


def build_run_directory(output_root: Path, label: str) -> Path:
    """Create a timestamped run directory under ``output_root``."""

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return output_root / f"{timestamp}_{slugify(label)}"


def main() -> None:
    """Parse CLI arguments, compute metrics, and write the run artifacts."""

    parser = argparse.ArgumentParser(
        description="Run non-LLM metric summaries for prediction JSONL files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--predictions",
        nargs="+",
        required=True,
        help="One or more prediction JSONL files to evaluate.",
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        default=None,
        help="Optional labels matching --predictions order. Defaults to file stems.",
    )
    parser.add_argument(
        "--output_root",
        default="results/metrics/metric_suite",
        help="Root directory for metric outputs.",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Write a comparison summary for the first two prediction files.",
    )
    parser.add_argument(
        "--include_unanswerable",
        action="store_true",
        help="Include rows whose reference answer is empty or 'unanswerable'.",
    )
    args = parser.parse_args()

    predictions = [Path(item) for item in args.predictions]
    if args.labels is not None and len(args.labels) != len(predictions):
        raise SystemExit("--labels must match the number of --predictions entries")

    labels = args.labels or [path.stem for path in predictions]
    run_label = "compare" if args.compare else "metrics"
    run_dir = build_run_directory(Path(args.output_root), run_label)
    log_path = Path("logs/metrics") / f"{run_dir.name}.log"
    logger = configure_logging(log_path)

    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"[setup] run_dir={run_dir}")
    logger.info(f"[setup] log_path={log_path}")
    logger.info(f"[setup] include_unanswerable={args.include_unanswerable}")

    manifest: dict[str, Any] = {
        "run_dir": str(run_dir),
        "log_path": str(log_path),
        "predictions": [str(path) for path in predictions],
        "labels": labels,
        "include_unanswerable": args.include_unanswerable,
        "compare": args.compare,
    }

    start = time.perf_counter()
    per_file: dict[str, Any] = {}
    for label, path in zip(labels, predictions, strict=True):
        logger.info(f"[file] load={path}")
        rows = load_jsonl(path)
        payload = summarize_scored_rows(
            rows=rows,
            predictions_path=path,
            include_unanswerable=args.include_unanswerable,
        )
        summary_path = run_dir / f"{slugify(label)}_nonllm.json"
        detail_path = run_dir / f"{slugify(label)}_nonllm.jsonl"
        write_json(summary_path, payload)
        write_jsonl(detail_path, payload["items"])
        logger.info(
            f"[file] label={label} num_rows={payload['summary']['num_rows']} "
            f"num_scored={payload['summary']['num_scored']} f1={payload['summary']['f1']:.4f} "
            f"rouge_l={payload['summary']['rouge_l']:.4f}"
        )
        per_file[label] = {
            "source": str(path),
            "summary_path": str(summary_path),
            "detail_path": str(detail_path),
            "summary": payload["summary"],
        }

    comparison: dict[str, Any] | None = None
    if args.compare:
        if len(predictions) < 2:
            raise SystemExit("--compare requires at least two prediction files")
        logger.info("[compare] building overlap comparison for the first two files")
        rows_a = load_jsonl(predictions[0])
        rows_b = load_jsonl(predictions[1])
        comparison = compare_prediction_files(
            rows_a=rows_a,
            rows_b=rows_b,
            include_unanswerable=args.include_unanswerable,
        )
        comparison_path = run_dir / "comparison_overlap.json"
        comparison_detail_path = run_dir / "comparison_overlap.jsonl"
        write_json(comparison_path, comparison)
        write_jsonl(comparison_detail_path, comparison["items"])
        logger.info(
            f"[compare] overlap={comparison['summary']['num_overlap_questions']} "
            f"mean_delta_f1={comparison['summary']['mean_delta_f1']:.4f} "
            f"mean_delta_rouge_l={comparison['summary']['mean_delta_rouge_l']:.4f}"
        )
        manifest["comparison_path"] = str(comparison_path)
        manifest["comparison_detail_path"] = str(comparison_detail_path)

    manifest["per_file"] = per_file
    manifest["comparison"] = comparison["summary"] if comparison else None
    manifest["elapsed_seconds"] = round(time.perf_counter() - start, 3)
    manifest_path = run_dir / "manifest.json"
    write_json(manifest_path, manifest)
    logger.info(f"[saved] manifest={manifest_path}")
    logger.info(f"[done] elapsed_seconds={manifest['elapsed_seconds']:.3f}")


if __name__ == "__main__":
    main()
