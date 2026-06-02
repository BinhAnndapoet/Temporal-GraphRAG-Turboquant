# Kế hoạch fix chi tiết: build community, query local/Gemini, demo, và runbook TurboQuant

Ngày soạn: 2026-06-02

Trạng thái tài liệu này:

- Đây là kế hoạch fix chi tiết và runbook vận hành.
- Tài liệu này phản ánh kế hoạch gốc tại thời điểm chưa sửa code.
- Sau đó đã có hai nhánh triển khai riêng:
  - query/demo: `fix/local-runtime-query-demo-endtoend`
  - build/community: `fix/build-community-budget-v4`
- Tài liệu kết quả triển khai và test thực tế:
  - [v3_build_failure_analysis.md](./v3_build_failure_analysis.md)
  - [build_community_v3_to_v4_root_cause_and_fix.md](./build_community_v3_to_v4_root_cause_and_fix.md)
  - [v4_build_fix_test_10docs.md](./v4_build_fix_test_10docs.md)

Tài liệu gốc phân tích nguyên nhân:

- [md/debug/fresh_v2_community_query_root_cause.md](./fresh_v2_community_query_root_cause.md)

---

## 1. Mục tiêu thực tế

Bạn đang cần 3 thứ tách biệt:

1. Fix build để không còn hỏng community khi chạy local `llama-server` qua TurboQuant.
2. Fix query để khi dùng `working_dir` đã build xong, query CLI và demo không bị lệch embedding/runtime.
3. Có runbook rõ ràng để so sánh:
   - cùng một graph output, query bằng local TurboQuant
   - cùng một graph output, query bằng Gemini

Điểm cần giữ chặt:

- `working_dir` là graph artifact đã build xong.
- LLM dùng để trả lời lúc query có thể đổi.
- Embedding dùng để retrieve lúc query phải khớp embedding space đã dùng lúc build, trừ khi bạn đang cố tình làm một thí nghiệm khác.

---

## 2. Điều gì sửa được ngay trên output `fresh_v2`, điều gì bắt buộc phải rebuild

### 2.1 Có thể làm ngay trên `fresh_v2`

Với output:

```text
outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2
```

bạn vẫn có thể:

- query `mode=local` để debug retrieval/query path
- dùng cùng `working_dir` đó và đổi LLM trả lời giữa:
  - local TurboQuant
  - Gemini
- chạy batch ECT-QA để xem chênh lệch generator trên cùng graph

### 2.2 Không nên làm trên `fresh_v2`

Không nên dùng `fresh_v2` làm baseline chất lượng cuối cùng cho:

- `mode=global`
- benchmark community quality
- benchmark end-to-end chính thức

Lý do:

- artifact community của `fresh_v2` đã có `Error Report for ...` trong `kv_store_community_reports.json`
- root cause là context overflow ở phase community report

Nói ngắn:

```text
fresh_v2 vẫn dùng được để debug local query path
nhưng không phải graph output "sạch" để chốt benchmark cuối
```

### 2.3 Khi nào bắt buộc rebuild

Bạn phải rebuild nếu muốn:

- community report sạch
- global query đáng tin cậy
- benchmark end-to-end để viết kết luận nghiêm túc

---

## 3. Kết luận fix ở mức hệ thống

Tôi đề xuất chia thành 2 nhánh sửa riêng:

### Nhánh 1: build/community

Tên branch đề xuất:

```text
fix/community-budget-and-build-manifest
```

Mục tiêu:

- tránh overflow community
- ghi manifest build để query/demo biết graph được build như thế nào

### Nhánh 2: query/demo

Tên branch đề xuất:

```text
fix/query-demo-local-embedding-sync
```

Mục tiêu:

- query CLI không tự ý lệch embedding
- demo không còn mơ hồ giữa TurboQuant / Gemini / Ollama
- local query context dùng lại graph evidence đúng hơn

### Nhánh hợp nhất sau khi xong cả 2

Tên branch tích hợp cuối:

```text
fix/local-runtime-query-demo-endtoend
```

---

## 4. Fix 1: community fail khi build local TurboQuant

## 4.1 Source hiện tại

### 4.1.1 Budget pack community đang bám `best_model_max_token_size`

File:

```text
tgrag/src/core/building.py
```

Đoạn hiện tại:

```python
describe = await _pack_single_community_describe(
    knwoledge_graph_inst,
    community,
    max_token_size=global_config["best_model_max_token_size"],
    already_reports=already_reports,
    global_config=global_config,
)
```

và:

```python
describe = await _pack_single_timestamp_describe(
    knowledge_graph_inst,
    community,
    max_token_size=global_config["best_model_max_token_size"],
    already_reports=already_reports,
    global_config=global_config,
)
```

Nguồn:

- `tgrag/src/core/building.py:1845-1850`
- `tgrag/src/core/building.py:1954-1959`

### 4.1.2 Default token budget hiện tại là `65536`

File:

```text
tgrag/src/temporal_graphrag.py
```

Đoạn hiện tại:

```python
best_model_max_token_size: int = 65536
```

Nguồn:

- `tgrag/src/temporal_graphrag.py:177`

### 4.1.3 `build_graph.py` hiện chưa expose CLI để override `best_model_max_token_size`

File:

```text
build_graph.py
```

Hiện tại có:

- `--llm_max_async`
- `--llm_timeout`
- `--embedding_provider`
- `--embedding_model`

Nhưng chưa có:

- `--best_model_max_token_size`

Nguồn:

- `build_graph.py:625-641`

## 4.2 Vì sao source hiện tại gây lỗi

Với server:

```text
-c 131072 --parallel 4
```

slot thật của server là:

```text
131072 / 4 = 32768 token / request
```

Nhưng app pack community theo budget logic `65536`, nên prompt khoảng `34k-38k` token:

- không bị coi là overflow trong app
- nhưng lại vượt slot thật ở server

Kết quả:

- app không fallback sub-community
- server từ chối request
- build không chết hẳn mà ghi `Error Report for ...`

## 4.3 Hướng fix đề xuất

### 4.3.1 Fix tối thiểu, ít chạm nhất

Expose `best_model_max_token_size` ra CLI của `build_graph.py`, rồi set nó theo slot thật của server.

Công thức vận hành:

```text
best_model_max_token_size <= floor(n_ctx / parallel) - headroom
```

Headroom nên để:

```text
2048 đến 4096 token
```

Ví dụ:

- `-c 131072 --parallel 4` -> slot `32768` -> nên set `best_model_max_token_size` khoảng `28672` đến `30720`
- `-c 131072 --parallel 2` -> slot `65536` -> nên set khoảng `57344` đến `61440`

### 4.3.2 Fix code đề xuất

#### Code cũ

```python
parser.add_argument(
    '--llm_max_async',
    type=int,
    default=None,
    help='Override max concurrent LLM calls. Defaults to 1 for --local_llm_backend turboquant'
)
parser.add_argument(
    '--llm_timeout',
    type=float,
    default=None,
    help='Override LLM request timeout in seconds. Defaults to 600 for --local_llm_backend turboquant'
)
```

#### Code mới đề xuất

```python
parser.add_argument(
    '--best_model_max_token_size',
    type=int,
    default=None,
    help='Override logical max token budget used by community/timestamp packing'
)
parser.add_argument(
    '--llm_max_async',
    type=int,
    default=None,
    help='Override max concurrent LLM calls. Should match llama-server --parallel'
)
parser.add_argument(
    '--llm_timeout',
    type=float,
    default=None,
    help='Override LLM request timeout in seconds'
)
```

Và trong `apply_runtime_overrides()`:

#### Code cũ

```python
if llm_max_async:
    override_config["best_model_max_async"] = llm_max_async
    override_config["cheap_model_max_async"] = llm_max_async
if llm_timeout:
    override_config["llm_timeout"] = llm_timeout
```

#### Code mới đề xuất

```python
best_model_max_token_size = args.best_model_max_token_size

if best_model_max_token_size:
    override_config["best_model_max_token_size"] = best_model_max_token_size
if llm_max_async:
    override_config["best_model_max_async"] = llm_max_async
    override_config["cheap_model_max_async"] = llm_max_async
if llm_timeout:
    override_config["llm_timeout"] = llm_timeout
```

## 4.4 Vì sao fix mới hợp lý

Vì core build hiện đã dùng `best_model_max_token_size` đúng chỗ. Vấn đề không phải thiếu logic pack, mà là:

- budget đang bị hardcode ở config/default
- CLI không expose để đồng bộ với slot context thật của server

Nên fix tối thiểu đúng là:

- expose budget hiện có
- buộc user set budget theo `n_ctx / parallel`

## 4.5 Cấu hình server/build khuyến nghị sau fix

### Profile an toàn hơn cho build 7B

Khuyến nghị:

```text
-c 131072 --parallel 2
--llm_max_async 2
--best_model_max_token_size 60000
```

Lý do:

- vẫn giữ được context lớn
- tránh slot 32768 quá chật như `p4`

### Nếu muốn cực an toàn

```text
-c 131072 --parallel 1
--llm_max_async 1
--best_model_max_token_size 120000 hoặc thấp hơn
```

Chi phí:

- throughput chậm hơn

---

## 5. Fix 2: build output phải có manifest

## 5.1 Source hiện tại

Output build hiện chỉ có:

- `graph_*.graphml`
- `kv_store_*.json`
- `vdb_*.json`

Không có file nào như:

- `build_manifest.json`
- `runtime_config.json`
- `embedding_manifest.json`

Điều này khiến query/demo không thể biết chắc:

- build dùng provider nào
- build dùng embedding provider/model nào
- build dùng prefix nào
- build dùng token budget nào

## 5.2 Hướng fix đề xuất

Sau khi `graph_rag` được khởi tạo xong trong `build_graph.py`, ghi thêm một file:

```text
<working_dir>/build_manifest.json
```

### Nội dung tối thiểu nên có

```json
{
  "build_timestamp": "2026-06-02T12:34:56+07:00",
  "working_dir": "...",
  "provider": "openai",
  "model": "qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072",
  "llm_base_url": "http://localhost:8080/v1",
  "best_model_max_async": 2,
  "best_model_max_token_size": 60000,
  "embedding_provider": "huggingface",
  "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
  "embedding_dim": 768,
  "embedding_device": "cuda",
  "embedding_batch_size": 16,
  "embedding_max_tokens": 7500,
  "embedding_prefix": "search_document: ",
  "corpus_path": "ect-qa/corpus/base.jsonl.gz",
  "num_docs": 384
}
```

## 5.3 Code cũ và code mới đề xuất

### Code cũ

`build_graph.py` hiện không có bước ghi manifest.

### Code mới đề xuất

Thêm helper:

```python
def write_build_manifest(output_dir: str, graph_rag, runtime_config: dict, args) -> None:
    manifest = {
        "build_timestamp": datetime.now().astimezone().isoformat(),
        "working_dir": graph_rag.working_dir,
        "provider": runtime_config.get("provider"),
        "model": runtime_config.get("model"),
        "llm_base_url": runtime_config.get("llm_base_url"),
        "best_model_max_async": graph_rag.best_model_max_async,
        "best_model_max_token_size": graph_rag.best_model_max_token_size,
        "embedding_provider": graph_rag.embedding_provider,
        "embedding_model": graph_rag.embedding_model,
        "embedding_dim": graph_rag.embedding_dim,
        "embedding_device": graph_rag.embedding_device,
        "embedding_batch_size": graph_rag.embedding_batch_size,
        "embedding_max_tokens": graph_rag.embedding_max_tokens,
        "embedding_prefix": graph_rag.embedding_prefix,
        "corpus_path": args.corpus_path,
        "num_docs": args.num_docs,
    }
    ...
```

Và gọi sau khi init thành công hoặc sau khi build thành công.

## 5.4 Vì sao fix này đáng làm

Không có manifest, query/demo phải đoán.

Có manifest, query/demo có thể:

- auto-fill embedding config đúng
- cảnh báo nếu user đang query graph HF mà lại chọn embedding Ollama
- giữ `working_dir` cố định rồi chỉ đổi generator LLM cho benchmark

---

## 6. Fix 3: query CLI không được tự ý lệch embedding

## 6.1 Source hiện tại trong `query_graph.py`

File:

```text
query_graph.py
```

Đoạn hiện tại:

```python
if args.local_llm_backend == "turboquant":
    provider = "openai"
    model = args.model or "qwen2.5-7b-instruct-q8-turbo3"
    llm_base_url = args.base_url or "http://localhost:8080/v1"
    embedding_provider = args.embedding_provider or "ollama"
    embedding_base_url = args.embedding_base_url or "http://localhost:11434"
    llm_max_async = args.llm_max_async or 1
    llm_timeout = args.llm_timeout or 600.0
```

Nguồn:

- `query_graph.py:146-153`

## 6.2 Vì sao source hiện tại sai về mặt thực nghiệm

Nếu bạn chỉ muốn đổi generator từ cloud sang local TurboQuant, thì embedding không được tự ý đổi theo.

Nhưng code hiện tại đang làm đúng điều đó:

```text
bật --local_llm_backend turboquant
=> nếu không truyền embedding args
=> embedding_provider bị ép sang ollama
```

Điều này làm thí nghiệm bị bẩn:

- bạn tưởng mình chỉ đổi generator
- thực tế retrieval embedding cũng đổi

## 6.3 Hướng fix đề xuất

### 6.3.1 Quy tắc mới

Khi `--local_llm_backend turboquant`:

- chỉ override LLM runtime:
  - provider
  - model
  - base_url
  - async
  - timeout
- không override embedding nếu user không truyền embedding args

### 6.3.2 Nếu có `build_manifest.json`

Thì query sẽ:

1. đọc manifest trong `working_dir`
2. nếu user không truyền embedding args:
   - tự lấy `embedding_provider`
   - `embedding_model`
   - `embedding_dim`
   - `embedding_device`
   - `embedding_batch_size`
   - `embedding_max_tokens`

### 6.3.3 Prefix query cho Nomic

Nếu:

- `embedding_provider == huggingface`
- `embedding_model == nomic-ai/nomic-embed-text-v1.5`
- user không truyền `--embedding_prefix`

thì query-time default nên là:

```text
search_query:
```

chứ không phải `search_document:`

## 6.4 Code cũ và code mới đề xuất

### Code cũ

```python
embedding_provider = args.embedding_provider or "ollama"
embedding_base_url = args.embedding_base_url or "http://localhost:11434"
```

### Code mới đề xuất

```python
embedding_provider = args.embedding_provider
embedding_base_url = args.embedding_base_url
```

và sau đó:

```python
manifest = load_build_manifest(args.working_dir) if args.working_dir else {}

if not embedding_provider and manifest.get("embedding_provider"):
    embedding_provider = manifest["embedding_provider"]
if not embedding_model and manifest.get("embedding_model"):
    embedding_model = manifest["embedding_model"]
if not embedding_dim and manifest.get("embedding_dim"):
    embedding_dim = manifest["embedding_dim"]
if not embedding_device and manifest.get("embedding_device"):
    embedding_device = manifest["embedding_device"]
if not embedding_batch_size and manifest.get("embedding_batch_size"):
    embedding_batch_size = manifest["embedding_batch_size"]
if not embedding_max_tokens and manifest.get("embedding_max_tokens"):
    embedding_max_tokens = manifest["embedding_max_tokens"]

if (
    embedding_provider == "huggingface"
    and embedding_model == "nomic-ai/nomic-embed-text-v1.5"
    and not embedding_prefix
):
    embedding_prefix = "search_query: "
```

## 6.5 Vì sao code mới đúng hơn

Vì nó phân tách rõ:

- graph artifact
- query generator
- retrieval embedding

Bạn có thể:

- giữ `working_dir` cố định
- giữ embedding cố định
- đổi riêng generator giữa TurboQuant và Gemini

Đó mới là so sánh sạch.

---

## 7. Fix 4: `build_graph.py` cũng đang có lỗi override embedding tương tự

## 7.1 Source hiện tại

File:

```text
build_graph.py
```

Đoạn hiện tại:

```python
if args.local_llm_backend == "turboquant":
    provider = "openai"
    model = args.model or "qwen2.5-7b-instruct-q8-turbo3"
    llm_base_url = args.base_url or "http://localhost:8080/v1"
    embedding_provider = args.embedding_provider or "ollama"
    embedding_base_url = args.embedding_base_url or "http://localhost:11434"
    llm_max_async = args.llm_max_async or 1
```

Nguồn:

- `build_graph.py:128-135`

## 7.2 Vấn đề

Nếu config build của bạn đang là HuggingFace embedding mà bạn chỉ bật:

```bash
--local_llm_backend turboquant
```

thì build có thể bị ép embedding sang Ollama nếu bạn quên truyền lại embedding args.

## 7.3 Fix đề xuất

### Code cũ

```python
embedding_provider = args.embedding_provider or "ollama"
embedding_base_url = args.embedding_base_url or "http://localhost:11434"
```

### Code mới đề xuất

```python
embedding_provider = args.embedding_provider
embedding_base_url = args.embedding_base_url
```

Nếu user không truyền embedding override, hãy giữ nguyên config file.

## 7.4 Vì sao cần sửa

Vì `local_llm_backend` chỉ nên nói về LLM generation path, không nên vô tình đổi embedding backend.

---

## 8. Fix 5: bug thật trong supplemental retrieval

## 8.1 Source hiện tại

File:

```text
tgrag/src/core/querying.py
```

Đoạn hiện tại:

```python
relation_node_datas = await asyncio.gather(
    *[knowledge_graph_inst.get_node(r["entity_name"]) for r in relation_results]
)
node_degrees = await asyncio.gather(
    *[knowledge_graph_inst.node_degree(r["entity_name"]) for r in relation_results]
)
relation_node_datas = []
for k, n, d in zip(relation_results, relation_node_datas, node_degrees):
    ...
```

và tương tự cho:

- `broader_node_datas`
- `general_node_datas`

Nguồn:

- `tgrag/src/core/querying.py:1632-1639`
- `tgrag/src/core/querying.py:1682-1689`
- `tgrag/src/core/querying.py:1711-1718`

## 8.2 Vì sao sai

List vừa retrieve xong lại bị reset thành `[]`, nên vòng `zip(...)` gần như không chạy thật.

## 8.3 Code mới đề xuất

### Code cũ

```python
relation_node_datas = await asyncio.gather(...)
node_degrees = await asyncio.gather(...)
relation_node_datas = []
for k, n, d in zip(relation_results, relation_node_datas, node_degrees):
    ...
```

### Code mới đề xuất

```python
relation_nodes = await asyncio.gather(...)
node_degrees = await asyncio.gather(...)
relation_node_datas = []
for k, n, d in zip(relation_results, relation_nodes, node_degrees):
    ...
```

Tương tự với:

- `broader_nodes`
- `general_nodes`

## 8.4 Vì sao fix này đáng làm ngay

Đây là bug logic rõ ràng, phạm vi nhỏ, rủi ro thấp, và cải thiện recall cho supplemental retrieval.

---

## 9. Fix 6: local query hiện đang bỏ phần lớn graph evidence

## 9.1 Source hiện tại

File:

```text
tgrag/src/core/querying.py
```

Đoạn hiện tại:

```python
logger.info("Building context for LOCAL query ")
logger.info("Only using text units (original chunks), not entities/relations/communities")
...
context = "".join(processed_chunks)
...
logger.info(f"[BUILD CONTEXT] Skipped {len(node_datas)} entities, {len(use_relations)} relations, {len(use_communities)} communities")
return context, retrieval_details_summary
```

Nguồn:

- `tgrag/src/core/querying.py:1895-1941`

## 9.2 Vì sao source hiện tại làm query tệ

Local query path hiện tại có retrieve qua graph, nhưng prompt cuối chỉ chứa raw chunk.

Nó bỏ:

- entity tables
- relation tables
- community tables

Trong khi prompt `local_rag_response` lại mong chờ structured `Data tables`.

Nguồn:

- `tgrag/configs/prompts.yaml:353-381`

## 9.3 Hướng fix đề xuất

### Mức tối thiểu

Giữ PPR + chunk retrieval hiện tại, nhưng context builder phải đưa lại:

1. `Entities`
2. `Relationships`
3. `Communities`
4. `Chunks`

theo budget hiện có:

- `local_max_token_for_local_context`
- `local_max_token_for_community_report`
- `local_max_token_for_text_unit`

### Code cũ

```python
logger.info("Only using text units (original chunks), not entities/relations/communities")
...
context = "".join(processed_chunks)
```

### Code mới đề xuất

```python
entity_table = build_entity_table(node_datas, query_param.local_max_token_for_local_context)
relation_table = build_relation_table(use_relations, query_param.local_max_token_for_local_context)
community_table = build_community_table(use_communities, query_param.local_max_token_for_community_report)
chunk_table = build_chunk_table(use_text_units, query_param.local_max_token_for_text_unit)

context = f"""
---Entities---
{entity_table}

---Relationships---
{relation_table}

---Communities---
{community_table}

---Source Chunks---
{chunk_table}
"""
```

## 9.4 Vì sao code mới hợp lý

Nó vẫn dùng core retrieval hiện có, nhưng thôi không vứt bỏ graph evidence ở bước cuối.

Đây là patch nhỏ hơn rất nhiều so với viết lại toàn bộ thuật toán query.

---

## 10. Fix 7: demo hiện tại gây nhầm giữa TurboQuant, Gemini và Ollama

## 10.1 Source hiện tại trong `demo.py`

### 10.1.1 Demo có runtime helper riêng, rất đơn giản

File:

```text
demo.py
```

Đoạn hiện tại:

```python
def apply_runtime_overrides(args, override_config):
    if args.provider:
        override_config["provider"] = args.provider
    if args.model:
        override_config["model"] = args.model
    if args.base_url:
        override_config["llm_base_url"] = args.base_url
    if args.embedding_base_url:
        override_config["embedding_base_url"] = args.embedding_base_url
    if args.local_llm_backend:
        override_config["local_llm_backend"] = args.local_llm_backend
```

Nguồn:

- `demo.py:31-43`

Vấn đề:

- demo không sync với logic runtime của `query_graph.py`
- demo không có concept manifest
- demo không có field chọn embedding provider/model đúng nghĩa

### 10.1.2 Quick Preset hiện tại chỉ set provider/base_url/mode

Ví dụ preset local TurboQuant:

```python
st.session_state.provider_select = "openai"
st.session_state.base_url_input = "http://localhost:8080/v1"
st.session_state.query_mode_select = "local"
st.session_state.enable_entity_retrieval_toggle = True
st.session_state.seed_node_method_select = "entities"
```

Nguồn:

- `demo.py:215-224`

Vấn đề:

- không set embedding provider/model
- không đọc manifest build
- rất dễ query graph build bằng HF nhưng runtime retrieval lại không khớp

## 10.2 Hướng fix demo đề xuất

### 10.2.1 Không giữ helper runtime riêng trong demo

Hướng tốt hơn:

- tách logic runtime override chung sang một module dùng chung
- cả `query_graph.py`, `build_graph.py`, `demo.py`, `run_batch_queries.py` cùng gọi

Tên module đề xuất:

```text
tgrag/src/runtime/runtime_overrides.py
```

### 10.2.2 Demo phải có manifest-aware UI

Thêm các thành phần UI:

- `Use build manifest defaults` toggle, mặc định `ON`
- `Embedding Provider`
- `Embedding Model`
- `Embedding Device`
- `Embedding Base URL`
- `Embedding Prefix`

### 10.2.3 Khi user điền `Working Directory`

Demo nên:

1. đọc `build_manifest.json`
2. auto-fill các field
3. nếu user chọn cấu hình khác manifest:
   - hiện warning rõ

Ví dụ warning:

```text
Graph này được build bằng HuggingFace Nomic, nhưng query hiện đang chọn Ollama embedding.
Điều này làm retrieval không còn là cùng embedding space.
```

### 10.2.4 Quick preset mới đề xuất

Thay preset hiện tại bằng:

1. `Local TurboQuant + Follow Build Manifest`
2. `Gemini + Follow Build Manifest`
3. `Ollama + Follow Build Manifest`
4. `Manual Advanced`

### 10.2.5 Thay đổi trong `scripts/run_demo_stack.sh`

Hiện tại script default:

```bash
CTX=131072
PARALLEL=4
MODEL_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072
```

Nguồn:

- `scripts/run_demo_stack.sh:14-20`

Đề xuất đổi default thành profile an toàn hơn:

```bash
CTX=131072
PARALLEL=2
MODEL_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072
```

Lý do:

- demo đang là điểm vào phổ biến nhất
- không nên mặc định bằng một profile đã từng gây overflow community ở build run trước

---

## 10.3 Ghi chú riêng về HuggingFace embedding vs Ollama embedding

Phần này cần nói rất rõ, vì nếu diễn đạt sai thì sau này benchmark sẽ bị hiểu nhầm.

### 10.3.1 Kết luận ngắn

Nếu bạn muốn dùng `huggingface` embedding cho graph build và query, điều đó là hợp lý.

Nhưng lý do đúng nên viết là:

```text
HF embedding trong repo hiện tại kiểm soát được sequence length / prefix / device / batch rõ hơn,
không phải cứ mặc định là "HF luôn có context window dài hơn Ollama" trong mọi cách chạy.
```

### 10.3.2 Source code hiện tại cho thấy gì

#### Nhánh HuggingFace

File:

```text
tgrag/src/llm/huggingface_embedding.py
```

Code hiện tại:

```python
model = SentenceTransformer(
    model_name,
    device=device,
    trust_remote_code=trust_remote_code,
)
model.max_seq_length = max_tokens
```

và:

```python
async def huggingface_embedding(
    texts: List[str],
    model: str = "nomic-ai/nomic-embed-text-v1.5",
    device: str = "cpu",
    batch_size: int = 16,
    max_tokens: int = 7500,
    prefix: str = "search_document: ",
```

Nguồn:

- `tgrag/src/llm/huggingface_embedding.py:32-38`
- `tgrag/src/llm/huggingface_embedding.py:42-49`

Điều này có nghĩa là nhánh HF trong repo đang cho bạn kiểm soát trực tiếp:

- `embedding_model`
- `embedding_device`
- `embedding_batch_size`
- `embedding_max_tokens`
- `embedding_prefix`

#### Nhánh Ollama

File:

```text
tgrag/src/llm/embedding.py
```

Code hiện tại:

```python
@wrap_embedding_func_with_attrs(embedding_dim=768, max_token_size=8192)
async def ollama_embedding(
    texts: List[str],
    model: str = "nomic-embed-text",
    base_url: Optional[str] = None
) -> np.ndarray:
    ...
    payload = {
        "model": model,
        "prompt": text,
    }
```

Nguồn:

- `tgrag/src/llm/embedding.py:117-123`
- `tgrag/src/llm/embedding.py:141-148`

Điều quan trọng là:

- code Ollama hiện **không có tham số** `max_tokens`
- code Ollama hiện **không có tham số** `prefix`
- code Ollama hiện chỉ gửi raw `prompt` sang `/api/embeddings`

Nói ngắn:

```text
HF path trong repo được điều khiển rõ hơn.
Ollama path trong repo hiện đơn giản hơn và ít "guard rail" hơn.
```

### 10.3.3 Về context/window của chính model Nomic

Theo model card chính thức của `nomic-ai/nomic-embed-text-v1.5`, model này hỗ trợ long-context và bảng trong model card ghi:

- `nomic-embed-text-v1.5` có `SeqLen 8192`
- model card cũng nói model hỗ trợ scale sequence length vượt `2048`

Nguồn:

- Hugging Face model card: https://huggingface.co/nomic-ai/nomic-embed-text-v1.5

Trong khi đó, phía Ollama hiện có dấu hiệu không nhất quán ở tài liệu public:

- trang library của `nomic-embed-text` hiển thị `2K context window`
- nhưng blob params public của model lại có `num_ctx: 8192`

Nguồn:

- Ollama library page: https://ollama.com/library/nomic-embed-text
- Ollama params blob: https://ollama.com/library/nomic-embed-text/blobs/ce4a164fc046

Vì vậy, nếu viết thật chặt chẽ thì phải nói:

```text
không nên lấy "HF dài hơn Ollama" làm luận điểm tuyệt đối.
Điều chắc chắn hơn là:
HF path trong repo hiện cho phép bạn kiểm soát và tái lập cấu hình embedding tốt hơn.
```

### 10.3.4 Vậy trong repo này, khi nào nên ưu tiên HF embedding?

Nên ưu tiên `huggingface` embedding khi:

1. bạn muốn build/query với `nomic-ai/nomic-embed-text-v1.5`
2. bạn cần kiểm soát rõ `embedding_max_tokens`
3. bạn cần dùng đúng prefix:
   - build/index: `search_document:`
   - query: `search_query:`
4. bạn muốn benchmark retrieval tái lập được

### 10.3.5 Vì sao demo hiện tại vẫn chưa phù hợp cho benchmark nghiêm túc với HF-built graph

Không phải vì HF embedding có vấn đề.

Lý do thật là:

- demo hiện chưa có field embedding đầy đủ
- demo chưa đọc manifest build
- demo chưa tự ép `embedding_provider/model/prefix/max_tokens` theo graph đã build

Nên câu cần ghi rõ là:

```text
demo hiện tại chưa phù hợp để benchmark nghiêm túc với graph build bằng HF embedding,
không phải vì HF embedding kém,
mà vì demo chưa đảm bảo query-time embedding bám đúng build-time embedding.
```

### 10.3.6 Câu khuyến nghị nên dùng trong docs

Có thể dùng nguyên văn câu sau:

```text
Nếu graph được build bằng HuggingFace embedding, đặc biệt là `nomic-ai/nomic-embed-text-v1.5`,
hãy ưu tiên CLI cho benchmark.
Lý do không phải chỉ vì "HF có context dài hơn Ollama",
mà vì nhánh HF trong repo hiện cho phép kiểm soát `embedding_model`, `embedding_device`,
`embedding_batch_size`, `embedding_max_tokens` và `embedding_prefix` rõ hơn,
giúp retrieval tái lập được hơn so với demo/UI hiện tại.
```

---

## 11. Hướng chạy hiện tại nếu CHƯA patch code

Phần này là workaround để bạn dùng ngay với code hiện tại.

## 11.1 Start server an toàn hơn

Khuyến nghị dùng `parallel=2`, không dùng `parallel=4` cho build lại community.

```bash
tmux kill-session -t llm_srv 2>/dev/null || true
tmux new -s llm_srv -d
tmux send-keys -t llm_srv "conda activate turboquant && cd /home/guest/Projects/Research/llama-cpp-turboquant && ./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --host 127.0.0.1 --port 8080 \
  -ctk q8_0 -ctv turbo3 -fa on -ngl 99 \
  -c 131072 --parallel 2 --n-predict 3072" C-m

curl -sS http://localhost:8080/v1/models
```

## 11.2 Nếu cần rebuild NGAY trên code hiện tại, phải dùng config riêng

Vì `build_graph.py` hiện chưa có:

```text
--best_model_max_token_size
```

nên nếu muốn rebuild ngay trước khi patch code, bạn phải:

1. copy `tgrag/configs/config.yaml` sang một file mới
2. chỉnh:

```yaml
best_model_max_token_size: 60000
```

hoặc thấp hơn tùy theo `n_ctx / parallel`

Ví dụ file:

```text
tgrag/configs/config_local_turboquant_build_fix.yaml
```

Sau đó build bằng CLI nhưng vẫn phải truyền explicit HF embedding args để tránh bị override sang Ollama:

```bash
python build_graph.py \
  --config tgrag/configs/config_local_turboquant_build_fix.yaml \
  --output_dir outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_fix_prepatch \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 384 \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --embedding_prefix "search_document: " \
  --llm_max_async 2 \
  --llm_timeout 900 \
  --entity_extraction_timeout 21600
```

Giải thích:

- phải sửa config vì current CLI chưa expose `best_model_max_token_size`
- phải explicit HF embedding vì current `build_graph.py` sẽ ép sang Ollama nếu chỉ bật `--local_llm_backend turboquant`

## 11.3 Query `fresh_v2` bằng local TurboQuant, giữ đúng HF embedding

Có, bạn làm được.

Lệnh mẫu:

```bash
python query_graph.py \
  --question "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --base_url http://localhost:8080/v1 \
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

Giải thích:

- `working_dir` vẫn là graph cũ `fresh_v2`
- LLM trả lời là TurboQuant local
- retrieval embedding vẫn là HF Nomic

## 11.4 Query cùng graph `fresh_v2` bằng Gemini có được không?

Có.

Điều kiện đúng là:

- vẫn giữ `working_dir` đó
- vẫn giữ retrieval embedding khớp với build
- chỉ đổi generator sang Gemini

Lệnh mẫu:

```bash
python query_graph.py \
  --question "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?" \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
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

## 11.5 Cách hiểu kết quả TurboQuant vs Gemini trên cùng graph

Nếu:

- retrieval giống nhau
- Gemini trả lời tốt hơn TurboQuant

thì khác biệt nằm chủ yếu ở generator.

Nếu:

- cả hai cùng trả lời sai theo cùng kiểu

thì lỗi chính nằm ở graph/retrieval/query path.

Nếu:

- retrieval khác hẳn nhau

thì runtime config hoặc embedding config của bạn đang không cố định.

## 11.6 Batch ECT-QA với `run_batch_queries.py` cho local TurboQuant

Lệnh mẫu:

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --questions ect-qa/questions/local_new.jsonl \
  --output results/preds/pred_fresh_v2_turboquant_hf_local_new.jsonl \
  --mode local \
  --local_llm_backend turboquant \
  --llm_model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --llm_base_url http://localhost:8080/v1 \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --embedding_prefix "search_query: " \
  --llm_max_async 1 \
  --llm_timeout 900
```

## 11.7 Batch ECT-QA với cùng graph nhưng query bằng Gemini

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2 \
  --questions ect-qa/questions/local_new.jsonl \
  --output results/preds/pred_fresh_v2_gemini_hf_local_new.jsonl \
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

## 11.8 Demo hiện tại nên dùng thế nào nếu chưa patch

Khuyến nghị thực dụng:

```text
Nếu graph được build bằng HuggingFace embedding,
không nên dùng demo hiện tại để benchmark nghiêm túc.
Hãy dùng CLI.
```

Lý do:

- demo hiện tại không có field embedding provider/model hoàn chỉnh
- demo không đọc build manifest
- demo không ép query embedding khớp build embedding

Nếu vẫn muốn dùng demo tạm thời:

- `Provider = openai` khi dùng local TurboQuant server
- `Model = server alias`
- `Base URL = http://localhost:8080/v1`
- `Working Directory = outputs/build_graph/...`

Nhưng phải hiểu là demo hiện tại chưa đủ chặt cho benchmark HF-built graph.

---

## 12. Hướng chạy SAU KHI patch code

## 12.1 Rebuild graph sạch bằng local TurboQuant + HF Nomic

Giả sử đã patch:

- `build_graph.py` có `--best_model_max_token_size`
- build có `build_manifest.json`

Lệnh mẫu:

```bash
python build_graph.py \
  --config tgrag/configs/config.yaml \
  --output_dir outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_fix1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 384 \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_max_tokens 7500 \
  --embedding_prefix "search_document: " \
  --llm_max_async 2 \
  --best_model_max_token_size 60000 \
  --llm_timeout 900 \
  --entity_extraction_timeout 21600
```

## 12.2 Query graph fix bằng local TurboQuant

```bash
python query_graph.py \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_fix1 \
  --question "What was DXC Technology's revenue performance in Q1 2022?" \
  --mode local \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --base_url http://localhost:8080/v1 \
  --llm_max_async 1 \
  --llm_timeout 900 \
  --show_retrieval
```

Khi patch manifest-aware đã có, bạn không cần lặp lại toàn bộ embedding args nếu muốn follow manifest.

## 12.3 Query cùng graph fix bằng Gemini

```bash
python query_graph.py \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_fix1 \
  --question "What was DXC Technology's revenue performance in Q1 2022?" \
  --mode local \
  --provider gemini \
  --model gemini-2.5-flash \
  --show_retrieval
```

Điều kiện:

- manifest-aware query phải tự sync embedding từ build output
- hoặc bạn vẫn truyền tay embedding args nếu chưa bật auto-sync

## 12.4 Batch ECT-QA sau patch

### Local TurboQuant

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_fix1 \
  --questions ect-qa/questions/local_new.jsonl \
  --output results/preds/pred_fix1_turboquant_local_new.jsonl \
  --mode local \
  --local_llm_backend turboquant \
  --llm_model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --llm_base_url http://localhost:8080/v1 \
  --llm_max_async 1 \
  --llm_timeout 900
```

### Gemini

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_fix1 \
  --questions ect-qa/questions/local_new.jsonl \
  --output results/preds/pred_fix1_gemini_local_new.jsonl \
  --mode local \
  --provider gemini \
  --model gemini-2.5-flash
```

---

## 13. Kế hoạch sửa docs

Các tài liệu nên sửa sau khi patch code:

1. `md/CLI/query_graph.md`
2. `md/CLI/start_server.md`
3. `md/runbooks/demo_setup_and_db_graph_flow.md`
4. `md/runbooks/turboquant_intervention_modes_cli.md`

## 13.1 Chỗ cần sửa trong docs

### `md/CLI/query_graph.md`

Sửa canonical command ở đầu file để không còn thiếu embedding rule.

### `md/CLI/start_server.md`

Hiện tài liệu có nhắc `scripts/run_7b_build_stack.sh`, nhưng file đó không còn có trong repo hiện tại.

Nên:

- hoặc xóa phần nhắc script này
- hoặc tạo lại script thật

### `md/runbooks/demo_setup_and_db_graph_flow.md`

Phải thêm quy tắc:

```text
LLM query có thể đổi
nhưng retrieval embedding phải khớp build embedding
```

### `scripts/run_demo_stack.sh`

Nên đổi default từ `p4` sang `p2`.

---

## 14. Thứ tự triển khai nếu bạn đồng ý cho patch

Tôi sẽ làm theo thứ tự này:

1. `fix/community-budget-and-build-manifest`
   - expose `best_model_max_token_size` trong `build_graph.py`
   - bỏ default ép embedding sang Ollama trong build runtime override
   - ghi `build_manifest.json`

2. `fix/query-demo-local-embedding-sync`
   - query CLI đọc manifest
   - bỏ default ép embedding sang Ollama trong query runtime override
   - thêm `search_query:` default cho HF Nomic query
   - fix bug reset list ở supplemental retrieval
   - demo đọc manifest và có field embedding rõ ràng

3. `fix/local-runtime-query-demo-endtoend`
   - sửa local context builder để đưa lại entities/relations/communities vào prompt
   - cập nhật docs và runbooks

4. Sau đó mới chạy:
   - rebuild graph sạch
   - query lại bằng local TurboQuant
   - query lại bằng Gemini trên cùng graph
   - batch ECT-QA local/global phù hợp

---

## 15. Kết luận ngắn

Nếu mục tiêu của bạn là:

```text
build local bằng TurboQuant
query local bằng TurboQuant
và so sánh công bằng với Gemini trên cùng graph output
```

thì patch bắt buộc nên có là:

1. build budget phải bám slot context thật
2. build output phải có manifest
3. query/demo không được tự ý đổi embedding backend
4. local query phải ngừng vứt bỏ graph evidence ở bước build context

Trước khi patch xong, cách dùng an toàn nhất là:

- build/query bằng CLI
- explicit toàn bộ embedding args
- demo chỉ dùng để xem tương tác, không dùng để benchmark nghiêm túc với HF-built graph
