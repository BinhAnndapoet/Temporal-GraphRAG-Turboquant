# TG-RAG Metrics Execution Runbook (TurboQuant)

Tài liệu này hướng dẫn cách chạy và xuất kết quả metrics theo quy trình nhất quán, gồm:

1. Prediction generation,
2. Specific metrics (LLM + non-LLM),
3. Abstract pairwise metrics,
4. Production-grade metrics (p95/p99 latency, TTFT, tokens/sec generation),
5. Bootstrap CI cho win-rate/F1,
6. Judge disagreement rate.

---

## 1. Chuẩn bị thư mục output

```bash
mkdir -p results/preds results/judged results/metrics results/reports
```

---

## 2. Sinh prediction batch

Ví dụ chạy local mode với TurboQuant backend:

```bash
python -u scripts/eval/run_batch_queries.py \
  --working_dir outputs/build_graph/BUILD_tq_e2e \
  --questions ect-qa/dataset/specific_qa.jsonl \
  --output results/preds/pred_tq_specific_local.jsonl \
  --mode local \
  --local_llm_backend turboquant \
  --llm_model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
  --llm_base_url http://localhost:8080/v1 \
  --embedding_provider ollama \
  --embedding_model nomic-embed-text \
  --embedding_dim 768 \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600
```

> File output đã chứa `elapsed_seconds`, `query_call_seconds`, `status` cho từng câu.

---

## 3. Tính non-LLM metrics (F1, ROUGE-L)

```bash
python -u scripts/eval/metrics_nonllm.py \
  --predictions results/preds/pred_tq_specific_local.jsonl \
  --output results/metrics/nonllm_tq_specific_local.json
```

---

## 4. Tính Specific LLM-as-a-Judge (Correct/Refusal/Incorrect)

```bash
python -u scripts/eval/judge_specific.py \
  --predictions results/preds/pred_tq_specific_local.jsonl \
  --output results/judged/judged_tq_specific_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

---

## 5. Tính Abstract pairwise metrics

```bash
python -u scripts/eval/judge_pairwise_abstract.py \
  --predictions_a results/preds/pred_tq_abstract_local.jsonl \
  --predictions_b results/preds/pred_baseline_abstract.jsonl \
  --name_a turboquant \
  --name_b baseline \
  --output results/judged/pairwise_tq_vs_base_abstract_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

---

## 6. Production-grade latency metrics: mean + p95 + p99

Từ file prediction JSONL (`elapsed_seconds`), tính thêm p95/p99:

```bash
python - <<'PY'
import json, statistics
from pathlib import Path

path = Path('results/preds/pred_tq_specific_local.jsonl')
vals = []
with path.open('r', encoding='utf-8') as f:
    for line in f:
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get('status') == 'ok':
            vals.append(float(row.get('elapsed_seconds', 0.0)))

if not vals:
    raise SystemExit('No successful rows to summarize')

vals_sorted = sorted(vals)

def pct(a, p):
    k = (len(a)-1) * p
    f = int(k)
    c = min(f+1, len(a)-1)
    if f == c:
        return a[f]
    return a[f] + (a[c]-a[f]) * (k-f)

summary = {
    'n_ok': len(vals),
    'latency_mean': statistics.fmean(vals),
    'latency_p95': pct(vals_sorted, 0.95),
    'latency_p99': pct(vals_sorted, 0.99),
}
print(json.dumps(summary, indent=2))
out = Path('results/metrics/latency_summary_tq_specific_local.json')
out.write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(f'[saved] {out}')
PY
```

---

## 7. TTFT và generation tokens/sec

Nếu API/log có `t_first_token`, `t_last_token`, `output_tokens`, dùng công thức:

- `TTFT = t_first_token - t_request_start`
- `Tokens/sec_gen = output_tokens / (t_last_token - t_first_token)`

Mẫu tính khi đã có các field trên trong JSONL:

```bash
python - <<'PY'
import json, statistics
from pathlib import Path

path = Path('results/preds/pred_tq_specific_local.jsonl')
ttft = []
tps = []
for line in path.read_text(encoding='utf-8').splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    if row.get('status') != 'ok':
        continue
    if all(k in row for k in ['t_request_start','t_first_token','t_last_token','output_tokens']):
        t0 = float(row['t_request_start'])
        t1 = float(row['t_first_token'])
        t2 = float(row['t_last_token'])
        n  = float(row['output_tokens'])
        if t1 > t0:
            ttft.append(t1 - t0)
        if t2 > t1:
            tps.append(n / (t2 - t1))

summary = {
    'n_ttft': len(ttft),
    'ttft_mean': statistics.fmean(ttft) if ttft else None,
    'n_tps': len(tps),
    'tokens_per_sec_gen_mean': statistics.fmean(tps) if tps else None,
}
print(json.dumps(summary, indent=2))
out = Path('results/metrics/ttft_tps_summary_tq_specific_local.json')
out.write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(f'[saved] {out}')
PY
```

> Nếu output hiện tại chưa có 4 field thời gian/token này, cần bổ sung instrumentation ở script query để đo TTFT đúng nghĩa.

---

## 8. Bootstrap CI (95%) cho F1 / win-rate

### 8.1 Bootstrap CI cho F1 từ file non-LLM chi tiết

```bash
python - <<'PY'
import json, random
from pathlib import Path

inp = Path('results/metrics/nonllm_tq_specific_local.json')
obj = json.loads(inp.read_text(encoding='utf-8'))
items = obj.get('items', [])
vals = [float(x['f1']) for x in items]
if not vals:
    raise SystemExit('No F1 values found')

B = 2000
means = []
rng = random.Random(42)
n = len(vals)
for _ in range(B):
    sample = [vals[rng.randrange(n)] for _ in range(n)]
    means.append(sum(sample)/n)
means.sort()
lo = means[int(0.025*B)]
hi = means[int(0.975*B)]
out = {
    'metric': 'f1',
    'mean': sum(vals)/n,
    'ci95': [lo, hi],
    'B': B,
    'n': n,
}
print(json.dumps(out, indent=2))
Path('results/metrics/bootstrap_ci_f1_tq_specific_local.json').write_text(
    json.dumps(out, indent=2), encoding='utf-8')
PY
```

### 8.2 Bootstrap CI cho overall win-rate (A thắng)

```bash
python - <<'PY'
import json, random
from pathlib import Path

path = Path('results/judged/pairwise_tq_vs_base_abstract_gemini.jsonl')
wins = []
for line in path.read_text(encoding='utf-8').splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    j = row.get('judgment', {})
    wins.append(1.0 if str(j.get('overall_winner','TIE')).upper() == 'A' else 0.0)

if not wins:
    raise SystemExit('No pairwise rows found')

B = 2000
rng = random.Random(42)
n = len(wins)
boot = []
for _ in range(B):
    sample = [wins[rng.randrange(n)] for _ in range(n)]
    boot.append(sum(sample)/n)
boot.sort()
out = {
    'metric': 'overall_win_rate_A',
    'mean': sum(wins)/n,
    'ci95': [boot[int(0.025*B)], boot[int(0.975*B)]],
    'B': B,
    'n': n,
}
print(json.dumps(out, indent=2))
Path('results/metrics/bootstrap_ci_overall_winrate_A.json').write_text(
    json.dumps(out, indent=2), encoding='utf-8')
PY
```

---

## 9. Judge disagreement rate (đa-judge)

Chạy judge A và judge B trên cùng predictions, sau đó tính bất đồng:

```bash
python -u scripts/eval/judge_specific.py \
  --predictions results/preds/pred_tq_specific_local.jsonl \
  --output results/judged/judged_tq_specific_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

```bash
python -u scripts/eval/judge_specific.py \
  --predictions results/preds/pred_tq_specific_local.jsonl \
  --output results/judged/judged_tq_specific_openai.jsonl \
  --judge_provider openai \
  --judge_model gpt-4o-mini
```

Tính disagreement theo câu hỏi:

```bash
python - <<'PY'
import json
from pathlib import Path

def load(path):
    d = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        q = row.get('question')
        j = row.get('judgment', {})
        # So sánh theo bộ (correct/refusal/incorrect/total)
        d[q] = (
            int(j.get('correct_count', 0)),
            int(j.get('refusal_count', 0)),
            int(j.get('incorrect_count', 0)),
            int(j.get('total_count', 0)),
        )
    return d

A = load('results/judged/judged_tq_specific_gemini.jsonl')
B = load('results/judged/judged_tq_specific_openai.jsonl')
common = [q for q in A if q in B]
if not common:
    raise SystemExit('No overlapping questions between judge outputs')

dis = sum(1 for q in common if A[q] != B[q])
out = {
    'n_common': len(common),
    'disagreement_count': dis,
    'disagreement_rate': dis / len(common),
}
print(json.dumps(out, indent=2))
Path('results/metrics/judge_disagreement_specific.json').write_text(
    json.dumps(out, indent=2), encoding='utf-8')
PY
```

---

## 10. Mẫu báo cáo gộp cuối cùng

Nên tổng hợp tối thiểu các file:

- `results/metrics/nonllm_*.json`
- `results/metrics/latency_summary_*.json`
- `results/metrics/ttft_tps_summary_*.json` (nếu có field)
- `results/metrics/bootstrap_ci_*.json`
- `results/metrics/judge_disagreement_*.json`

Và trình bày theo 3 trục:

1. **Quality**: Correct/Refusal/Incorrect, F1, ROUGE-L, Temporal Coverage.
2. **Efficiency**: mean/p95/p99 latency, TTFT, generation tokens/sec, VRAM.
3. **Reliability**: bootstrap CI, judge disagreement rate.
