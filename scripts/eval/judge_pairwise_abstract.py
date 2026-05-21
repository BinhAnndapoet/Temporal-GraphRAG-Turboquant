#!/usr/bin/env python3
"""Pairwise LLM-as-judge for abstract/global ECT-QA predictions."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


PAIRWISE_PROMPT = """You are an expert judge evaluating two answers to a financial temporal analysis question.

Question:
{question}

Answer A:
{answer_a}

Answer B:
{answer_b}

Evaluate the answers on:
1. Comprehensiveness: Which answer covers more relevant aspects and details?
2. Diversity: Which answer provides more varied perspectives and insights?
3. Temporal Coverage: Which answer better handles years, quarters, chronology, and temporal relationships?
4. Overall Winner: Which answer is better overall?

Return only JSON:
{{
  "comprehensiveness": "A|B|TIE",
  "diversity": "A|B|TIE",
  "temporal_coverage": "A|B|TIE",
  "overall_winner": "A|B|TIE",
  "reasoning": "..."
}}
"""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def by_question(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row.get("question", ""): row for row in rows if row.get("question")}


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


def judge_pair(question: str, answer_a: str, answer_b: str, provider: str, model: str) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt = PAIRWISE_PROMPT.format(question=question, answer_a=answer_a, answer_b=answer_b)
    if provider == "gemini":
        return call_gemini(prompt, model)
    if provider == "openai":
        return call_openai(prompt, model)
    raise ValueError(f"Unsupported judge provider: {provider}")


def init_counts() -> dict[str, int]:
    return {"A": 0, "B": 0, "TIE": 0}


def normalize_winner(value: Any) -> str:
    value = str(value).upper().strip()
    return value if value in {"A", "B", "TIE"} else "TIE"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute pairwise win rates for abstract/global predictions.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--predictions_a", required=True)
    parser.add_argument("--predictions_b", required=True)
    parser.add_argument("--name_a", default="A")
    parser.add_argument("--name_b", default="B")
    parser.add_argument("--output", required=True)
    parser.add_argument("--judge_provider", choices=["gemini", "openai"], default="gemini")
    parser.add_argument("--judge_model", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.judge_model is None:
        args.judge_model = "gemini-2.5-flash-lite" if args.judge_provider == "gemini" else "gpt-4o-mini"

    rows_a = by_question(load_jsonl(Path(args.predictions_a)))
    rows_b = by_question(load_jsonl(Path(args.predictions_b)))
    questions = [q for q in rows_a if q in rows_b]
    if args.limit is not None:
        questions = questions[: args.limit]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    counts = {
        "comprehensiveness": init_counts(),
        "diversity": init_counts(),
        "temporal_coverage": init_counts(),
        "overall_winner": init_counts(),
    }
    failed = 0
    start = time.perf_counter()

    with output_path.open("w", encoding="utf-8") as out:
        for idx, question in enumerate(questions, start=1):
            one_start = time.perf_counter()
            print(f"[{idx}/{len(questions)}] pairwise {question[:100]}")
            try:
                judgment, usage = judge_pair(
                    question=question,
                    answer_a=rows_a[question].get("prediction", ""),
                    answer_b=rows_b[question].get("prediction", ""),
                    provider=args.judge_provider,
                    model=args.judge_model,
                )
                status = "ok"
            except Exception as exc:
                judgment = {
                    "comprehensiveness": "TIE",
                    "diversity": "TIE",
                    "temporal_coverage": "TIE",
                    "overall_winner": "TIE",
                    "reasoning": f"Judge error: {exc}",
                }
                usage = {}
                status = "error"
                failed += 1

            for key in counts:
                winner = normalize_winner(judgment.get(key, "TIE"))
                judgment[key] = winner
                counts[key][winner] += 1

            result = {
                "question": question,
                "name_a": args.name_a,
                "name_b": args.name_b,
                "answer_a": rows_a[question].get("prediction", ""),
                "answer_b": rows_b[question].get("prediction", ""),
                "status": status,
                "elapsed_seconds": round(time.perf_counter() - one_start, 3),
                "judge_provider": args.judge_provider,
                "judge_model": args.judge_model,
                "usage": usage,
                "judgment": judgment,
            }
            out.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            out.flush()
            print(f"[winner] overall={judgment['overall_winner']} time={result['elapsed_seconds']:.2f}s status={status}")

    total = max(len(questions), 1)
    summary = {
        "name_a": args.name_a,
        "name_b": args.name_b,
        "num_pairs": len(questions),
        "failed": failed,
        "win_rates": {
            key: {
                args.name_a: value["A"] / total,
                args.name_b: value["B"] / total,
                "tie": value["TIE"] / total,
            }
            for key, value in counts.items()
        },
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "output": str(output_path),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
