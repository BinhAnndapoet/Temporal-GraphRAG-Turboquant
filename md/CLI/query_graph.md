# CLI Query Graph Cho Temporal-GraphRAG-Turboquant

File này hướng dẫn cách **query trực tiếp trên folder output đã build xong** của `Temporal-GraphRAG-Turboquant`.

Mục tiêu chính:

- Query được ngay sau khi build và export thành công.
- Trỏ đúng vào **folder build gốc** `outputs/build_graph/<BUILD_CASE>`.
- Biết đủ CLI args để chạy `local`, `global`, `naive`.
- Tránh nhầm giữa folder build và folder export Neo4j.

---

## 1. Query Đúng Vào Folder Nào?

Bạn phải query vào folder build có các file như:

- `kv_store_full_docs.json`
- `kv_store_text_chunks.json`
- `kv_store_community_reports.json`
- `vdb_entities.json`
- `vdb_relations.json`
- `graph_chunk_entity_relation.graphml`
- `graph_temporal_hierarchy.graphml`

Ví dụ folder đúng của bạn:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2
```

**Không dùng** folder Neo4j export kiểu `outputs/database_exports/...` để query bằng `query_graph.py`.

---

## 1.1 Canonical query command (khuyến nghị, ít lỗi nhất)

Nếu bạn đang chạy local `llama-server` turboquant ở `http://localhost:8080/v1`, dùng lệnh này để query ổn định:

```bash
python query_graph.py \
  --question "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

Lưu ý:

- `--model` phải khớp server alias.
- `--llm_max_async` nên khớp `llama-server --parallel`.
- Nếu dùng demo UI cùng lúc, để `Provider=openai` với cùng model/base_url để tránh lệch behavior.

---

## 2. Chuẩn Bị Môi Trường

Trước khi query, bật đúng conda env và vào đúng repo:

```bash
eval "$(conda shell.bash hook)"
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
```

Nếu bạn dùng local LLM qua `llama-server`, server phải đang chạy ở:

```text
http://localhost:8080/v1
```

### 2.1 Quy tắc key/provider cho query (không nhầm nữa)

| Backend bạn đang dùng | `--local_llm_backend` | Key cần set |
|---|---|---|
| OpenAI cloud | (không bắt buộc local backend) | `OPENAI_API_KEY` thật |
| Local `llama-server` OpenAI-compatible | `turboquant` (hoặc dùng provider openai trong demo) | `OPENAI_API_KEY=dummy` (non-empty) |
| Gemini API | (không dùng local llama-server) | `GOOGLE_API_KEY`/`GEMINI_API_KEY` thật |
| Ollama | `ollama` | Không cần key |

**Gợi ý an toàn nhất cho local `llama-server`:**

```bash
export OPENAI_API_KEY=dummy
export OPENAI_BASE_URL=http://localhost:8080/v1
```

Lý do: một số luồng khởi tạo kiểm tra key với provider không phải `ollama`; dùng key dummy giúp tránh fail do validate môi trường.

---

## 3. Start `llama-server` Đúng Cấu Hình

Để tránh conflict khi query graph, server và client phải khớp 3 thứ:

- `--alias` của `llama-server`
- `--model` của `query_graph.py`
- `--parallel` của server phải khớp `--llm_max_async` nếu bạn override bằng CLI

### 3.1 Profile 7B khớp run v2 (đã chạy thật)

```bash
cd /home/guest/Projects/Research/llama-cpp-turboquant

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 131072 \
  --parallel 4 \
  --n-predict 3072 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/query_7b_$(date +%Y%m%d_%H%M%S).log
```

Log thật của run v2 cho thấy:

- `n_ctx = 131072`
- `n_ctx_seq = 32768`
- `n_slots = 4`

Tức là mỗi slot query thực tế chỉ có khoảng `32768` context, nên `p4` không phải 131K cho từng request.

Khi query đúng theo run v2 này, client nên dùng `--llm_max_async 4` và `--llm_timeout 900` để khớp server.

### 3.2 Profile 14B Q5 khuyến nghị

```bash
cd /home/guest/Projects/Research/llama-cpp-turboquant

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/Qwen3-14B-Q5_0.gguf \
  --alias qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 2 \
  --n-predict 4096 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/query_14bq5_$(date +%Y%m%d_%H%M%S).log
```

### Ý nghĩa các arg

- `--alias`: tên model mà `query_graph.py --model` phải dùng y hệt.
- `-c`: tổng context của server.
- `--parallel`: số slot xử lý song song.
- `--n-predict`: giới hạn output mỗi request.
- `-ctk q8_0 -ctv turbo3`: profile KV cache TurboQuant.
- `-fa on -ngl 99`: offload GPU tối đa khi máy đủ VRAM.
- `--log-file`: giữ log riêng để debug khi query lỗi hoặc timeout.

### Quy tắc chống conflict

- Nếu server chạy `--parallel 2` thì client nên dùng `--llm_max_async 2` hoặc không override để dùng mặc định.
- Nếu đổi sang `--parallel 1`, hãy đổi `--llm_max_async 1` khi query.
- Nếu đổi model, nhớ đổi lại cả `--alias` và `--model`.

---

## 4. Lệnh Query Nhanh Nhất

### 4.1 Local query — khuyến nghị cho câu hỏi chi tiết theo thời gian

```bash
python query_graph.py \
  --question "What was DXC Technology's revenue performance in Q1 2022?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

### Ý nghĩa

- `--question`: câu hỏi bạn muốn hỏi graph.
- `--working_dir`: folder build output đã có graph/vector/cache.
- `--mode local`: mode phù hợp câu hỏi fact cụ thể, có timestamp.
- `--local_llm_backend turboquant`: dùng `llama-server` local.
- `--model`: phải khớp alias của server đang chạy.
- `--base_url`: endpoint OpenAI-compatible của server.
- `--llm_max_async`: nên khớp `--parallel` của server; với run v2 này là 4.
- `--llm_timeout`: tăng lên 900 để giảm timeout khi prompt dài.
- `--show_retrieval`: in thêm evidence retrieval detail để debug.

### 4.2 Local query với HuggingFace embedding

Nếu build dùng HuggingFace embedding model, hãy query cùng backend đó để giữ điều kiện so sánh công bằng:

```bash
python query_graph.py \
  --question "What was DXC Technology's revenue performance in Q1 2022?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --show_retrieval
```

### Ý nghĩa bổ sung

- `--embedding_provider huggingface`: dùng sentence-transformers local thay vì Ollama embeddings.
- `--embedding_model`: phải khớp model dùng lúc build.
- `--embedding_device`: thường là `cuda` nếu máy có GPU phù hợp, hoặc `cpu` nếu không.
- `--embedding_batch_size`: batch size khi encode embeddings.
- `--embedding_max_tokens`: giới hạn độ dài đầu vào cho embedding model.
- Không cần `--embedding_base_url` khi dùng HuggingFace embedding.

---

## 5. Lệnh Query Global

Dùng khi bạn muốn tổng quan, xu hướng, tóm tắt nhiều community:

```bash
python query_graph.py \
  --question "Summarize the main trends across 2022." \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode global \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900
```

### Ý nghĩa

- `global` sẽ ưu tiên community reports và summary.
- Không cần `--show_retrieval` vì global mode thường trả response trực tiếp.

---

## 6. Lệnh Query Naive

Naive mode là baseline đơn giản, chỉ vector search trên text chunks:

```bash
python query_graph.py \
  --question "What happened in Q1 2022?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode naive \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900
```

### Khi nào dùng

- Muốn so sánh nhanh với local/global.
- Muốn test xem graph retrieval có giúp gì hơn không.

---

## 7. Output Mong Muốn Khi Query Đúng

Nếu chạy đúng, bạn thường sẽ thấy:

- `query_graph.py` in ra kết quả cuối cùng thay vì lỗi timeout.
- Có phần trả lời dạng tóm tắt/giải thích đúng theo `mode` bạn chọn.
- Nếu bật `--show_retrieval`, sẽ có evidence/retrieval detail kèm theo.
- Không có lỗi kiểu `Working directory does not exist` hoặc `API request failed`.

Ví dụ dấu hiệu “đang đúng đường”:

```text
✅ Query completed successfully
🔎 Retrieved evidence ...
💬 Final answer ...
```

---

## 8. Các Arg Quan Trọng

### 8.1 `--working_dir`

Đây là arg quan trọng nhất.

```text
--working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2
```

Nó phải trỏ vào folder build đã hoàn tất, nơi có các file `kv_store_*.json` và `graph_*.graphml`.

Nếu trỏ nhầm sang folder Neo4j export, query sẽ không load đúng graph gốc.

### 8.2 `--mode`

- `local`: câu hỏi fact theo thời gian, có timestamp rõ.
- `global`: tổng quan, trend, summary.
- `naive`: baseline, chỉ vector search.

### 8.3 `--local_llm_backend`

- `turboquant`: dùng local `llama-server`.
- `ollama`: dùng Ollama native.

Với workflow của bạn, nên dùng `turboquant`.

Nếu muốn khớp đúng log v2, dùng `--llm_max_async 4` ở client.

### 8.4 `--model`

Phải khớp alias model đang chạy trong server.

Ví dụ 7B khớp run v2:

```text
qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072
```

Nếu server alias khác, đổi theo alias đó.

### 8.5 `--base_url`

Mặc định local server là:

```text
http://localhost:8080/v1
```

---

## 9. Checklist Trước Khi Query

Chạy nhanh mấy bước này:

```bash
ls outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2
```

Kỳ vọng thấy các file:

```text
kv_store_full_docs.json
kv_store_text_chunks.json
kv_store_community_reports.json
vdb_entities.json
vdb_relations.json
graph_chunk_entity_relation.graphml
graph_temporal_hierarchy.graphml
```

Nếu chưa có các file này, bạn đang trỏ sai folder hoặc build chưa xong.

---

## 10. Troubleshooting

### 8.1 Báo lỗi không thấy working dir

Nếu script báo kiểu:

```text
Working directory does not exist
```

thì:

- kiểm tra lại `--working_dir`
- đảm bảo path là folder build gốc, không phải folder export Neo4j

### 8.2 Không kết nối được server

Nếu bạn dùng `--local_llm_backend turboquant`, server phải đang chạy.

Kiểm tra nhanh:

```bash
curl http://localhost:8080/props
```

Nếu không ra JSON, hãy start lại `llama-server`.

### 8.3 Model alias không khớp

Nếu server chạy alias khác với `--model`, query có thể fail hoặc gọi nhầm model.

Cách xử lý:

- xem alias lúc start `llama-server`
- copy đúng alias đó vào `--model`

---

## 10. Ví Dụ Thực Tế

### Câu hỏi local

```bash
python query_graph.py \
  --question "What was DXC Technology's revenue performance in Q1 2022?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --show_retrieval
```

### Câu hỏi global

```bash
python query_graph.py \
  --question "What were the most important company-level trends in 2022?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode global \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1
```

### Câu hỏi naive

```bash
python query_graph.py \
  --question "What happened in Q1 2022?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode naive \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1
```

---

## 11. Ghi Nhớ Quan Trọng

- Query bằng `query_graph.py` thì luôn trỏ vào `outputs/build_graph/...`.
- Đừng nhầm sang `outputs/database_exports/...`.
- Nếu muốn query Neo4j, đó là một workflow khác, không phải `query_graph.py`.
- `local` là mode bạn sẽ dùng nhiều nhất cho câu hỏi fact có mốc thời gian.
- `global` phù hợp khi cần summary hoặc xu hướng.
- Nếu build dùng HuggingFace embedding thì query cũng nên chạy `--embedding_provider huggingface` và cùng `--embedding_model`.

---

## 12. Lệnh Tối Thiểu Bạn Cần Nhớ

```bash
eval "$(conda shell.bash hook)"
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

python query_graph.py \
  --question "What was DXC Technology's revenue performance in Q1 2022?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --show_retrieval
```

---

## 13. Bộ test ECT-QA để so sánh nhanh

Nếu bạn muốn chạy query xong là đối chiếu ngay với `answer` trong file `.jsonl`, dùng bộ case dưới đây. Tất cả đều là **query_graph** (không phải build).

### 13.1 Local mode — các case có answer rõ

```bash
python query_graph.py \
  --question "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

Expected answer: `$2 billion, $2.3 billion, and nearly $1.3 billion.`

```bash
python query_graph.py \
  --question "In which quarter did EPAM Systems Inc. have the lowest GAAP gross margin from 2021 to mid-2022?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

Expected answer: `Q2 2022`

```bash
python query_graph.py \
  --question "How much did Cincinnati Financial Corporation invest in fixed maturity securities in each year before 2023?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

Expected answer: `$291 million in 2020, $927 million in 2021, and $788 million in 2022.`

```bash
python query_graph.py \
  --question "What were Skechers U.S.A., Inc.'s quarterly sales in each quarter from Q4 2021 to Q3 2022?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

Expected answer: `$1.65 billion, over $1.8 billion, $1.87 billion, and $1.88 billion.`

```bash
python query_graph.py \
  --question "In which quarter in 2023 did jd.com record the highest non-GAAP net income attributable to ordinary shareholders?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

Expected answer: `Q3 2023`

```bash
python query_graph.py \
  --question "In which quarter from 2022 Q4 to 2023 Q2 did Marathon Petroleum Corporation return the highest amount via share repurchases and dividends?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

Expected answer: `Q1 2023`

```bash
python query_graph.py \
  --question "Which quarter saw the highest deferred revenue growth for Autodesk Inc from 2022-Q3 to 2023-Q3?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

Expected answer: `2022-Q3`

```bash
python query_graph.py \
  --question "What was the highest quarterly net income ONEOK, Inc. reported from Q4 2021 through Q3 2023?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

Expected answer: `Q1 2023`

### 13.2 Global mode — case tổng quan

```bash
python query_graph.py \
  --question "Summarize the main trends across 2022." \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode global \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900
```

### 13.3 Case âm tính để kiểm tra `unanswerable`

```bash
python query_graph.py \
  --question "What were the operating margins of Albertsons Companies, Inc., Kolmar Korea, and Guangzhou R&F Properties Co., Ltd. in 2024-q3?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --show_retrieval
```

Expected answer: `unanswerable`
