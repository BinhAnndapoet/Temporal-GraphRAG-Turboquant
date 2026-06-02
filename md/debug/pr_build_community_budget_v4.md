# PR Description: `fix/build-community-budget-v4`

## 1. Tiêu đề PR

```text
[codex] Fix local build community packing and runtime budget for TurboQuant
```

## 2. PR này xử lý vấn đề gì

PR này sửa nhánh build local của `Temporal-GraphRAG-Turboquant` khi chạy qua `llama-server` theo chuẩn OpenAI-compatible từ `llama-cpp-turboquant`.

Vấn đề cũ không phải chỉ do cấu hình. Nó là tổ hợp của:

1. lỗi logic trong phần pack temporal community report;
2. app không bám theo slot context thật của `llama-server`;
3. output build không ghi lại runtime metadata để query/demo bám theo.

Kết quả là các run kiểu `fresh_v2` và `v3` có thể:

- build xong một phần;
- vẫn ghi output;
- nhưng phase community đã hỏng và để lại `Error Report for ...`.

## 3. Root cause đã phân tích

### 3.1 `build_graph.py` cũ chỉ healthcheck server, không lấy slot context thật

Code cũ ở `main@2c93df6`:

```python
def xac_nhan_turboquant(base_url: str = None, strict: bool = False) -> bool:
    base_url = base_url or os.getenv("OPENAI_BASE_URL", "http://localhost:8080/v1")
    props_url = base_url.replace("/v1", "").rstrip("/") + "/props"

    try:
        with urllib.request.urlopen(props_url, timeout=3) as response:
            if response.status == 200:
                response.read()
                return True
```

Ý nghĩa của lỗi:

- code cũ chỉ check `/props` có trả `200` hay không;
- không đọc `default_generation_settings.n_ctx`;
- không biết mỗi slot còn bao nhiêu context thật sau khi chia `--parallel`;
- không tự hạ `best_model_max_token_size`.

Ví dụ với server:

```text
-c 131072 --parallel 2
```

thì slot context thật chỉ là:

```text
65536
```

chứ không phải `131072`.

Code mới:

```python
def fetch_server_props(...):
    ...

def _extract_slot_context_from_props(server_props):
    ...

def resolve_best_model_token_budget(...):
    safe_budget = max(1024, slot_tokens - headroom)
```

Nguồn code mới:

- [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:44)
- [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:163)

### 3.2 `build_graph.py` cũ không expose budget build và không ghi manifest

Code cũ ở `main@2c93df6` chỉ có các arg kiểu:

```python
parser.add_argument('--llm_max_async', ...)
parser.add_argument('--llm_timeout', ...)
parser.add_argument('--entity_extraction_timeout', ...)
```

Nhưng chưa có:

```python
--best_model_max_token_size
--community_token_headroom
```

và cũng chưa có `build_manifest.json`.

Code mới đã thêm:

```python
parser.add_argument('--best_model_max_token_size', ...)
parser.add_argument('--community_token_headroom', ...)
...
def write_build_manifest(graph_rag, build_status: str, error_message: str = None):
    ...
```

Nguồn code mới:

- [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:720)
- [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:786)

Ý nghĩa của fix:

- có thể override build budget từ CLI khi cần;
- app tự biết headroom an toàn;
- output build lưu lại model/provider/base_url/budget/embedding/runtime server.

### 3.3 `building.py` cũ truncate temporal edge theo sai field

Temporal edge row có layout:

```python
[id, timestamp, source, target, description, rank]
```

Code cũ ở `main@2c93df6`:

```python
edges_may_truncate_list_data = truncate_list_by_token_size(
    edges_list_data, key=lambda x: x[3], max_token_size=max_token_size // 2
)
```

Vấn đề:

- `x[3]` là `target`
- `x[4]` mới là `description`

Nên code cũ đo token theo tên `target`, không phải text `description`. Kết quả là app giữ lại quá nhiều edge text và prompt temporal community phình lên.

Code mới:

```python
edges_may_truncate_list_data = truncate_list_by_token_size(
    edges_list_data, key=lambda x: x[4], max_token_size=max_token_size // 2
)
```

Nguồn code mới:

- [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1412)

### 3.4 `building.py` cũ match temporal edge sai tuple khi fallback sub-community

Code cũ ở `main@2c93df6`:

```python
report_exclude_edges_list_data = [
    e for e in edges_list_data if (e[1], e[2]) not in contain_edges
]
report_include_edges_list_data = [
    e for e in edges_list_data if (e[1], e[2]) in contain_edges
]
```

Vấn đề:

- với temporal edge row, identity hợp lý phải là:

```python
(timestamp, source, target)
```

- nhưng code cũ chỉ match kiểu `(timestamp, source)`;
- fallback sub-community vì vậy có thể include/exclude edge sai.

Code mới:

```python
report_exclude_edges_list_data = [
    e for e in edges_list_data if (e[1], e[2], e[3]) not in contain_edges
]
report_include_edges_list_data = [
    e for e in edges_list_data if (e[1], e[2], e[3]) in contain_edges
]
```

Nguồn code mới:

- [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1442)

### 3.5 `building.py` cũ hardcode cách gọi LLM cho temporal community

Code cũ ở `main@2c93df6`:

```python
response = await use_llm_func(prompt, response_format={'type': 'json_object'})
```

Code mới:

```python
response = await use_llm_func(prompt, **llm_extra_kwargs)
```

Nguồn code mới:

- [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1963)

Ý nghĩa:

- temporal community report đi theo runtime/config thống nhất hơn;
- không hardcode riêng một kiểu gọi local LLM.

### 3.6 `building.py` cũ ghi label lỗi quá mơ hồ

Code cũ ở `main@2c93df6`:

```python
"title": f"Error Report for {community.get('name', 'Unknown')}"
```

Code mới:

```python
community_label = (
    community.get("name")
    or community.get("title")
    or community.get("timestamp")
    or "Unknown"
)
```

Nguồn code mới:

- [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:2015)

Ý nghĩa:

- nếu sau này còn fail, output sẽ dễ map ngược hơn;
- không còn quá nhiều `Unknown`.

## 4. Dẫn chứng thực tế từ `v3`

Run lỗi cũ:

- usage log: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3.jsonl](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3.jsonl:1)
- output: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3)

Kết quả đã phân tích:

- `api_error = 24`
- community output có `8` report lỗi kiểu `Error Report for ...`

Nói ngắn:

```text
v3 không phải clean build
```

Tài liệu phân tích chi tiết:

- [v3_build_failure_analysis.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/debug/v3_build_failure_analysis.md:1)

## 5. PR này sửa những file nào

Code:

- [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:44)
- [tgrag/src/core/building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1412)

Docs:

- [md/CLI/build_graph.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/CLI/build_graph.md:1)
- [md/README_MD.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/README_MD.md:29)
- [md/debug/fix_plan_build_query_demo_turboquant.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/debug/fix_plan_build_query_demo_turboquant.md:5)
- [md/debug/build_community_v3_to_v4_root_cause_and_fix.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/debug/build_community_v3_to_v4_root_cause_and_fix.md:1)
- [md/debug/v4_build_fix_test_10docs.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/debug/v4_build_fix_test_10docs.md:1)

## 6. Kết quả test lại `v4`

Run test:

- output: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4)
- build log: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:24)
- manifest: [build_manifest.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4/build_manifest.json:1)
- usage log: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl:1)

### 6.1 Dẫn chứng runtime trong build log

Build log đã in rõ:

```text
Slot context: 65536 tokens (slots=2)
Community pack budget: 61440 (resolution=auto_from_server_props)
```

Nguồn:

- [build log line 28](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:28)
- [build log line 29](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:29)

Manifest cũng xác nhận:

```json
"build_status": "completed",
"best_model_max_token_size": 61440,
"community_token_headroom": 4096,
"budget_resolution": "auto_from_server_props",
"server_slot_tokens": 65536,
"server_total_slots": 2
```

Nguồn:

- [build_manifest.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4/build_manifest.json:3)

### 6.2 Dẫn chứng phase community đã chạy sạch

Build log cho thấy:

```text
temporal community levels: [3, 1, 0]
generate temporal community reports: reports=20
community report generation: 164.67s
Graph building completed successfully
Documents processed: 10
```

Nguồn:

- [build log line 121](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:121)
- [build log line 129](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:129)
- [build log line 131](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:131)
- [build log line 135](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:135)
- [build log line 142](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:142)

### 6.3 Dẫn chứng không còn lỗi community kiểu cũ

Tôi đã kiểm lại artifact `v4`:

- usage log đếm được:
  - `api_success = 101`
  - `cache_hit = 1`
  - `api_error = 0`
- prompt lớn nhất:
  - `prompt_tokens = 26233`
  - `total_tokens = 27140`
- community output:
  - `community_reports = 20`
  - `error_reports = 0`

Nguồn dữ liệu:

- [usage log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl:1)
- [community reports](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4/kv_store_community_reports.json:1)

Nói ngắn:

```text
v4 10-doc đã sạch lỗi community kiểu v3
```

## 7. Static validation

Đã chạy:

```bash
python -m py_compile build_graph.py tgrag/src/core/building.py
```

## 8. Lệnh test lại bằng `tmux`

### 8.1 Start server

```bash
tmux new -s tq_full_srv
```

Trong tmux:

```bash
cd /home/guest/Projects/Research/llama-cpp-turboquant
./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 131072 \
  --parallel 2 \
  --n-predict 3072 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4.log
```

### 8.2 Start build

```bash
tmux new -s tq_full_build
```

Trong tmux:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false
export OPENAI_API_KEY=dummy
export TG_RAG_USAGE_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4.jsonl

conda run --no-capture-output -n turboquant python -u build_graph.py \
  --output_dir /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4 \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --base_url http://127.0.0.1:8080/v1 \
  --corpus_path /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_batch_num 16 \
  --embedding_max_async 1 \
  --embedding_prefix "search_document: " \
  --chunk_size 1200 \
  --chunk_overlap 100 \
  --num_docs 384 \
  --llm_max_async 2 \
  --llm_timeout 900 \
  --entity_extraction_timeout 43200 \
  |& tee /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4.log
```

## 9. Cách check log sau khi chạy full

```bash
rg -n 'Community pack budget|Slot context|BUILD SUMMARY|Failed to generate community report|Error Report for' \
  logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4.log
```

```bash
rg -n 'api_error' \
  results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4.jsonl
```

Kiểm tra thêm:

```text
outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4/build_manifest.json
```

## 10. Giới hạn còn lại

PR này đã chứng minh:

- fix đúng root cause cũ;
- build local sạch trên `10 docs`;
- docs/runbook đã đồng bộ để chạy lại rõ ràng hơn.

Nhưng PR này **chưa chứng minh** rằng:

```text
full 384 docs chắc chắn sạch hoàn toàn
```

Bước kỹ thuật hợp lý tiếp theo vẫn là:

1. chạy `50 docs`
2. chạy `100 docs`
3. nếu sạch thì mới chạy full `384 docs`
