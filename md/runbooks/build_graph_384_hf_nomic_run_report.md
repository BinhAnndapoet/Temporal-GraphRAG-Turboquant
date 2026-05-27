# Báo Cáo Run 384 Docs (v2): 7B TurboQuant + HuggingFace Nomic Embedding

> Đây là bản **v2** cho run 7B, bổ sung rõ phần kết quả export Neo4j và trạng thái chất lượng community reports.
>
> **Lưu ý naming/version:** canonical path để review version là
> `md/runbooks/build_graph_384_hf_nomic_run_report_v2.md`.
> File hiện tại được giữ để tương thích link cũ.

---

## V2 Snapshot (7B)

### Trạng thái tổng quan

- Build 384 docs: **PASS kỹ thuật** (graph/vector/docs đã persist)
- Community reports: **chưa clean** (vẫn còn lỗi do context overflow ở một số community lớn)
- Export Neo4j package: **đã hoàn tất và verify**

### Neo4j export evidence (v2)

- `graph_run_id`: `BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2_neo4j_20260526_235707`
- `docs=384`, `chunks=1462`, `entity_nodes=18722`, `entity_relationships=15222`, `node_chunk_links=35861`
- Temporal nodes (`DATE|MONTH|QUARTER|YEAR`): `195`
- Edges chạm temporal nodes: `517`

Chi tiết đầy đủ nằm trong file:

- `md/export_graphdb-neo4j/neo4j_export_results_7b_v2.md`

Tài liệu này ghi lại run full 384 docs mới nhất của `Temporal-GraphRAG-Turboquant` sau khi chuyển embedding từ Ollama sang HuggingFace Nomic. Mục tiêu là có một file tra cứu nhanh: chạy bằng lệnh/cấu hình nào, log nằm ở đâu, output nằm ở đâu, đã pass tới đâu, còn lỗi gì, và resume hiện tại có giúp chạy tiếp được không.

Run này **chưa phải clean pass hoàn toàn**. Nó pass kỹ thuật vì đã ghi đủ graph/vector/docs, nhưng còn lỗi chất lượng ở bước community report.

---

## 1. Kết Luận Nhanh

| Hạng mục | Kết luận |
|---|---|
| Build 384 docs | Hoàn tất kỹ thuật |
| Embedding HuggingFace | Thành công, không còn lỗi Ollama input length |
| HF token | Chỉ là warning tải model từ HuggingFace Hub, không phải lỗi build |
| Lỗi còn lại | 10 community reports fail do prompt vượt context slot |
| Nguyên nhân chính | Server chạy `-c 131072 --parallel 4`, nên mỗi request chỉ có `n_ctx_slot=32768` |
| Output có dùng được không | Dùng được cho graph/vector/docs, nhưng community report chưa clean |
| Resume hiện tại | Chưa đủ ổn định để resume đúng stage; cần thiết kế thêm community-only rebuild và chunk checkpoint |

---

## 2. Đường Dẫn Cần Đối Chiếu

| Loại file | Đường dẫn |
|---|---|
| Build log | `logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh.log` |
| llama-server log | `logs/llama_server/SERVER_llama_server_qwen25_7b_p4_c131072_q8_20260525_122222.log` |
| Usage log JSONL | `results/usage/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh.jsonl` |
| Output dir | `outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh` |

Các file output chính trong output dir:

```text
kv_store_full_docs.json
kv_store_text_chunks.json
kv_store_llm_response_cache.json
kv_store_community_reports.json
vdb_entities.json
vdb_entities_new.json
vdb_relations.json
graph_chunk_entity_relation.graphml
graph_temporal_hierarchy.graphml
```

---

## 3. Cấu Hình Run Đã Chạy

Build log ghi runtime config:

```text
model=qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072
llm_max_async=4
llm_timeout=900
entity_extraction_timeout=43200
embedding_provider=huggingface
embedding_model=nomic-ai/nomic-embed-text-v1.5
embedding_dim=768
embedding_max_tokens=7500
embedding_max_chars=24000
embedding_device=cuda
embedding_batch_size=8
embedding_batch_num=16
embedding_max_async=1
chunk_size=1200
chunk_overlap=100
num_docs=384
```

Server log ghi context thật:

```text
n_ctx = 131072
n_ctx_seq = 32768
n_slots = 4
slot 0 n_ctx = 32768
slot 1 n_ctx = 32768
slot 2 n_ctx = 32768
slot 3 n_ctx = 32768
```

Điểm cần nhớ: `-c 131072 --parallel 4` không có nghĩa mỗi request có 131K context. Nó chia thành 4 slot, nên mỗi request chỉ có khoảng 32K context.

---

## 4. Lệnh Chạy Tương Ứng

### 4.1 Start llama-server

```bash
tmux new -s SERVER_llama_server_qwen25_7b_p4_c131072_q8

conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server

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
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_llama_server_qwen25_7b_p4_c131072_q8_$(date +%Y%m%d_%H%M%S).log
```

Ý nghĩa các arg quan trọng:

| Arg | Ý nghĩa | Tác động trong run này |
|---|---|---|
| `-c 131072` | Tổng context server cấp cho toàn bộ slots | Bị chia theo `--parallel` |
| `--parallel 4` | 4 request đồng thời | Nhanh hơn extraction, nhưng mỗi slot chỉ còn 32K context |
| `--n-predict 3072` | Giới hạn output tối đa mỗi request | Giữ output extraction/community không quá dài |
| `-ctk q8_0 -ctv turbo3` | KV cache theo TurboQuant | Giảm VRAM cho context dài |
| `--alias ...c131072-p4-np3072` | Tên model build graph gọi tới | Phải khớp `--model` trong build |

### 4.2 Build graph 384 docs

```bash
tmux new -s BUILD_graph_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs

conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false
export TG_RAG_USAGE_LOG=results/usage/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh.jsonl

mkdir -p logs/build_graph outputs/build_graph results/usage

python -u build_graph.py \
  --output_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cuda \
  --embedding_batch_size 8 \
  --embedding_batch_num 16 \
  --embedding_max_async 1 \
  --embedding_prefix "search_document: " \
  --chunk_size 1200 \
  --chunk_overlap 100 \
  --num_docs 384 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --entity_extraction_timeout 43200 \
  2>&1 | tee logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh.log
```

Ý nghĩa các arg quan trọng:

| Arg | Ý nghĩa | Tác động trong run này |
|---|---|---|
| `--llm_max_async 4` | Cho phép 4 request LLM đồng thời | Khớp `--parallel 4`, extraction nhanh hơn p1/p2 |
| `--embedding_device cuda` | Chạy HF embedding trên GPU | Embedding nhanh, nhưng có thể tranh VRAM nếu model lớn hơn |
| `--embedding_batch_size 8` | Batch size nội bộ cho sentence-transformers | An toàn hơn batch lớn khi dùng chung GPU |
| `--embedding_max_async 1` | Không cho nhiều batch embedding chạy đồng thời | Giảm rủi ro spike VRAM |
| `--embedding_max_chars 24000` | Guard không embed description quá dài | Run này không cần truncate vì max entity chỉ 3132 chars |
| `--entity_extraction_timeout 43200` | Timeout riêng cho extraction dài | Tránh 384 docs bị timeout trước khi xong |
| `--chunk_size 1200 --chunk_overlap 100` | Chunking ECT-QA | Tạo 1462 chunks cho 384 docs |

---

## 5. Kết Quả Định Lượng

Build log:

```text
new documents: 384
new chunks: 1462
Graph building completed successfully
Documents processed: 384
Total elapsed: 22716.34s
```

Tổng thời gian:

```text
22716.34s ~= 6.31 giờ
```

Output counts:

| File | Count |
|---|---:|
| `kv_store_full_docs.json` | 384 |
| `kv_store_text_chunks.json` | 1462 |
| `kv_store_community_reports.json` | 392 |
| `kv_store_llm_response_cache.json` | 3293 |
| `vdb_entities.json` | 16631 vectors |
| `vdb_entities_new.json` | 16631 vectors |
| `vdb_relations.json` | 19260 vectors |
| `graph_chunk_entity_relation.graphml` | exists, ~19.6 MB |
| `graph_temporal_hierarchy.graphml` | exists, ~118 KB |

Stage timing:

| Stage | Time |
|---|---:|
| Document hashing + chunking | 0.29s |
| Chunk LLM extraction + parsing | 21872.14s |
| Entity merge/upsert | 314.23s |
| Relation merge/upsert | 0.27s |
| Entity vector embedding/upsert | 41.97s |
| Entity_new vector embedding/upsert | 30.83s |
| Relation vector embedding/upsert | 20.72s |
| Temporal hierarchy build | 0.02s |
| Community report generation | 416.90s |
| Persist all storages | 18.51s |

Kết luận tốc độ:

- Bottleneck thật là `chunk LLM extraction + parsing`: hơn 6 giờ gần như nằm ở đây.
- HF CUDA embedding không phải bottleneck: tổng embedding khoảng 93.52s cho entities/entities_new/relations.

---

## 6. Vì Sao Còn Warning HF Token

Log có:

```text
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
```

Đây là warning từ HuggingFace Hub khi process tải hoặc kiểm tra model `nomic-ai/nomic-embed-text-v1.5` / remote code. Nó **không phải lỗi build**, vì:

- Build vẫn load được model.
- Embedding vẫn chạy local bằng `sentence-transformers`.
- Vector embedding generation đã hoàn tất.
- Không có lỗi `Ollama embedding API error`.
- Không có lỗi HuggingFace download/authentication fatal.

HF token chỉ cần nếu:

- máy chưa có model trong cache và bị rate limit khi download,
- model bị gated/private,
- muốn giảm rủi ro download fail khi chạy máy mới,
- muốn login trước cho ổn định.

Nếu muốn bỏ warning, dùng một trong hai cách:

```bash
export HF_TOKEN=hf_xxx
```

hoặc:

```bash
huggingface-cli login
```

Không ghi token vào code, không ghi vào config, không commit token.

Nếu đã cache model ở:

```text
/home/guest/Projects/Research/.cache/huggingface
```

thì những lần sau ít phụ thuộc network hơn. Tuy nhiên warning vẫn có thể xuất hiện nếu thư viện vẫn gọi Hub metadata.

---

## 7. Lỗi Còn Lại: Community Prompt Vượt Context

Build log có 10 lần:

```text
ERROR - Failed to generate community report after 3 attempts
```

Usage log xác nhận:

```text
rows=3615
api_success=3297
cache_hit=288
api_error=30
```

30 API errors tương ứng với:

```text
10 community reports lỗi x 3 retry
```

Các community lỗi:

```text
2020-Q2
2020-Q4
2021-Q2
2021-Q4
2022-Q1
2022-Q2
2020
2021
2022
2022-01
```

Server log ghi rõ lỗi:

```text
request (33079 tokens) exceeds the available context size (32768 tokens)
request (103616 tokens) exceeds the available context size (32768 tokens)
request (104203 tokens) exceeds the available context size (32768 tokens)
request (111468 tokens) exceeds the available context size (32768 tokens)
request (111529 tokens) exceeds the available context size (32768 tokens)
request (113147 tokens) exceeds the available context size (32768 tokens)
request (120723 tokens) exceeds the available context size (32768 tokens)
request (181375 tokens) exceeds the available context size (32768 tokens)
request (186530 tokens) exceeds the available context size (32768 tokens)
```

Vì sao lỗi:

1. `--parallel 4` chia `-c 131072` thành 4 slots.
2. Mỗi request community report chỉ có `n_ctx_slot=32768`.
3. Một số community cấp quarter/year gom quá nhiều entity/relation/description.
4. Prompt community có thể dài từ 33K tới 186K tokens.
5. llama-server trả HTTP 400 trước khi model sinh output.
6. Source retry 3 lần, vẫn fail, rồi ghi error report thay vì dừng toàn bộ build.

Điểm quan trọng: đây không phải lỗi embedding. Đây là lỗi community summarization prompt quá dài.

---

## 8. Vì Sao `Graph building completed successfully` Nhưng Vẫn Có Lỗi

Trong source hiện tại, community report generation có cơ chế fallback. Nếu một community fail sau 3 attempts, source tạo report lỗi dạng:

```text
Error Report ...
Failed to generate report ...
Report generation failed
```

Vì vậy build vẫn đi tiếp và persist toàn bộ storages. Điều này có lợi vì không mất toàn bộ 6 giờ extraction, nhưng nguy hiểm nếu chỉ nhìn dòng:

```text
Graph building completed successfully
```

Một run sạch phải kiểm thêm:

```bash
grep -R "Failed to generate report\\|Error Report\\|Report generation failed" \
  outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh/kv_store_community_reports.json
```

Run này có 10 community lỗi, nên nên ghi trạng thái là:

```text
PASS kỹ thuật, nhưng community reports chưa clean.
```

---

## 9. Resume Hiện Tại Có Giúp Chạy Tiếp Không

Đọc theo `md/runbooks/resume_setup.md`, source hiện tại có resume hạn chế.

### 9.1 Với run này, phần nào đã có thể giữ lại

Run này đã persist đủ:

```text
full_docs=384
text_chunks=1462
entities=16631
relations=19260
graphml exists
community_reports=392
llm_response_cache=3293
```

Nên nếu chỉ xét graph/vector/docs, output này có thể giữ lại. Không nên xóa output dir.

### 9.2 Phần chưa có cách resume tốt

Vấn đề còn lại là community reports. Hiện source chưa có mode:

```text
--rebuild_communities_only
```

Nếu rerun cùng `output_dir`, `TemporalGraphRAG.ainsert()` có thể thấy docs đã tồn tại trong `full_docs` và return sớm. Như vậy không chắc sẽ rebuild community report được.

Nếu rerun output dir mới, sẽ phải chạy lại 6 giờ extraction, dù graph/vector cũ đã có.

Vì vậy resume hiện tại **chưa đủ ổn định** cho trường hợp này. Nó cứu được nhờ output đã persist, nhưng chưa có CLI/source để chỉ sửa đúng phần community lỗi.

### 9.3 Kết luận resume cho run này

| Mục tiêu | Hiện làm được chưa | Ghi chú |
|---|---:|---|
| Không mất graph/vector/docs đã build | Có | Vì run đã persist cuối |
| Rerun chỉ 10 community lỗi | Chưa | Cần community-only rebuild |
| Rerun toàn bộ community reports trên graph cũ | Chưa rõ/không ổn định | Source hiện không thiết kế rõ mode này |
| Rerun extraction từ cache để tiết kiệm | Có một phần | LLM cache có 3293 entries, nhưng không phải checkpoint structured theo chunk |
| Resume nếu crash trước persist cuối | Chưa | Cần chunk extraction checkpoint |

---

## 10. Hướng Giải Quyết Chưa Code

### 10.1 Không nên fix bằng cách chỉ tăng parallel/context

Nếu đổi từ p4 sang p2:

```text
-c 131072 --parallel 2 -> n_ctx_slot khoảng 65536
```

Cách này chỉ xử lý được prompt 33079 tokens. Nó vẫn fail các prompt 103K, 113K, 181K, 186K.

Nếu đổi sang p1:

```text
-c 131072 --parallel 1 -> n_ctx_slot khoảng 131072
```

Cách này có thể xử lý các prompt 103K-120K, nhưng vẫn không xử lý được prompt 181K-186K. Ngoài ra p1 sẽ làm extraction chậm hơn nhiều nếu chạy lại từ đầu.

### 10.2 Fix đúng cho community report

Cần thêm cơ chế giới hạn payload trước khi gọi LLM community report:

```text
--community_max_prompt_tokens
--community_max_chars
--community_max_entities
--community_max_relations
--community_description_max_chars
```

Hoặc chia community lớn:

```text
year -> quarter -> month
large community -> subcommunity batches -> final summary
```

Với ECT-QA, các node thời gian như `2020`, `2021`, `2022`, `2020-Q2` dễ gom rất nhiều relation/entity. Không nên nhét toàn bộ vào một prompt.

### 10.3 Fix đúng cho resume

Cần thêm ít nhất 2 mode:

```text
--skip_community_reports
--rebuild_communities_only
```

Quy trình hợp lý:

1. Build graph/vector/docs trước, có thể skip community hoặc cho phép community lỗi không chặn output.
2. Sau đó chạy community-only rebuild với profile context phù hợp hơn.
3. Nếu community lớn vẫn vượt context, split/cap payload.

Cần thêm checkpoint:

```text
kv_store_chunk_extractions.json
resume_manifest.json
```

Mục tiêu là nếu fail sau 5 giờ extraction, lần sau không phải gọi lại toàn bộ 1462 chunk prompts.

---

## 11. Lệnh Check Nhanh Sau Run

### 11.1 Check build log

```bash
grep -E "runtime|new chunks|embedding_provider|embedding_device|embedding content lengths|Truncate embedding|Failed to generate community report|Graph building completed|Documents processed|Total elapsed" \
  /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh.log
```

### 11.2 Check server context slot và lỗi context

```bash
grep -E "n_ctx|n_ctx_seq|new slot|exceeds the available context size|POST /v1/chat/completions" \
  /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_llama_server_qwen25_7b_p4_c131072_q8_20260525_122222.log
```

### 11.3 Check usage log API errors

```bash
python - <<'PY'
import json, collections, re
p = "/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh.jsonl"
counts = collections.Counter()
tokens = collections.Counter()
for line in open(p, encoding="utf-8"):
    if not line.strip():
        continue
    row = json.loads(line)
    event = row.get("event")
    counts[event] += 1
    if event == "api_error":
        m = re.search(r"request \\((\\d+) tokens\\).*context size \\((\\d+) tokens\\)", row.get("error", ""))
        if m:
            tokens[int(m.group(1))] += 1
print("events:", dict(counts))
print("api_error_token_counts:", sorted(tokens.items()))
PY
```

Kỳ vọng của run này:

```text
events: {'api_success': 3297, 'cache_hit': 288, 'api_error': 30}
api_error_token_counts:
33079 x 6
103616 x 3
104203 x 3
111468 x 3
111529 x 3
113147 x 3
120723 x 3
181375 x 3
186530 x 3
```

### 11.4 Check community reports lỗi

```bash
grep -o "Failed to generate report\\|Error Report\\|Report generation failed" \
  /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh/kv_store_community_reports.json | sort | uniq -c
```

---

## 12. Khuyến Nghị Vận Hành Tiếp Theo

Không chạy lại 384 từ đầu ngay nếu chỉ muốn sửa lỗi community. Run này đã tốn hơn 6 giờ và đã có graph/vector đủ.

Thứ tự hợp lý:

1. Giữ nguyên output dir hiện tại.
2. Đánh dấu run này là `technical pass with community errors`.
3. Bổ sung thiết kế/code cho `community-only rebuild`.
4. Bổ sung giới hạn prompt community để không tạo request 181K-186K tokens.
5. Sau khi có community-only rebuild, dùng output hiện tại để rebuild community thay vì chạy lại extraction.
6. Nếu vẫn muốn rerun full để benchmark, dùng p2 hoặc p1 tùy mục tiêu, nhưng phải biết p1 chậm hơn và p2 vẫn không đủ cho prompt >65K.

Trạng thái tốt nhất trước khi benchmark/eval:

```text
full_docs=384
text_chunks=1462
entities/relations vectors đầy đủ
community_error=0
usage_log api_error=0 hoặc chỉ lỗi không ảnh hưởng
cache model là alias Qwen local, không phải Gemini
```

