# TurboQuant Intervention Modes (CLI Runbook)

Mục tiêu tài liệu này: làm rõ **TurboQuant có thể can thiệp từng phần** (không bắt buộc all-or-nothing), và cung cấp lệnh CLI cụ thể theo từng mode.

---

## 1. Kết luận nhanh

- Có thể chạy **Build-only local LLM**: tối ưu indexing/update.
- Có thể chạy **Query-only local LLM**: tối ưu latency khi trả lời.
- Có thể chạy **Build+Query local LLM**: đánh giá end-to-end tối ưu TG-RAG.
- Có thể chạy **Hybrid (judge external)**: pipeline chính local, chấm điểm bằng model ngoài (Gemini/OpenAI) để giảm bias.

---

## 2. Tham số CLI cốt lõi

### 2.1 Build (`build_graph.py`)

Các tham số quan trọng để bật local LLM TurboQuant:

- `--local_llm_backend turboquant`
- `--model <llama-server alias>`
- `--base_url http://localhost:8080/v1`
- `--llm_max_async <n>`
- `--llm_timeout <seconds>`

Embedding nên giữ cố định khi so benchmark:

- `--embedding_provider ...`
- `--embedding_model ...`
- `--embedding_dim ...`
- `--embedding_device ...`
- `--embedding_batch_size ...`
- `--embedding_max_async ...`

### 2.2 Query (`query_graph.py`)

Các tham số quan trọng:

- `--working_dir <graph_output_dir>`
- `--question "..."`
- `--mode local|global|naive`
- `--local_llm_backend turboquant`
- `--model <llama-server alias>`
- `--base_url http://localhost:8080/v1`
- `--llm_max_async <n>`
- `--llm_timeout <seconds>`

---

## 3. Chế độ 1 — Build-only local LLM

Dùng khi mục tiêu là đo giảm thời gian build/index/update nhờ TurboQuant.

```bash
python -u build_graph.py \
  --output_dir outputs/build_graph/BUILD_tq_build_only \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 100 \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_device cpu \
  --embedding_batch_size 16 \
  --embedding_max_async 1 \
  --llm_max_async 2 \
  --llm_timeout 900
```

---

## 4. Chế độ 2 — Query-only local LLM

Dùng khi graph đã build sẵn, mục tiêu là đo latency/query throughput khi inference.

```bash
python -u query_graph.py \
  --working_dir outputs/build_graph/BUILD_baseline_graph \
  --question "What was Western Digital's revenue in 2023 Q1 to Q3?" \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 1 \
  --llm_timeout 600
```

---

## 5. Chế độ 3 — Build + Query local LLM (khuyến nghị cho claim end-to-end)

Dùng khi mục tiêu nghiên cứu là: **"TurboQuant optimize TG-RAG"** một cách đầy đủ.

Bước 1: build bằng local TurboQuant (như mục 3).

Bước 2: query batch bằng local TurboQuant:

```bash
python -u scripts/eval/run_batch_queries.py \
  --working_dir outputs/build_graph/BUILD_tq_e2e \
  --questions ect-qa/dataset/specific_qa.jsonl \
  --output results/preds/pred_tq_e2e_specific_local.jsonl \
  --mode local \
  --local_llm_backend turboquant \
  --llm_model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
  --llm_base_url http://localhost:8080/v1 \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --llm_max_async 1 \
  --llm_timeout 600
```

> Ghi chú: `run_batch_queries.py` hiện hỗ trợ `--local_llm_backend` với giá trị `normal|turboquant`, và thêm `--embedding_provider huggingface` để query cùng embedding backend với build.

---

## 6. Chế độ 4 — Hybrid (judge external)

Dùng khi muốn giảm bias đánh giá:

- Pipeline build/query chạy local TurboQuant.
- Judge dùng Gemini/OpenAI.

Specific judge:

```bash
python -u scripts/eval/judge_specific.py \
  --predictions results/preds/pred_tq_e2e_specific_local.jsonl \
  --output results/judged/judged_tq_e2e_specific_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

Pairwise abstract judge:

```bash
python -u scripts/eval/judge_pairwise_abstract.py \
  --predictions_a results/preds/pred_tq_e2e_abstract_local.jsonl \
  --predictions_b results/preds/pred_baseline_abstract.jsonl \
  --name_a turboquant \
  --name_b baseline \
  --output results/judged/pairwise_tq_vs_base_abstract_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

---

## 7. Vì sao cấu hình dễ "phức tạp"?

Vì có nhiều lớp độc lập:

1. LLM runtime cho generation (TurboQuant vs non-TurboQuant),
2. Embedding runtime,
3. Query mode (`local/global/naive`),
4. Judge runtime (nếu dùng LLM-as-a-Judge).

Nếu không cố định các lớp còn lại, rất dễ so sánh sai biến.

---

## 8. Setup tối giản khuyến nghị (để claim đúng mục tiêu)

Nếu mục tiêu là **TurboQuant optimize TG-RAG**:

1. Cố định dataset + config retrieval + embedding.
2. Chỉ thay biến LLM chính: baseline vs TurboQuant.
3. Chạy cả build + query local cho bản TurboQuant.
4. Judge bằng external model độc lập.
5. Báo cáo đồng thời quality + efficiency + production metrics (p95/p99, TTFT, bootstrap CI, disagreement).

---

## 9. Checklist trước khi chạy

- [ ] `llama-server` đang chạy và truy cập được `http://localhost:8080/v1`.
- [ ] Alias model truyền vào `--model` hoặc `--llm_model` khớp server.
- [ ] `--working_dir` query trỏ đúng output build.
- [ ] Embedding config được giữ cố định giữa các nhánh so sánh.
- [ ] Nếu dùng judge external, `.env` có khóa API tương ứng (`GOOGLE_API_KEY` hoặc `OPENAI_API_KEY`).
