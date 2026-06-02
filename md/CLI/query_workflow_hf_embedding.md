# Query Workflow Sau Khi Build Xong Bằng HF Embedding

Tài liệu này dành riêng cho case của bạn:

- graph đã build bằng `huggingface` embedding
- LLM local chạy qua `llama-server` trong repo `llama-cpp-turboquant`
- bạn muốn dùng đúng `working_dir` output để query bằng:
  - local TurboQuant
  - Gemini

File này ngắn và ưu tiên copy lệnh.

Lưu ý với code hiện tại:

- `query_graph.py`, `run_batch_queries.py` và demo đã biết đọc `build_manifest.json` nếu output có file này
- nhưng các output cũ như `fresh_v2` hoặc build đang chạy từ code cũ thường chưa có manifest
- vì vậy với output cũ, bạn vẫn nên truyền rõ HF embedding args trong các lệnh mẫu bên dưới

---

## 1. Khi nào dùng file này

Dùng file này nếu build của bạn có dạng như:

```text
outputs/build_graph/BUILD_qwen25_7b_*_hf_nomic_* 
```

Ví dụ:

```text
outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2
outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3
```

Không dùng file này cho:

- graph build bằng `ollama` embedding
- workflow export Neo4j
- benchmark `global` cuối cùng nếu build artifact còn lỗi community

---

## 2. Điều kiện trước khi query

Bạn cần chờ build tmux chạy xong hẳn.

Ít nhất phải kiểm tra 3 thứ:

1. tmux session build đã kết thúc hoặc không còn log mới
2. output folder đã xuất hiện đủ file
3. `llama-server` vẫn đang sống nếu bạn muốn query local

### 2.1 Kiểm tra build đã xong chưa

```bash
tmux ls
```

Nếu bạn biết tên session build:

```bash
tmux capture-pane -pt <BUILD_SESSION> | tail -n 120
```

Bạn cần thấy build đi đến cuối và không còn tiếp tục ghi thêm log.

### 2.2 Kiểm tra output folder

Đặt biến trước:

```bash
WORKDIR=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3
```

Sau đó kiểm tra:

```bash
ls -la "$WORKDIR"
```

Bạn kỳ vọng có:

- `graph_chunk_entity_relation.graphml`
- `graph_temporal_hierarchy.graphml`
- `kv_store_full_docs.json`
- `kv_store_text_chunks.json`
- `kv_store_community_reports.json`
- `vdb_entities.json`
- `vdb_relations.json`

### 2.3 Nếu build còn lỗi community thì sao

Nếu `kv_store_community_reports.json` còn có `Error Report for Unknown`, thì:

- vẫn dùng được để debug `local query`
- vẫn dùng được để so `TurboQuant vs Gemini` trên cùng graph
- chưa nên dùng để chốt `global query` hay benchmark end-to-end cuối

---

## 3. Chuẩn bị môi trường query

```bash
eval "$(conda shell.bash hook)"
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
```

Với local `llama-server`:

```bash
export OPENAI_API_KEY=dummy
export OPENAI_BASE_URL=http://localhost:8080/v1
```

---

## 4. Kiểm tra local `llama-server`

Đặt biến:

```bash
MODEL_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072
BASE_URL=http://localhost:8080/v1
```

Kiểm tra:

```bash
curl -sS "$BASE_URL/models"
```

Alias trong output phải khớp `MODEL_ALIAS` bạn sẽ truyền lúc query.

---

## 5. Canonical rule cho HF embedding

Nếu graph build bằng:

```text
embedding_provider = huggingface
embedding_model = nomic-ai/nomic-embed-text-v1.5
```

thì khi query bằng CLI, bạn nên giữ:

```text
--embedding_provider huggingface
--embedding_model nomic-ai/nomic-embed-text-v1.5
```

Và nên dùng:

- build/index: `search_document: `
- query: `search_query: `

Điểm quan trọng:

```text
Bạn có thể đổi LLM trả lời giữa TurboQuant và Gemini.
Nhưng retrieval embedding nên giữ cố định nếu muốn so sánh sạch.
```

---

## 6. Query local bằng TurboQuant trên chính output đã build

### 6.1 Single question

```bash
python query_graph.py \
  --question "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?" \
  --working_dir "$WORKDIR" \
  --mode local \
  --local_llm_backend turboquant \
  --model "$MODEL_ALIAS" \
  --base_url "$BASE_URL" \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --embedding_prefix "search_query: " \
  --llm_max_async 1 \
  --llm_timeout 900 \
  --show_retrieval
```

### 6.2 Ý nghĩa

- `working_dir`: trỏ đúng graph output
- `local_llm_backend turboquant`: LLM trả lời lấy từ local `llama-server`
- `embedding_provider huggingface`: retrieval vẫn bám đúng embedding space đã dùng lúc build

---

## 7. Query cùng graph nhưng dùng Gemini làm generator

### 7.1 Single question

```bash
python query_graph.py \
  --question "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?" \
  --working_dir "$WORKDIR" \
  --mode local \
  --provider gemini \
  --model gemini-2.5-flash \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --embedding_prefix "search_query: " \
  --show_retrieval
```

### 7.2 Ý nghĩa

Ở đây:

- graph vẫn là cùng một `working_dir`
- retrieval vẫn là HF Nomic
- chỉ đổi generator từ local TurboQuant sang Gemini

Đây là cách so sánh sạch nhất trước khi patch code query.

---

## 8. Batch ECT-QA bằng local TurboQuant

### 8.1 Local set

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir "$WORKDIR" \
  --questions ect-qa/questions/local_new.jsonl \
  --output results/preds/pred_v3_turboquant_hf_local_new.jsonl \
  --mode local \
  --local_llm_backend turboquant \
  --llm_model "$MODEL_ALIAS" \
  --llm_base_url "$BASE_URL" \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --embedding_prefix "search_query: " \
  --llm_max_async 1 \
  --llm_timeout 900
```

### 8.2 Nếu muốn resume

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir "$WORKDIR" \
  --questions ect-qa/questions/local_new.jsonl \
  --output results/preds/pred_v3_turboquant_hf_local_new.jsonl \
  --mode local \
  --local_llm_backend turboquant \
  --llm_model "$MODEL_ALIAS" \
  --llm_base_url "$BASE_URL" \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --embedding_prefix "search_query: " \
  --llm_max_async 1 \
  --llm_timeout 900 \
  --resume
```

---

## 9. Batch ECT-QA cùng graph nhưng dùng Gemini

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir "$WORKDIR" \
  --questions ect-qa/questions/local_new.jsonl \
  --output results/preds/pred_v3_gemini_hf_local_new.jsonl \
  --mode local \
  --provider gemini \
  --model gemini-2.5-flash \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --embedding_prefix "search_query: "
```

---

## 10. Demo dùng thế nào cho đúng

Kết luận phải nói rõ:

```text
demo hiện tại dùng được để smoke test tương tác,
chưa nên dùng để benchmark nghiêm túc với graph build bằng HF embedding.
```

Lý do:

- demo chưa ép query-time embedding bám đúng build-time embedding
- demo chưa có manifest build
- demo hiện dễ làm người dùng tưởng chỉ đổi LLM, nhưng thực tế retrieval runtime có thể bị lệch

### 10.1 Nếu vẫn muốn dùng demo để test nhanh

Điền tối thiểu:

- `Provider`: `openai`
- `Model`: đúng `MODEL_ALIAS`
- `Base URL`: `http://localhost:8080/v1`
- `Working Directory`: đúng `WORKDIR`
- `Query Mode`: `local`

Và nhớ:

```text
Kết quả demo chỉ nên coi là smoke test UI/runtime,
không nên coi là metric benchmark cuối cho HF-built graph.
```

---

## 11. Bạn đang chờ build `v3` xong thì nên làm gì

Thứ tự hợp lý:

1. chờ build `v3` xong
2. kiểm tra `WORKDIR`
3. chạy single query local TurboQuant
4. chạy single query Gemini trên cùng graph
5. chạy batch ECT-QA local
6. sau đó mới quyết định có cần patch query branch ngay hay không

Nếu mục tiêu của bạn là ưu tiên fix query branch trước, thì `v3` output này vẫn dùng được để:

- test `query_graph.py`
- test `run_batch_queries.py`
- so generator TurboQuant vs Gemini

Bạn không cần rebuild lại chỉ để bắt đầu debug local query path.
