#!/usr/bin/env python3
"""LLM-as-judge metrics for specific ECT-QA predictions."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


JUDGE_PROMPT = """You are an expert evaluator for financial temporal question answering.

Evaluate the model prediction against the question, ground-truth answer, and supporting evidence.

Task:
1. Decompose the ground-truth answer into the required factual elements.
2. For each required factual element, classify the model prediction as one of:
   - CORRECT: the prediction gives the right fact/value and matches the required temporal scope.
   - REFUSAL: the prediction explicitly says it cannot answer that element because evidence is missing.
   - INCORRECT: the prediction is wrong, unsupported, hallucinated, or mismatched in time.
3. The counts must satisfy correct_count + refusal_count + incorrect_count = total_count.

Question:
{question}

Ground-truth answer:
{answer}

Supporting evidence:
{evidence}

Model prediction:
{prediction}

Return only JSON with this schema:
{{
  "elements": [
    {{"required_element": "...", "status": "CORRECT|REFUSAL|INCORRECT", "reason": "..."}}
  ],
  "correct_count": 0,
  "refusal_count": 0,
  "incorrect_count": 0,
  "total_count": 0
}}
"""


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


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def evidence_to_text(evidence_list: list[dict[str, Any]], max_chars: int) -> str:
    parts = []
    for ev in evidence_list:
        prefix = " | ".join(
            str(ev.get(key, ""))
            for key in ["company_name", "year", "quarter", "ect_filename"]
            if ev.get(key)
        )
        evidence = ev.get("evidence", "")
        parts.append(f"{prefix}: {evidence}" if prefix else str(evidence))
    text = "\n".join(parts)
    return text[:max_chars]


def normalize_judgment(judgment: dict[str, Any]) -> dict[str, Any]:
    elements = judgment.get("elements") or []
    correct = int(judgment.get("correct_count", 0))
    refusal = int(judgment.get("refusal_count", 0))
    incorrect = int(judgment.get("incorrect_count", 0))
    total = int(judgment.get("total_count", 0))

    if total <= 0 and elements:
        correct = sum(1 for item in elements if str(item.get("status", "")).upper() == "CORRECT")
        refusal = sum(1 for item in elements if str(item.get("status", "")).upper() == "REFUSAL")
        incorrect = sum(1 for item in elements if str(item.get("status", "")).upper() == "INCORRECT")
        total = correct + refusal + incorrect

    judgment["correct_count"] = correct
    judgment["refusal_count"] = refusal
    judgment["incorrect_count"] = incorrect
    judgment["total_count"] = total
    return judgment


def call_gemini(prompt: str, model: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GOOGLE_API_KEY or GEMINI_API_KEY for Gemini judging.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    usage = {}
    if getattr(response, "usage_metadata", None) is not None:
        usage = dict(response.usage_metadata.model_dump())
    return extract_json(response.text or ""), usage


def call_openai(prompt: str, model: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY for OpenAI judging.")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    usage = response.usage.model_dump() if response.usage else {}
    return extract_json(response.choices[0].message.content or ""), usage


def judge_one(row: dict[str, Any], provider: str, model: str, evidence_chars: int) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt = JUDGE_PROMPT.format(
        question=row.get("question", ""),
        answer=row.get("answer", ""),
        evidence=evidence_to_text(row.get("evidence_list", []), evidence_chars),
        prediction=row.get("prediction", ""),
    )
    if provider == "gemini":
        return call_gemini(prompt, model)
    if provider == "openai":
        return call_openai(prompt, model)
    raise ValueError(f"Unsupported judge provider: {provider}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute Correct/Refusal/Incorrect with an LLM judge.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--judge_provider", choices=["gemini", "openai"], default="gemini")
    parser.add_argument("--judge_model", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--include_unanswerable", action="store_true")
    parser.add_argument("--evidence_chars", type=int, default=6000)
    args = parser.parse_args()

    if args.judge_model is None:
        args.judge_model = "gemini-2.5-flash-lite" if args.judge_provider == "gemini" else "gpt-4o-mini"

    rows = load_jsonl(Path(args.predictions))
    if not args.include_unanswerable:
        rows = [
            row for row in rows
            if row.get("answer") and str(row.get("answer", "")).lower() != "unanswerable"
        ]
    if args.limit is not None:
        rows = rows[: args.limit]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    done_questions = load_done_questions(output_path) if args.resume else set()
    open_mode = "a" if args.resume else "w"

    totals = {"correct": 0, "refusal": 0, "incorrect": 0, "elements": 0}
    start = time.perf_counter()
    processed = 0
    failed = 0

    with output_path.open(open_mode, encoding="utf-8") as out:
        for idx, row in enumerate(rows, start=1):
            question = row.get("question", "")
            if question in done_questions:
                continue

            one_start = time.perf_counter()
            print(f"[{idx}/{len(rows)}] judge {question[:100]}")
            try:
                judgment, usage = judge_one(row, args.judge_provider, args.judge_model, args.evidence_chars)
                judgment = normalize_judgment(judgment)
                status = "ok"
            except Exception as exc:
                judgment = {
                    "elements": [],
                    "correct_count": 0,
                    "refusal_count": 0,
                    "incorrect_count": 0,
                    "total_count": 0,
                    "error": str(exc),
                }
                usage = {}
                status = "error"
                failed += 1

            elapsed = time.perf_counter() - one_start
            correct = judgment["correct_count"]
            refusal = judgment["refusal_count"]
            incorrect = judgment["incorrect_count"]
            total = judgment["total_count"]
            totals["correct"] += correct
            totals["refusal"] += refusal
            totals["incorrect"] += incorrect
            totals["elements"] += total
            processed += 1

            result = {
                "question": question,
                "answer": row.get("answer", ""),
                "prediction": row.get("prediction", ""),
                "status": status,
                "elapsed_seconds": round(elapsed, 3),
                "judge_provider": args.judge_provider,
                "judge_model": args.judge_model,
                "usage": usage,
                "judgment": judgment,
            }
            out.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            out.flush()

            if total:
                print(
                    f"[score] correct={correct / total:.3f} "
                    f"refusal={refusal / total:.3f} incorrect={incorrect / total:.3f} "
                    f"time={elapsed:.2f}s status={status}"
                )
            else:
                print(f"[score] no elements time={elapsed:.2f}s status={status}")

    denom = max(totals["elements"], 1)
    summary = {
        "processed": processed,
        "failed": failed,
        "total_elements": totals["elements"],
        "correct": totals["correct"] / denom,
        "refusal": totals["refusal"] / denom,
        "incorrect": totals["incorrect"] / denom,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "output": str(output_path),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
