# Build Community: Root Cause cũ, hướng fix, và kết quả `v4`

## Mục đích

Tài liệu này gom lại thành một chỗ:

1. lỗi build cũ ở `v3` là gì;
2. code cũ gây lỗi như thế nào;
3. code mới đã sửa ra sao;
4. test `v4` khác gì so với `v3`;
5. còn giới hạn gì trước khi chạy full `384 docs`.

Tài liệu kết quả test thực tế đi kèm:

- [v3_build_failure_analysis.md](./v3_build_failure_analysis.md)
- [v4_build_fix_test_10docs.md](./v4_build_fix_test_10docs.md)

## 1. Symptom cũ ở `v3`

Run lỗi cũ:

- usage log: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3.jsonl](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3.jsonl:1)
- output: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3)

Điểm quan trọng:

- `v3` có `24` dòng `api_error` trong usage log.
- output community có `8` report lỗi kiểu `Error Report for ...`.
- `v3` vẫn ghi output, nhưng đó không phải clean build.

Tức là:

```text
build không crash toàn bộ
nhưng phase community đã hỏng một phần
```

## 2. Code cũ gây lỗi ở đâu

Commit nền trước khi sửa build branch:

```text
main@2c93df6
```

### 2.1 `build_graph.py` cũ chỉ healthcheck server, không lấy slot context thật

Code cũ:

```python
def xac_nhan_turboquant(base_url: str = None, strict: bool = False) -> bool:
    base_url = base_url or os.getenv("OPENAI_BASE_URL", "http://localhost:8080/v1")
    props_url = base_url.replace("/v1", "").rstrip("/") + "/props"

    try:
        with urllib.request.urlopen(props_url, timeout=3) as response:
            if response.status == 200:
                response.read()
                ...
                return True
```

Nguồn cũ: `build_graph.py` ở `main@2c93df6`, vùng dòng `43-71`.

Vấn đề:

- code chỉ check rằng `/props` trả `200`;
- nhưng không trích `default_generation_settings.n_ctx`;
- không biết slot context thật trên từng request;
- không tự clamp `best_model_max_token_size`.

Với local `llama-server`, đây là lỗ hổng quan trọng vì `-c 131072 --parallel 2` không đồng nghĩa mỗi request được `131072`; slot thực tế chỉ còn `65536`.

### 2.2 `build_graph.py` cũ không có CLI/runtime control cho budget build

Code cũ:

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

Nguồn cũ: `build_graph.py` ở `main@2c93df6`, vùng dòng `625-642`.

Vấn đề:

- build budget chỉ bám config/app default;
- CLI không có cách override sạch theo slot context thật của server;
- khó kiểm soát khi đổi `--parallel`.

### 2.3 `build_graph.py` cũ không ghi `build_manifest.json`

Code cũ khi init/build chỉ:

```python
graph_rag = create_temporal_graphrag_from_config(...)
...
graph_rag.insert(prepared_docs)
```

Nguồn cũ: `build_graph.py` ở `main@2c93df6`, vùng dòng `675-755`.

Vấn đề:

- output không lưu runtime build metadata quan trọng;
- query/demo về sau khó biết graph đã build bằng provider/model/embedding/budget nào;
- rất dễ drift runtime khi query lại.

### 2.4 `building.py` cũ truncate temporal edges theo sai field

Code cũ:

```python
edges_may_truncate_list_data = truncate_list_by_token_size(
    edges_list_data, key=lambda x: x[3], max_token_size=max_token_size // 2
)
```

Nguồn cũ: `tgrag/src/core/building.py` ở `main@2c93df6`, vùng dòng `1412-1414`.

Với temporal edge row:

```python
[id, timestamp, source, target, description, rank]
```

thì:

- `x[3]` là `target`
- `x[4]` mới là `description`

Vấn đề:

- app tưởng đang truncate theo text dài nhất của edge;
- thực tế chỉ đo theo tên `target` vốn rất ngắn;
- kết quả là prompt temporal community không bị cắt đủ;
- prompt có thể phình rất lớn dù app vẫn tưởng là trong budget.

### 2.5 `building.py` cũ match temporal edge sai tuple khi fallback sub-community

Code cũ:

```python
report_exclude_edges_list_data = [
    e for e in edges_list_data if (e[1], e[2]) not in contain_edges
]
report_include_edges_list_data = [
    e for e in edges_list_data if (e[1], e[2]) in contain_edges
]
```

Nguồn cũ: `tgrag/src/core/building.py` ở `main@2c93df6`, vùng dòng `1442-1446`.

Với temporal edge row:

```python
[id, timestamp, source, target, description, rank]
```

thì tuple nhận diện hợp lý phải là:

```python
(timestamp, source, target)
```

Vấn đề:

- fallback theo sub-community không giữ được temporal edges đúng;
- include/exclude bị sai;
- prompt có thể vừa dài vừa sai ưu tiên.

### 2.6 `building.py` cũ hardcode `response_format` khi generate temporal report

Code cũ:

```python
response = await use_llm_func(prompt, response_format={'type': 'json_object'})
```

Nguồn cũ: `tgrag/src/core/building.py` ở `main@2c93df6`, vùng dòng `1963`.

Vấn đề:

- bỏ qua `llm_extra_kwargs` đã được config sẵn cho community report;
- làm local runtime kém nhất quán hơn so với config path còn lại;
- khó debug khi đổi provider/backend.

### 2.7 `building.py` cũ ghi error title quá mơ hồ

Code cũ:

```python
return {
    "title": f"Error Report for {community.get('name', 'Unknown')}",
    ...
}
```

Nguồn cũ: `tgrag/src/core/building.py` ở `main@2c93df6`, vùng dòng `2015-2023`.

Vấn đề:

- với temporal community thường không có `name` phù hợp;
- output dễ ra `Error Report for Unknown`;
- khó map ngược về `timestamp` hoặc level cộng đồng nào bị hỏng.

## 3. Vì sao code cũ dẫn tới fail build

Lỗi build cũ đến từ tổ hợp hai lớp nguyên nhân:

### 3.1 Lỗi logic trong pack temporal community

- truncate theo `target` thay vì `description`
- fallback sub-community match sai edge tuple

Hai lỗi này làm prompt temporal community phình hơn nhiều so với điều app tưởng tượng.

### 3.2 Lỗi runtime budget mismatch với `llama-server`

App pack theo budget logic nội bộ, nhưng request local thực tế bị giới hạn bởi:

```text
n_ctx_seq = floor(n_ctx / parallel)
```

Ví dụ:

```text
-c 131072 --parallel 2  => slot thực = 65536
-c 131072 --parallel 4  => slot thực = 32768
```

Nếu app không tự đọc `/props` rồi clamp budget, thì prompt vẫn có thể bị gửi sang server ở kích thước mà server không chấp nhận.

## 4. Code mới đã sửa như thế nào

### 4.1 `build_graph.py` mới đọc `/props` và tự resolve budget

Code mới thêm helper:

- `_props_url_from_base_url()`
- `fetch_server_props()`
- `_extract_slot_context_from_props()`
- `resolve_best_model_token_budget()`

Nguồn: [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:44), [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:163)

Ý nghĩa:

- lấy `default_generation_settings.n_ctx` từ server thật;
- lấy `total_slots`;
- tự tính:

```text
safe_budget = slot_n_ctx - community_token_headroom
```

- nếu budget người dùng/config lớn hơn mức an toàn thì tự clamp.

### 4.2 `build_graph.py` mới expose CLI budget controls

Code mới:

```python
parser.add_argument('--best_model_max_token_size', ...)
parser.add_argument('--community_token_headroom', ...)
```

Nguồn: [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:720)

Ý nghĩa:

- có thể override budget build bằng CLI khi cần;
- có thể giữ headroom tách biệt khỏi slot context.

### 4.3 `build_graph.py` mới ghi `build_manifest.json`

Code mới:

```python
def write_build_manifest(graph_rag, build_status: str, error_message: str = None) -> None:
    ...
```

Nguồn: [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:786)

Manifest mới ghi:

- provider/model/base_url
- wire protocol
- `best_model_max_token_size`
- `community_token_headroom`
- `server_slot_tokens`
- `server_total_slots`
- embedding runtime
- corpus path / num docs
- build status

Ý nghĩa:

- query/demo về sau có thể biết chính xác graph này được build như thế nào;
- dễ debug drift runtime giữa build và query.

### 4.4 `building.py` mới truncate temporal edges theo `description`

Code mới:

```python
edges_may_truncate_list_data = truncate_list_by_token_size(
    edges_list_data, key=lambda x: x[4], max_token_size=max_token_size // 2
)
```

Nguồn: [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1412)

Ý nghĩa:

- truncate bây giờ bám đúng text dài thật sự của edge;
- prompt community giảm về gần budget logic dự kiến.

### 4.5 `building.py` mới match temporal edge đúng tuple

Code mới:

```python
report_exclude_edges_list_data = [
    e for e in edges_list_data if (e[1], e[2], e[3]) not in contain_edges
]
report_include_edges_list_data = [
    e for e in edges_list_data if (e[1], e[2], e[3]) in contain_edges
]
```

Nguồn: [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1442)

Ý nghĩa:

- fallback sub-community giữ edge đúng hơn;
- packing nhất quán hơn khi cộng đồng lớn bị cắt nhỏ.

### 4.6 `building.py` mới dùng `llm_extra_kwargs`

Code mới:

```python
response = await use_llm_func(prompt, **llm_extra_kwargs)
```

Nguồn: [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1963)

Ý nghĩa:

- temporal community report đi theo runtime/config thống nhất;
- không hardcode riêng một kiểu gọi local LLM.

### 4.7 `building.py` mới ghi label error rõ hơn

Code mới:

```python
community_label = (
    community.get("name")
    or community.get("title")
    or community.get("timestamp")
    or "Unknown"
)
```

Nguồn: [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:2017)

Ý nghĩa:

- nếu còn fail về sau, artifact sẽ dễ lần ngược hơn;
- không còn quá nhiều `Unknown`.

## 5. Kết quả test `v4` khác gì `v3`

Run test mới:

- [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4)
- [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:1)
- [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl:1)

### 5.1 Khác biệt định lượng

`v3`:

- `api_error = 24`
- có `8` error community reports

`v4` test 10-doc:

- `api_success = 101`
- `cache_hit = 1`
- `api_error = 0`
- `error_reports = 0`

### 5.2 Khác biệt runtime

`v4` manifest cho thấy app bây giờ biết rõ:

- `server_slot_tokens = 65536`
- `server_total_slots = 2`
- `best_model_max_token_size = 61440`
- `budget_resolution = auto_from_server_props`

Nguồn: [build_manifest.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4/build_manifest.json:1)

### 5.3 Khác biệt về khả năng kiểm tra run

`v3`:

- không có build log text nếu shell không tự `tee`
- không có manifest

`v4`:

- có build log text
- có usage log
- có manifest
- grep được ngay các dấu:
  - `Slot context`
  - `Community pack budget`
  - `BUILD SUMMARY`

## 6. Còn điều gì chưa thể kết luận

Chưa thể kết luận rằng:

```text
full 384 docs giờ chắc chắn sạch hoàn toàn
```

Lý do:

- `v4` hiện mới test `10 docs`;
- prompt community lớn nhất trong bài test vẫn còn cách xa ngưỡng slot `65536`;
- full `384 docs` có hierarchy và density lớn hơn nhiều.

Kết luận đúng phải là:

```text
nhánh build hiện đã sửa đúng root cause cũ
và đã pass test build local sạch trên 10 docs
nhưng vẫn cần chạy thêm 50/100 rồi mới lên full 384 docs
```

## 7. Trạng thái thực dụng

Bạn có thể xem nhánh build hiện tại là:

- đã sửa đúng lỗi cũ ở mức code path;
- đã có runbook/logging tốt hơn;
- đã có bằng chứng thực nghiệm `10 docs`.

Bước kế tiếp hợp lý:

1. push branch `fix/build-community-budget-v4`
2. chạy `50 docs`
3. chạy `100 docs`
4. nếu cả hai đều sạch, mới chạy full `384 docs`
