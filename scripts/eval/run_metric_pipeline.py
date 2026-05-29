#!/usr/bin/env python3
"""Run the full metric pipeline for TG-RAG prediction artifacts.

The pipeline wraps the existing metric scripts so a single command can execute
the requested evaluation groups:

1. Specific QA non-LLM metrics and optional Gemini/OpenAI judge scoring.
2. Abstract QA pairwise judge scoring when two abstract prediction files are
   provided.

The goal is operational convenience rather than new scoring logic. All heavy
lifting remains in the dedicated scripts:

- ``scripts/eval/run_metric_suite.py`` for non-LLM summaries and overlap
  comparison.
- ``scripts/eval/judge_specific.py`` for element-wise factual judging.
- ``scripts/eval/judge_pairwise_abstract.py`` for abstract pairwise judging.

This wrapper only orchestrates those scripts, records commands in a log, and
keeps the resulting artifact paths together in one manifest.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def slugify(text: str) -> str:
    """Turn a label into a filesystem-friendly identifier."""

    import re

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip())
    return slug.strip("-") or "run"


def configure_logger(log_path: Path):
    """Create a simple logger that mirrors messages to stdout and a file."""

    import logging
    import sys as _sys

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"metric_pipeline_{log_path.stem}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(message)s")
    stream_handler = logging.StreamHandler(_sys.stdout)
    stream_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger


def run_command(command: list[str], logger) -> None:
    """Run a subprocess command and fail fast if it returns a non-zero code."""

    logger.info("[command] " + " ".join(command))
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        logger.info(line.rstrip("\n"))
    return_code = process.wait()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Persist a JSON artifact with pretty formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    """Parse CLI arguments and orchestrate the requested metric groups."""

    parser = argparse.ArgumentParser(
        description="Run TG-RAG metric groups in one place.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--specific_predictions",
        nargs="+",
        default=None,
        help="Specific QA prediction files to summarize and judge.",
    )
    parser.add_argument(
        "--specific_labels",
        nargs="+",
        default=None,
        help="Optional labels for the specific prediction files.",
    )
    parser.add_argument(
        "--abstract_predictions_a",
        default=None,
        help="First abstract QA prediction file for pairwise judging.",
    )
    parser.add_argument(
        "--abstract_predictions_b",
        default=None,
        help="Second abstract QA prediction file for pairwise judging.",
    )
    parser.add_argument(
        "--output_root",
        default="results/metrics/pipeline",
        help="Root directory for pipeline outputs.",
    )
    parser.add_argument(
        "--judge_provider",
        choices=["gemini", "openai"],
        default="gemini",
        help="Judge backend for LLM-based scoring.",
    )
    parser.add_argument(
        "--judge_model",
        default=None,
        help="Judge model name. Defaults to gemini-2.5-flash-lite or gpt-4o-mini.",
    )
    parser.add_argument(
        "--include_unanswerable",
        action="store_true",
        help="Include unanswerable rows in non-LLM and specific judge runs.",
    )
    parser.add_argument(
        "--run_specific",
        action="store_true",
        help="Run specific QA metrics/judging.",
    )
    parser.add_argument(
        "--run_abstract",
        action="store_true",
        help="Run abstract QA pairwise judging.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run every requested group in one command.",
    )
    args = parser.parse_args()

    specific_predictions = [Path(p) for p in args.specific_predictions or []]
    if args.specific_labels is not None and len(args.specific_labels) != len(specific_predictions):
        raise SystemExit("--specific_labels must match --specific_predictions length")

    run_specific = args.run_specific or bool(specific_predictions)
    run_abstract = args.run_abstract or bool(args.abstract_predictions_a and args.abstract_predictions_b)

    if (args.run_specific or (args.all and specific_predictions)) and not specific_predictions:
        raise SystemExit("Specific QA was requested but --specific_predictions is empty")
    if args.run_abstract and not (args.abstract_predictions_a and args.abstract_predictions_b):
        raise SystemExit("Abstract QA was requested but both abstract prediction files were not provided")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_name = slugify("all" if args.all else "pipeline")
    run_dir = Path(args.output_root) / f"{timestamp}_{run_name}"
    log_path = Path("logs/metrics/pipeline") / f"{run_dir.name}.log"
    logger = configure_logger(log_path)
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "run_dir": str(run_dir),
        "log_path": str(log_path),
        "judge_provider": args.judge_provider,
        "judge_model": args.judge_model,
        "include_unanswerable": args.include_unanswerable,
        "specific_predictions": [str(p) for p in specific_predictions],
        "specific_labels": args.specific_labels,
        "abstract_predictions_a": args.abstract_predictions_a,
        "abstract_predictions_b": args.abstract_predictions_b,
    }

    logger.info(f"[setup] run_dir={run_dir}")
    logger.info(f"[setup] log_path={log_path}")

    created_artifacts: dict[str, Any] = {}

    if run_specific:
        label_args = []
        if args.specific_labels:
            label_args = ["--labels", *args.specific_labels]

        metric_cmd = [
            sys.executable,
            "scripts/eval/run_metric_suite.py",
            "--predictions",
            *[str(path) for path in specific_predictions],
            "--output_root",
            str(run_dir / "specific"),
            "--compare",
        ]
        if args.include_unanswerable:
            metric_cmd.append("--include_unanswerable")
        metric_cmd.extend(label_args)
        run_command(metric_cmd, logger)

        metric_run_root = run_dir / "specific"
        created_artifacts["specific_metrics_root"] = str(metric_run_root)

        judge_outputs: dict[str, str] = {}
        for idx, prediction in enumerate(specific_predictions, start=1):
            label = args.specific_labels[idx - 1] if args.specific_labels else prediction.stem
            judge_output = run_dir / "specific" / "judged" / f"{slugify(label)}_{args.judge_provider}.jsonl"
            judge_cmd = [
                sys.executable,
                "scripts/eval/judge_specific.py",
                "--predictions",
                str(prediction),
                "--output",
                str(judge_output),
                "--judge_provider",
                args.judge_provider,
            ]
            if args.judge_model:
                judge_cmd.extend(["--judge_model", args.judge_model])
            if args.include_unanswerable:
                judge_cmd.append("--include_unanswerable")
            run_command(judge_cmd, logger)
            judge_outputs[label] = str(judge_output)

        created_artifacts["specific_judged"] = judge_outputs

    if run_abstract:
        abstract_output = run_dir / "abstract" / f"pairwise_{args.judge_provider}.jsonl"
        abstract_cmd = [
            sys.executable,
            "scripts/eval/judge_pairwise_abstract.py",
            "--predictions_a",
            str(args.abstract_predictions_a),
            "--predictions_b",
            str(args.abstract_predictions_b),
            "--name_a",
            "A",
            "--name_b",
            "B",
            "--output",
            str(abstract_output),
            "--judge_provider",
            args.judge_provider,
        ]
        if args.judge_model:
            abstract_cmd.extend(["--judge_model", args.judge_model])
        run_command(abstract_cmd, logger)
        created_artifacts["abstract_judged"] = str(abstract_output)
    elif args.all and not (args.abstract_predictions_a and args.abstract_predictions_b):
        logger.info("[skip] abstract group skipped because no abstract prediction pair was supplied")

    manifest["created_artifacts"] = created_artifacts
    manifest_path = run_dir / "manifest.json"
    write_json(manifest_path, manifest)
    logger.info(f"[saved] manifest={manifest_path}")
    logger.info("[done] pipeline complete")


if __name__ == "__main__":
    main()