# Metric Pipeline Runbook for Temporal-GraphRAG-Turboquant

Tài liệu này mô tả **cách chấm metric sau khi query xong**, không phải build graph.
Luồng đúng là:

1. Build graph
2. Query graph
3. Lấy prediction JSONL
4. Chạy metric runner / judge scripts
5. Lưu kết quả để so sánh, kiểm tra, và viết report

Trước khi chạy CLI, dùng:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant
```

Nếu terminal đã hiện `(turboquant)` thì chỉ cần `cd` vào repo là đủ.

---

## 1) Phân vai giữa các lớp file

### Input để chấm

- `results/preds/*.jsonl`

Đây là raw predictions từ CLI query. File này chứa câu hỏi, prediction, answer, thời gian chạy, và metadata retrieval.

### Output sau khi chấm

- `results/metrics/**`
- `results/judged/**`

`results/metrics/**` chứa summary cuối cùng.  
`results/judged/**` chứa file chấm chi tiết theo từng câu.

### Log để đối chiếu

- `logs/metrics/**`

Log này dùng để kiểm tra run nào ra kết quả gì, và để so sánh giữa các experiment.

---

## 2) Metric gốc của TG-RAG

Theo paper TG-RAG, các metric gốc trên ECT-QA là:

### 2.0 Sáu nhóm metric tổng thể

Để tránh nhầm lẫn, toàn bộ evaluation được chia thành **6 nhóm**:

#### Nhóm theo paper (4 nhóm)

1. **Specific QA**
2. **Abstract QA**
3. **Incremental Evaluation**
4. **Ablation / Component Contribution**

#### Nhóm bổ sung cho TurboQuant (2 nhóm)

5. **Efficiency / Runtime**: latency, p95/p99, TTFT, tokens/sec, build/update time
6. **Reliability / Stability**: VRAM peak, overflow count, retry count, judge disagreement, CI

Trong đó:

- Nhóm 1–4 bám sát paper và đánh giá chất lượng TG-RAG.
- Nhóm 5–6 là metric triển khai local để đo trade-off của TurboQuant.
- Với nhóm quality chính, ưu tiên Gemini judge thay vì để local LLM tự chấm.

### Specific QA

- `Correct`
- `Refusal`
- `Incorrect`
- `ROUGE-L`
- `F1`

### Abstract QA

- `Comprehensiveness`
- `Diversity`
- `Temporal Coverage`
- `Overall Winner`

### Incremental evaluation

- Base queries on base corpus
- Base queries on updated corpus
- New queries on updated corpus
- Update cost / indexing cost

### Ablation

- Temporal Retrieval
- PPR Ranking
- Temporal Indexing

---

## 3) Metric bổ sung khi dùng TurboQuant

Nhóm này không thay thế metric gốc của paper. Nó chỉ bổ sung để đo trade-off hiệu năng.

- latency mean
- p95 / p99 latency
- TTFT
- tokens/sec
- VRAM peak
- API error count
- overflow count
- retry count

### 3.1 Reliability / agreement

Nếu chạy nhiều lần hoặc nhiều judge backend, nên lưu thêm:

- judge disagreement rate
- bootstrap CI cho win-rate / F1
- variance giữa các lần chạy

---

## 4) Cây thư mục khuyến nghị cho mỗi run

```text
outputs/build_graph/<BUILD_CASE>/
results/preds/<PRED_FILE>.jsonl
results/judged/<JUDGED_FILE>.jsonl
results/metrics/metric_suite/<RUN_ID>/
logs/metrics/<RUN_ID>.log
```

Mỗi run nên để lại ít nhất:

- một file summary JSON
- một file detail JSONL
- một log file
- một manifest JSON

---

## 5) Script mới để chạy metric summary

File này được thiết kế để chấm **non-LLM metrics** và compare 2 prediction files.

### Script

- `scripts/eval/run_metric_suite.py`

### Script orchestration one-shot

- `scripts/eval/run_metric_pipeline.py`

### Nó làm gì

- đọc một hoặc nhiều file prediction JSONL
- tính `F1` và `ROUGE-L`
- ghi summary JSON + detail JSONL
- nếu bật compare, so sánh hai file trên các câu hỏi giao nhau
- ghi manifest + log để tái kiểm tra sau này

`run_metric_pipeline.py` thì làm nhiệm vụ điều phối nhiều nhóm chạy trong cùng một lệnh:

- specific non-LLM metrics
- specific Gemini/OpenAI judge
- abstract pairwise judge (nếu có 2 file abstract)

### Nó không làm gì

- không build graph
- không query model
- không gọi Gemini/OpenAI judge

Phần judge LLM đã có script riêng:

- `scripts/eval/judge_specific.py`
- `scripts/eval/judge_pairwise_abstract.py`

---

## 6) CLI cho 2 file query hiện có

Giả sử bạn muốn so sánh hai kết quả query gần nhất:

- `results/preds/pred_ctx24k_v2_hf_local384.jsonl`
- `results/preds/pred_fresh_v2_hf_local10.jsonl`

Chạy:

```bash
python -u scripts/eval/run_metric_suite.py \
  --predictions \
  results/preds/pred_ctx24k_v2_hf_local384.jsonl \
  results/preds/pred_fresh_v2_hf_local10.jsonl \
  --output_root results/metrics/metric_suite \
  --compare
```

Nếu muốn giữ cả câu unanswerable trong thống kê:

```bash
python -u scripts/eval/run_metric_suite.py \
  --predictions \
  results/preds/pred_ctx24k_v2_hf_local384.jsonl \
  results/preds/pred_fresh_v2_hf_local10.jsonl \
  --output_root results/metrics/metric_suite \
  --compare \
  --include_unanswerable
```

### Chạy toàn bộ nhóm trong một lệnh

Khi bạn đã có đủ input cho các nhóm, chạy một lệnh kiểu:

```bash
python -u scripts/eval/run_metric_pipeline.py \
  --all \
  --specific_predictions \
  results/preds/pred_ctx24k_v2_hf_local384.jsonl \
  results/preds/pred_fresh_v2_hf_local10.jsonl \
  --judge_provider gemini \
  --output_root results/metrics/pipeline
```

Nếu sau này bạn có thêm 2 file abstract prediction, chỉ cần thêm:

```bash
  --abstract_predictions_a results/preds/<abstract_a>.jsonl \
  --abstract_predictions_b results/preds/<abstract_b>.jsonl
```

Khi đó một lệnh sẽ chạy hết các nhóm đã khai báo.

### Phạm vi tự động hóa hiện tại

- **Đã tự động hóa tốt**: Specific QA, non-LLM summary, Gemini judge cho specific, Gemini pairwise cho abstract khi có đủ input.
- **Chưa gom vào một lệnh chung**: Incremental Evaluation và Ablation, vì hai nhóm này cần build/update setup riêng.
- **TurboQuant extras**: Efficiency / Runtime và Reliability / Stability lấy từ prediction JSONL + log, rồi tổng hợp bằng runbook metrics.

---

## 12) Chạy Gemini judge theo batch để tránh quota

Nếu bạn lo bị `RESOURCE_EXHAUSTED` hoặc rate limit, cách an toàn nhất là chạy Gemini judge theo đợt nhỏ bằng `--limit`, rồi dùng `--resume` để nối tiếp.

### 12.1 Specific QA: chạy từng batch

Ví dụ batch 20 câu đầu tiên:

```bash
python -u scripts/eval/judge_specific.py \
  --predictions results/preds/pred_ctx24k_v2_hf_local384.jsonl \
  --output results/judged/pred_ctx24k_v2_hf_local384_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite \
  --limit 20
```

Chạy tiếp batch sau trên **cùng output file**:

```bash
python -u scripts/eval/judge_specific.py \
  --predictions results/preds/pred_ctx24k_v2_hf_local384.jsonl \
  --output results/judged/pred_ctx24k_v2_hf_local384_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite \
  --limit 20 \
  --resume
```

Muốn chạy theo nhiều đợt hơn, tăng `--limit` lên 50/100 tùy quota. Ý tưởng là:

- chạy một batch nhỏ
- chờ quota hồi lại nếu cần
- chạy lại với `--resume`

### 12.2 Abstract QA: chạy từng batch

`judge_pairwise_abstract.py` cũng có `--limit`, nên có thể chia nhỏ nếu abstract set lớn:

```bash
python -u scripts/eval/judge_pairwise_abstract.py \
  --predictions_a results/preds/<abstract_a>.jsonl \
  --predictions_b results/preds/<abstract_b>.jsonl \
  --name_a turboquant \
  --name_b baseline \
  --output results/judged/pairwise_abstract_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite \
  --limit 20
```

### 12.3 Nên dùng cách nào?

- **Muốn nhanh và ít risk quota**: chạy batch nhỏ 20/50 câu.
- **Muốn tổng kết đầy đủ**: dùng `--resume` cho specific và chạy nhiều đợt cho tới hết.
- **Muốn chỉ kiểm tra chất lượng**: không cần chấm toàn bộ, lấy mẫu 20–50 câu cũng đủ nhìn xu hướng ban đầu.

### 12.4 Ba mức chạy nhanh để copy-paste

Nếu bạn muốn chọn ngay một mức chạy, dùng các mốc này:

- **Mini check**: `--limit 20`
- **Batch vừa**: `--limit 50`
- **Batch lớn**: `--limit 100`

Gợi ý thao tác:

1. Chạy `--limit 20` trước để test prompt, auth, và output schema.
2. Nếu ổn thì tăng lên `--limit 50` để lấy mẫu đáng kể hơn.
3. Nếu quota còn tốt thì lên `--limit 100` và dùng `--resume` khi cần nối tiếp.

Ví dụ thực tế cho specific QA:

```bash
python -u scripts/eval/judge_specific.py \
  --predictions results/preds/pred_ctx24k_v2_hf_local384.jsonl \
  --output results/judged/pred_ctx24k_v2_hf_local384_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite \
  --limit 50
```

Khi cần nối tiếp batch kế tiếp:

```bash
python -u scripts/eval/judge_specific.py \
  --predictions results/preds/pred_ctx24k_v2_hf_local384.jsonl \
  --output results/judged/pred_ctx24k_v2_hf_local384_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite \
  --limit 50 \
  --resume
```

---

## 7) Output sẽ nằm ở đâu

Sau khi chạy, runner sẽ tự tạo một thư mục run dạng:

```text
results/metrics/metric_suite/<TIMESTAMP>_compare/
```

Bên trong sẽ có:

- `pred_ctx24k_v2_hf_local384_nonllm.json`
- `pred_ctx24k_v2_hf_local384_nonllm.jsonl`
- `pred_fresh_v2_hf_local10_nonllm.json`
- `pred_fresh_v2_hf_local10_nonllm.jsonl`
- `comparison_overlap.json`
- `comparison_overlap.jsonl`
- `manifest.json`

Và log sẽ ở:

- `logs/metrics/<TIMESTAMP>_compare.log`

---

## 8) Cách đọc metric output

### Summary JSON

Mỗi file summary có các trường chính:

- `num_rows`
- `num_scored`
- `f1`
- `rouge_l`

### Comparison JSON

File compare có:

- `num_overlap_questions`
- `same_prediction_count`
- `better_a_count_f1`
- `better_b_count_f1`
- `mean_delta_f1`
- `mean_delta_rouge_l`

### Detail JSONL

Mỗi dòng có:

- question
- answer
- prediction_a / prediction_b
- f1_a / f1_b
- rouge_l_a / rouge_l_b
- delta_f1 / delta_rouge_l

Đây là file quan trọng nhất nếu bạn muốn debug tại sao một run tốt hơn run kia.

---

## 11) Full command theo nhóm

### Nhóm specific: non-LLM metrics

```bash
python -u scripts/eval/run_metric_suite.py \
  --predictions \
  results/preds/pred_ctx24k_v2_hf_local384.jsonl \
  results/preds/pred_fresh_v2_hf_local10.jsonl \
  --output_root results/metrics/metric_suite \
  --compare
```

### Nhóm specific: Gemini judge

```bash
python -u scripts/eval/judge_specific.py \
  --predictions results/preds/pred_ctx24k_v2_hf_local384.jsonl \
  --output results/judged/pred_ctx24k_v2_hf_local384_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite

python -u scripts/eval/judge_specific.py \
  --predictions results/preds/pred_fresh_v2_hf_local10.jsonl \
  --output results/judged/pred_fresh_v2_hf_local10_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

### Nhóm abstract: Gemini pairwise judge

```bash
python -u scripts/eval/judge_pairwise_abstract.py \
  --predictions_a results/preds/<abstract_a>.jsonl \
  --predictions_b results/preds/<abstract_b>.jsonl \
  --name_a turboquant \
  --name_b baseline \
  --output results/judged/pairwise_abstract_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

### Một lệnh chạy hết các nhóm

```bash
python -u scripts/eval/run_metric_pipeline.py \
  --all \
  --specific_predictions \
  results/preds/pred_ctx24k_v2_hf_local384.jsonl \
  results/preds/pred_fresh_v2_hf_local10.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite \
  --output_root results/metrics/pipeline
```

Nếu chưa có abstract prediction files thì lệnh trên vẫn chạy phần specific; phần abstract chỉ bật khi bạn truyền đủ 2 file abstract.

---

## 9) Nếu muốn chấm LLM judge sau này

Khi có API key cho judge, chạy riêng hai script sau:

- `scripts/eval/judge_specific.py`
- `scripts/eval/judge_pairwise_abstract.py`

Ví dụ cụ thể sẽ phụ thuộc vào question split:

- specific QA → `judge_specific.py`
- abstract QA → `judge_pairwise_abstract.py`

Nếu môi trường không có key, chỉ chạy non-LLM metrics trước là đủ để có baseline comparison.

---

## 10) Quy ước report tối thiểu

Khi viết báo cáo, nên ghi rõ:

1. Input prediction file nào
2. Query mode gì
3. Build case nào
4. Non-LLM metric nào
5. Log file ở đâu
6. Comparison summary ở đâu

Điều này giúp bạn tránh lẫn giữa raw prediction, judged file, và metric summary.

---

## 12) Troubleshooting Gemini judge

Nếu `judge_specific.py` hoặc `judge_pairwise_abstract.py` báo lỗi kiểu:

- `API key expired`
- `API_KEY_INVALID`

thì cần:

1. Cập nhật lại `GOOGLE_API_KEY` hoặc `GEMINI_API_KEY` trong `.env`
2. Chạy lại pipeline judge

Các output lỗi vẫn được giữ trong `results/judged/**` và log trong `logs/metrics/pipeline/**`, nên bạn có thể dùng chúng để debug, nhưng để có kết quả judge thật thì cần key hợp lệ.
