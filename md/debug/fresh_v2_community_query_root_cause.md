# Phân tích `fresh-v2`: community fail, query sai, và độ rối của demo

Ngày rà soát: 2026-06-01

Phạm vi tài liệu này:

- Không sửa code.
- Không chạy lại build/query.
- Chỉ đọc source, log, output artifact, docs trong `md/`, và đối chiếu với repo gốc `hanjiale/Temporal-GraphRAG` trên GitHub.

## 1. Kết luận ngắn

Có 4 điểm chính:

1. Run `BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2` fail community vì app pack prompt theo budget logic `65536`, nhưng `llama-server` thực tế chỉ còn `32768` token mỗi slot do chạy `-c 131072 --parallel 4`.
2. Lỗi này không nằm ở TurboQuant. `llama-cpp-turboquant` đang hành xử đúng: nó chia context theo slot và từ chối request vượt slot.
3. Query local đúng là đang dùng graph trong `working_dir`, nhưng graph chủ yếu chỉ được dùng để chọn ra vài raw chunk qua relation retrieval + PPR. Prompt cuối không đưa full graph evidence vào; nó trả lời từ các chunk đã chọn.
4. Demo hiện tại dễ làm query tệ hơn nữa vì preset/UI không ép query-time embedding phải khớp với embedding đã dùng lúc build. Với graph build bằng HuggingFace Nomic, demo mặc định rất dễ query bằng embedding khác.

---

## 2. Nguồn đã đọc

### 2.1 Log và output chính

- Build log `fresh-v2`: [logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2.log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2.log:1)
- Output build `fresh-v2`: `outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2`
- Build log `ctx24k_v2`: [logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_ctx24k_v2.log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_ctx24k_v2.log:1)
- Server log tương ứng `fresh-v2`: [logs/llama_server/SERVER_llama_server_qwen25_7b_p4_c131072_q8_20260525_122222.log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_llama_server_qwen25_7b_p4_c131072_q8_20260525_122222.log:141)
- Metric compare: [logs/metrics/20260530_001221_compare.log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/metrics/20260530_001221_compare.log:1)
- Prediction file local HF: [results/preds/pred_ctx24k_v2_hf_local384.jsonl](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/preds/pred_ctx24k_v2_hf_local384.jsonl:1)

### 2.2 Source code chính

- Factory tạo runtime: [tgrag/src/build.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/build.py:131)
- Runtime graph/query: [tgrag/src/temporal_graphrag.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/temporal_graphrag.py:226)
- Build community: [tgrag/src/core/building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1369)
- Query local/global: [tgrag/src/core/querying.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/querying.py:1280)
- KV storage: [tgrag/src/storage/kv_json.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/kv_json.py:31)
- Graph storage: [tgrag/src/storage/graph_networkx.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/graph_networkx.py:124)
- Vector storage: [tgrag/src/storage/vector_nanovectordb.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/vector_nanovectordb.py:33)
- HF embedding: [tgrag/src/llm/huggingface_embedding.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/huggingface_embedding.py:42)
- Ollama embedding: [tgrag/src/llm/embedding.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/embedding.py:117)

### 2.3 Docs trong `md/`

- [md/README_MD.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/README_MD.md:1)
- [md/CLI/build_graph.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/CLI/build_graph.md:1)
- [md/CLI/query_graph.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/CLI/query_graph.md:1)
- [md/CLI/inference_config.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/CLI/inference_config.md:1)
- [md/runbooks/demo_setup_and_db_graph_flow.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/runbooks/demo_setup_and_db_graph_flow.md:1)
- [md/temporal-graphrag/query_graph.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/temporal-graphrag/query_graph.md:1)
- [md/debug/debug_localLLM_log_results.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/debug/debug_localLLM_log_results.md:1)

### 2.4 Repo gốc đã đối chiếu

- Upstream repo theo README: `https://github.com/hanjiale/Temporal-GraphRAG`
- Kết quả đối chiếu: logic community/query cốt lõi hiện tại trong fork này gần như giữ nguyên từ upstream ở các phần đang gây vấn đề. Nghĩa là đây không phải lỗi do TurboQuant integration tạo ra một mình.

---

## 3. Query có thực sự dùng graph trong `working_dir` không?

Có, nhưng phải hiểu đúng cách nó dùng.

### 3.1 `working_dir` được load như thế nào

`TemporalGraphRAG.__post_init__()` tạo các storage dựa trên `working_dir`:

- `kv_store_full_docs.json`
- `kv_store_text_chunks.json`
- `kv_store_community_reports.json`
- `graph_chunk_entity_relation.graphml`
- `graph_temporal_hierarchy.graphml`
- `vdb_entities.json` / `vdb_entities_new.json`
- `vdb_relations.json`

Chỗ load:

- KV: [kv_json.py:33-35](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/kv_json.py:33)
- GraphML: [graph_networkx.py:124-134](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/graph_networkx.py:124)
- Vector DB JSON: [vector_nanovectordb.py:33-60](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/vector_nanovectordb.py:33)

### 3.2 Flow query thực tế

CLI/demo đều gọi cùng một đường:

- [query_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/query_graph.py:457)
- [demo.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/demo.py:477)
- `TemporalGraphRAG.query()` -> `aquery()` -> `local_query()` / `global_query()` tại [temporal_graphrag.py:326-394](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/temporal_graphrag.py:326)

Điểm rất quan trọng:

- Local mode dùng graph để retrieve.
- Prompt cuối cho LLM lại là các raw chunk đã được chọn.

Tức là:

```text
working_dir artifacts
-> relations_vdb + graphml + temporal_hierarchy
-> retrieve relation -> seed nodes -> PPR -> top chunks
-> format raw chunks
-> LLM trả lời từ raw chunks
```

Chỗ này được xác nhận bởi:

- thuật toán local trong doc: [md/temporal-graphrag/query_graph.md](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/temporal-graphrag/query_graph.md:216)
- context builder thật trong code: [querying.py:1895-1941](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/querying.py:1895)
- prompt `local_rag_response` yêu cầu trả lời từ `Data tables`: [prompts.yaml:353-381](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/configs/prompts.yaml:353)

Vì vậy, nếu ai kỳ vọng “query trực tiếp đọc community/entity/relation rồi trả lời từ graph schema”, thì source hiện tại không làm như vậy trong local mode.

---

## 4. Vì sao `fresh-v2` fail community

### 4.1 Build log cho thấy lỗi xảy ra ở level 0 community

Run `fresh-v2` có cấu hình:

- config: `tgrag/configs/config.yaml`
- `best_model_max_async = 4`
- server runtime `p4`

Xem: [fresh-v2 build log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2.log:4)

Community phase:

- total communities: `483`
- levels: `[3, 2, 1, 0]`
- lỗi xuất hiện ở level `0`

Xem: [fresh-v2 build log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2.log:672)

### 4.2 Server thực tế chỉ có `32768` token mỗi slot

Server log cho thấy:

- `n_seq_max = 4`
- `n_ctx = 131072`
- `n_ctx_seq = 32768`

Xem: [server log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_llama_server_qwen25_7b_p4_c131072_q8_20260525_122222.log:141)

Nghĩa là:

```text
-c 131072 --parallel 4
=> mỗi request thực tế chỉ có 32768 token
```

### 4.3 Artifact output chứng minh đúng là overflow context

Hai community level năm bị biến thành error report:

- community `"2021"`: [kv_store_community_reports.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2/kv_store_community_reports.json:281654)
- community `"2022"`: [kv_store_community_reports.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2/kv_store_community_reports.json:320299)

Nội dung lỗi nói thẳng:

- `34777 tokens > 32768`
- `38243 tokens > 32768`

Server log cũng ghi lại đúng các request fail đó:

- [406151-406155](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_llama_server_qwen25_7b_p4_c131072_q8_20260525_122222.log:406151)

### 4.4 Nguyên nhân sâu hơn trong source

Root cause không chỉ là “parallel cao”, mà là:

1. App pack prompt community theo `best_model_max_token_size`, không theo slot context thật của server.
2. `best_model_max_token_size` mặc định là `65536`.
3. Cơ chế fallback sang sub-community chỉ kích hoạt khi dữ liệu bị xem là `truncated` so với budget logic đó.

Chỗ set default:

- [temporal_graphrag.py:177](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/temporal_graphrag.py:177)

Chỗ pack community:

- [building.py:1845-1850](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1845)
- [building.py:1954-1959](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1954)

Logic fallback:

- [building.py:1416-1457](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1416)

Điểm then chốt:

```text
max_token_size = 65536
community prompt năm 2021/2022 ~= 34k-38k
=> app KHÔNG xem là overflow theo budget logic nội bộ
=> sub-community fallback không kích hoạt
=> request được gửi nguyên sang server
=> server từ chối vì slot thật chỉ 32768
```

Đây là lý do hai run `2021` và `2022` fail rất “đúng quy trình”.

### 4.5 Vậy lỗi community là do context hay do parallel?

Là do cả hai, nhưng đúng hơn là:

```text
lỗi do mismatch giữa:
- budget logic trong app
và
- slot context thật sau khi chia bởi --parallel
```

Nếu giữ `-c 131072`:

- `--parallel 4` -> `32768/slot`
- `--parallel 2` -> `65536/slot`
- `--parallel 1` -> `131072/slot`

Với community kiểu năm `2021` / `2022`, `p4` là cấu hình dễ nổ nhất.

### 4.6 Setup nào để không lỗi community với kiểu build này

Cho đường 7B local hiện tại, thứ tự an toàn là:

1. `-c 131072 --parallel 2`
2. `--llm_max_async 2`
3. Nếu còn lỗi community lớn, giảm tiếp xuống `--parallel 1`
4. Về phía app logic, budget pack community phải thấp hơn slot thật một khoảng an toàn

Về thực hành:

```text
Không nên coi p4/c131072 là cấu hình an toàn cho build 384 docs nếu app vẫn pack theo 65536.
```

---

## 5. Vì sao `ctx24k_v2` không phải bản fix sạch

Run `ctx24k_v2` tránh được hard overflow, nhưng nó không cho ra artifact đẹp.

### 5.1 Dấu hiệu

- config log dùng `tgrag/configs/config_7b_v2_community_fix.yaml`: [ctx24k_v2 build log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_ctx24k_v2.log:4)
- file config này hiện không có trong worktree, nên reproducibility đang thiếu
- entity summarization bị tắt: [ctx24k_v2 build log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_ctx24k_v2.log:26)
- output có community malformed `Unknown Community`: [ctx24k_v2 output](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_ctx24k_v2/kv_store_community_reports.json:151906)

### 5.2 Chất lượng graph cũng xấu hơn baseline Gemini

So sánh artifact:

| Run | Docs | Chunks | Entities | Relations | Communities |
|---|---:|---:|---:|---:|---:|
| `cmp_tq_gemini_api_384docs` | 384 | 1462 | 14577 | 19013 | 507 |
| `fresh-v2` | 384 | 1462 | 17506 | 19760 | 483 |
| `ctx24k_v2` | 384 | 1462 | 17497 | 20492 | 464 |

Nhận xét:

- Local 7B build ra graph lớn và nhiễu hơn baseline Gemini.
- `ctx24k_v2` còn ít community hơn `fresh-v2`.
- Việc né overflow đã đổi lấy artifact kém sạch hơn, không phải “fix xong”.

### 5.3 Suy luận hợp lý

Do file config `config_7b_v2_community_fix.yaml` không còn trong repo, chỉ có thể suy từ kết quả:

- nhiều khả năng run này đã hạ budget pack xuống khoảng `24k`
- hoặc ép truncation/fallback mạnh hơn
- nhờ vậy không vượt `32768`
- nhưng report bị cụt, méo, hoặc mất ngữ nghĩa

---

## 6. Vì sao query local rất tệ

Phải tách làm 2 trường hợp:

1. batch query đã dùng HuggingFace embedding đúng backend
2. demo/CLI tương tác có thể còn query bằng embedding lệch backend

### 6.1 Query local không trả lời trực tiếp từ graph schema

Local query hiện làm:

```text
relations_vdb.query(query)
-> filter relation theo timestamp
-> lấy seed nodes
-> chạy PPR trên graph
-> chấm điểm chunk
-> nhét vài chunk vào prompt
-> LLM trả lời
```

Code chính:

- relation -> seed nodes -> PPR -> chunk scoring: [querying.py:1336-1556](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/querying.py:1336)
- final local context chỉ format chunk: [querying.py:1895-1941](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/querying.py:1895)

Nói ngắn:

```text
graph dùng cho retrieval
không phải graph dùng trực tiếp cho final answer context
```

Nếu graph build bị nhiễu, hoặc relation retrieval lệch, prompt cuối sẽ lệch ngay.

### 6.2 Query hiện rất phụ thuộc vào relation retrieval + timestamp filtering

Bước đầu local mode query quan hệ trước, rồi filter relation theo timestamp:

- [querying.py:1336-1408](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/querying.py:1336)

Hậu quả:

- nếu vector search relation không đưa đúng relation của quý/năm cần hỏi
- hoặc timestamp normalization không khớp
- hoặc relation entity names quá nhiễu

thì `seed_nodes` sẽ ít hoặc bằng 0, kéo theo PPR và chunk scoring đều yếu.

### 6.3 Local context chỉ có khoảng 3-4 chunk

`local_max_token_for_text_unit = 4000` trong config mặc định:

- [config.yaml](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/configs/config.yaml:69)

Với chunk size khoảng `1200`, local mode thường chỉ nhét được 3-4 chunk. Điều này giải thích vì sao các câu hỏi multi-quarter, multi-company, comparison rất dễ trả lời thiếu hoặc lẫn quý.

### 6.4 Có bug thật trong supplemental retrieval

Trong `_supplemental_evidence_retrieval()`, danh sách node vừa `await gather(...)` xong lại bị reset thành `[]`:

- [querying.py:1632-1639](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/querying.py:1632)
- [querying.py:1682-1689](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/querying.py:1682)
- [querying.py:1711-1718](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/querying.py:1711)

Điều đó làm nhánh bổ sung entity gần như không tạo được gì.

Lưu ý:

- bug này cũng có trong upstream hiện tại
- nên đây không phải lỗi riêng của TurboQuant fork

### 6.5 `seed_node_method` và `enable_entity_retrieval` không ảnh hưởng mạnh như docs/demo đang gợi ý

`seed_node_method` chỉ được dùng ở nhánh supplemental retrieval:

- [querying.py:1627](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/querying.py:1627)

Nhưng primary local path trong `_iterative_evidence_retrieval()` luôn đi relation->PPR:

- [querying.py:1584-1598](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/querying.py:1584)

`enable_entity_retrieval` chủ yếu ảnh hưởng file VDB entity nào được load:

- [vector_nanovectordb.py:34-40](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/vector_nanovectordb.py:34)

Nhưng local primary path lại không dựa vào entity VDB.

Vì vậy:

```text
Demo nói:
- bật Enable Entity Retrieval
- chọn Seed Node Method = entities

nhưng trong source hiện tại, đây không phải hai cần gạt chính của main local pipeline.
```

### 6.6 Evidence định lượng: query đã dùng HF đúng backend mà vẫn rất kém

Prediction file `pred_ctx24k_v2_hf_local384.jsonl` cho thấy nhiều câu có:

- `entity = 0`
- `relation = 0`
- `text_units = 3` hoặc `4`

Xem ví dụ:

- [row 1](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/preds/pred_ctx24k_v2_hf_local384.jsonl:1)
- [row 7](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/preds/pred_ctx24k_v2_hf_local384.jsonl:7)
- [row 8](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/preds/pred_ctx24k_v2_hf_local384.jsonl:8)

Metric tổng:

- `pred_fresh_v2_hf_local10`: `f1=0.0384`
- `pred_ctx24k_v2_hf_local384`: `f1=0.0368`

Xem: [metric compare log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/metrics/20260530_001221_compare.log:4)

Điều này rất quan trọng:

```text
Ngay cả khi query-time embedding đã là HF và khớp tên file `hf_*`,
chất lượng vẫn tệ.
```

Vậy root cause chính của batch query tệ là:

1. graph local 7B build không sạch bằng baseline Gemini
2. local query algorithm quá mong manh với relation/timestamp mismatch
3. context cuối quá ít chunk
4. supplemental retrieval đang bug

---

## 7. Có thêm một lớp lỗi ở demo/CLI: query-time embedding dễ bị lệch backend

Đây là phần quan trọng cho trải nghiệm “demo/query rất tệ”.

### 7.1 CLI `query_graph.py` mặc định local TurboQuant -> embedding `ollama`

Nếu dùng:

```bash
--local_llm_backend turboquant
```

thì `apply_runtime_overrides()` tự mặc định:

- `provider = openai`
- `embedding_provider = ollama`

Xem: [query_graph.py:145-156](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/query_graph.py:145)

Trong khi build `fresh-v2` dùng:

- `embedding_provider = huggingface`
- `embedding_model = nomic-ai/nomic-embed-text-v1.5`

Xem: [fresh-v2 build log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2.log:5)

Vậy nếu user chạy query theo command “canonical” ở đầu doc mà không thêm HF embedding args, thì query embedding có thể đi bằng Ollama thay vì HF.

Doc đang tự mâu thuẫn:

- command “canonical” đầu file không có HF override: [md/CLI/query_graph.md:36-50](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/CLI/query_graph.md:36)
- nhưng cuối file lại nhắc phải query cùng HF backend: [md/CLI/query_graph.md:461-484](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/CLI/query_graph.md:461)

### 7.2 Demo còn rủi ro hơn CLI

Demo preset `Local Turboquant (recommended)` chỉ set:

- provider
- base_url
- query mode
- vài toggle retrieval

Nhưng demo UI không expose `embedding_provider` và `embedding_model` cho query-time.

Xem:

- preset logic: [demo.py:201-253](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/demo.py:201)
- run query override: [demo.py:403-467](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/demo.py:403)

Trong khi config mặc định `querying.embedding_provider` lại là `ollama`:

- [config.yaml:46-47](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/configs/config.yaml:46)

Nghĩa là:

```text
build bằng HF
demo query rất dễ vẫn dùng embedding ollama
=> vector search query-time bị lệch backend
=> retrieval sai thêm một tầng
```

### 7.3 Ngay cả HF path hiện tại cũng còn một bất lợi

HF embedding wrapper luôn prefix text bằng `search_document:`:

- [huggingface_embedding.py:48-59](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/huggingface_embedding.py:48)
- [build.py:112-120](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/build.py:112)

Trong debug notes của repo lại ghi rõ với Nomic:

- document nên dùng `search_document:`
- query nên dùng `search_query:`

Xem: [debug_localLLM_log_results.md:3783](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/debug/debug_localLLM_log_results.md:3783)

Tức là ngay cả khi đã query bằng HF, query embedding vẫn chưa đi theo cặp prefix tốt nhất cho Nomic.

---

## 8. Audit lại phần demo: chỗ nào đang rối hoặc gây hiểu nhầm

### 8.1 Đúng

Doc demo giải thích đúng một ý quan trọng:

- `working_dir` là graph artifacts
- `provider/model/base_url` là LLM dùng ở query time

Xem: [demo runbook](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/runbooks/demo_setup_and_db_graph_flow.md:17)

### 8.2 Chưa đủ

Doc chưa nhấn mạnh một quy tắc bắt buộc khác:

```text
Nếu working_dir được build bằng embedding backend/model A,
thì query-time embedding cũng phải là A
hoặc ít nhất phải cùng embedding space.
```

Hiện phần demo chưa chỉ rõ điều này trong bước “điền UI đúng 100%”:

- [demo runbook:79-109](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/runbooks/demo_setup_and_db_graph_flow.md:79)

### 8.3 Hai gợi ý retrieval trong demo đang hơi đánh lạc hướng

Doc và UI gợi ý:

- `Enable Entity Retrieval = ON`
- `Seed Node Method = entities`

Nhưng như phân tích ở mục 6.5, hai lựa chọn này không chi phối main local path. Vì thế:

- chúng có thể hữu ích ở nhánh phụ
- nhưng không giải quyết tận gốc local query hiện tại

### 8.4 `run_demo_stack.sh` mặc định vẫn dùng `p4`

Script demo stack hiện mặc định:

- `MODEL_ALIAS = ...p4...`
- `PARALLEL = 4`

Xem: [scripts/run_demo_stack.sh](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/scripts/run_demo_stack.sh:14)

Điều này ăn khớp với run `fresh-v2`, nhưng lại không phải profile build/query an toàn nhất cho community.

---

## 9. Cách setup thực tế để ít lỗi hơn

### 9.1 Nếu mục tiêu là build 7B ổn định hơn

Ưu tiên:

1. `llama-server -c 131072 --parallel 2`
2. `build_graph.py --llm_max_async 2`
3. nếu community vẫn nổ, hạ `parallel` xuống `1`
4. query-time embedding phải khớp với build-time embedding

### 9.2 Nếu vẫn dùng graph build bằng HF Nomic

Khi query:

```text
phải dùng lại HuggingFace embedding
và cùng model nomic-ai/nomic-embed-text-v1.5
```

Với demo hiện tại, điều này chưa được hỗ trợ rõ trên UI. Dùng demo để so sánh HF-built graph là không lý tưởng nếu chưa sửa UI hoặc chưa đổi config query sang HF trước.

### 9.3 Nếu phải dùng demo ngay bây giờ

Đọc demo theo quy tắc ngắn sau:

1. `Provider = openai` khi runtime là `llama-server` trong `/home/guest/Projects/Research/llama-cpp-turboquant`
2. `Model = đúng alias server`
3. `Base URL = http://localhost:8080/v1`
4. `Working Directory = đúng folder BUILD_*`
5. nếu graph build bằng HF embedding, không nên tin demo preset mặc định nếu chưa đảm bảo query config cũng dùng HF
6. `gemini` chỉ dùng khi cố ý đổi query LLM sang Gemini cloud
7. `ollama` chỉ dùng khi cố ý đổi hẳn runtime sang Ollama
8. `turboquant` provider chỉ để test nhánh app logic, không phải lựa chọn chuẩn cho local llama-server

---

## 10. Kết luận cuối cùng

Nếu phải xếp hạng nguyên nhân theo mức độ ảnh hưởng tới câu hỏi “vì sao query đang sai”, tôi xếp như sau:

1. Community build `fresh-v2` fail vì app pack theo `65536` nhưng server slot thật là `32768`.
2. Graph build local 7B ra artifact nhiễu hơn baseline Gemini.
3. Local query hiện là graph-guided chunk retrieval, không phải graph-rich final prompting; vì vậy chỉ cần relation/timestamp lệch là câu trả lời trượt mạnh.
4. Supplemental retrieval có bug thật.
5. Demo/CLI hiện rất dễ query bằng embedding backend không khớp với build, nhất là khi graph build bằng HF.
6. Ngay cả HF query path hiện tại cũng chưa tách document prefix và query prefix cho Nomic.

Kết luận ngắn gọn nhất:

```text
TurboQuant không phải thủ phạm chính.

Lỗi chính nằm ở:
- community pack budget không bám slot context thật
- artifact local graph chưa sạch
- local query pipeline quá mong manh
- demo/query-time embedding setup còn dễ lệch backend
```

