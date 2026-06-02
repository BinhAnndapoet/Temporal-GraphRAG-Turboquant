# Phân Tích Lỗi Build `v3` Và Vì Sao Không Có File Log Text

File này phân tích run:

- output: [outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3)
- usage log: [results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3.jsonl](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3.jsonl:1)

Mục tiêu:

1. Xác định `v3` lỗi do code hay do cấu hình
2. Chỉ ra cộng đồng nào bị fail
3. Giải thích vì sao không có file `logs/build_graph/...v3.log`

---

## 1. Kết Luận Ngắn

`v3` **không phải clean build**.

Nó đã tạo đủ artifact graph/vector/KV, nhưng vẫn có **8 temporal community reports bị fail** vì prompt gửi sang local `llama-server` vượt quá slot context thực `65536`.

Nguyên nhân là **kết hợp của code bug + cấu hình chưa an toàn**:

1. Có bug thật trong code pack temporal community report
2. App pack prompt sát trần `best_model_max_token_size=65536`
3. Server thực chỉ cho mỗi slot khoảng `65536` token khi chạy `-c 131072 --parallel 2`

Trong run này, **code bug là nguyên nhân gốc mạnh hơn**. Nếu chỉ nhìn cấu hình, prompt không nên phình tới `96k-257k` token như usage log đã ghi.

---

## 2. Bằng Chứng `v3` Vẫn Bị Lỗi Community

### 2.1 Output `v3` có đủ artifact

Run `v3` đã ghi đầy đủ các file chính:

- [kv_store_full_docs.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3/kv_store_full_docs.json:1)
- [kv_store_text_chunks.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3/kv_store_text_chunks.json:1)
- [kv_store_community_reports.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3/kv_store_community_reports.json:1)
- [vdb_entities.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3/vdb_entities.json:1)
- [vdb_relations.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3/vdb_relations.json:1)
- [graph_chunk_entity_relation.graphml](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3/graph_chunk_entity_relation.graphml:1)
- [graph_temporal_hierarchy.graphml](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3/graph_temporal_hierarchy.graphml:1)

Nghĩa là build đã đi đến cuối pipeline và flush output ra disk.

### 2.2 Nhưng community report chứa `Error Report for Unknown`

Trong [kv_store_community_reports.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3/kv_store_community_reports.json:16744) có nhiều record kiểu:

```text
# Error Report for Unknown
Failed to generate report: Error code: 400 - ...
```

Các timestamp/community bị lỗi trong `v3` gồm:

- `"2022-Q2"`
- `"2020-Q4"`
- `"2021-Q4"`
- `"2022-Q3"`
- `"2022-Q4"`
- `"2020"`
- `"2021"`
- `"2022"`

Tổng cộng: **8 failed community reports**

---

## 3. Usage Log Cho Thấy Lỗi Này Lặp Đúng 3 Lần Mỗi Community

File usage log:

- [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3.jsonl](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3.jsonl:1)

Thống kê event:

- `api_success`: `3316`
- `cache_hit`: `294`
- `api_error`: `24`

Đây là tín hiệu rất rõ:

- code temporal report retry tối đa `3` lần
- có `8` community lỗi
- `8 * 3 = 24`

Phần retry nằm ở:

- [_form_single_timestamp_report()](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1940)

Khi fail đủ 3 lần, code không abort build mà trả về object lỗi:

- [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:2011)

Vì vậy build vẫn “xong”, nhưng artifact community đã hỏng cục bộ.

---

## 4. Prompt Overflow Trong `v3` Không Còn 32K, Nhưng Vẫn Vượt 65K

Run `v3` dùng `p2`, tức là:

```text
-c 131072 --parallel 2
```

Suy ra slot context thực tế khoảng:

```text
131072 / 2 = 65536
```

Usage log ghi nhiều lỗi kiểu:

- `request (96323 tokens) exceeds the available context size (65536 tokens)`
- `request (110003 tokens) exceeds the available context size (65536 tokens)`
- `request (114564 tokens) exceeds the available context size (65536 tokens)`
- `request (115682 tokens) exceeds the available context size (65536 tokens)`
- `request (121317 tokens) exceeds the available context size (65536 tokens)`
- `request (121779 tokens) exceeds the available context size (65536 tokens)`
- `request (136549 tokens) exceeds the available context size (65536 tokens)`
- `request (257321 tokens) exceeds the available context size (65536 tokens)`

Những con số này quá lớn để xem là “chỉ thiếu headroom vài nghìn token”.

Điều đó chỉ ra rằng `v3` không đơn thuần hỏng vì `parallel=2` vẫn còn nhỏ, mà prompt đang bị pack sai ở mức logic.

---

## 5. Root Cause Chính: Bug Trong `_pack_single_timestamp_describe()`

Hàm temporal community pack nằm ở:

- [_pack_single_timestamp_describe()](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1478)

### 5.1 Bug 1: truncate temporal edge bằng sai field

Temporal edge row được build theo format:

```python
[id, timestamp, source, target, description, rank]
```

Nhưng khi truncate, code lại dùng:

```python
edges_may_truncate_list_data = truncate_list_by_token_size(
    edges_list_data, key=lambda x: x[3], max_token_size=max_token_size // 2
)
```

Nguồn:

- [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1535)

`x[3]` ở đây là **target**, không phải `description`.

Đúng ra phải là:

```python
key=lambda x: x[4]
```

Hậu quả:

- code tưởng đang cắt theo độ dài edge description
- thực tế chỉ đếm token của tên target entity, rất ngắn
- nên temporal edges hầu như không bị truncate
- prompt temporal community có thể phình cực lớn

Đây là bug code trực tiếp gây overflow.

### 5.2 Bug 2: fallback sub-community của temporal edges cũng dùng index sai

Trong cùng hàm:

```python
report_exclude_edges_list_data = [
    e for e in edges_list_data if (e[1], e[2]) not in contain_edges
]
report_include_edges_list_data = [
    e for e in edges_list_data if (e[1], e[2]) in contain_edges
]
```

Nguồn:

- [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1565)

Nhưng với temporal row:

- `e[1] = timestamp`
- `e[2] = source`
- `e[3] = target`

Trong khi `contain_edges` lại được build từ `c["temporal_edges"]`, tức là tuple temporal edge đầy đủ:

- [_pack_single_community_by_sub_communities()](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1317)

Nghĩa là logic include/exclude temporal edge trong fallback cũng không khớp dữ liệu thực.

Kết luận:

- nhánh fallback sub-community cho temporal report hiện tại **không đáng tin**
- nên dù code có phát hiện `truncated`, phần “cứu” prompt bằng sub-community vẫn có thể hoạt động sai

---

## 6. Cấu Hình Vẫn Có Vấn Đề, Nhưng Là Yếu Tố Phụ

Ngoài bug code, config hiện tại vẫn không an toàn:

### 6.1 App pack prompt theo `best_model_max_token_size`

Temporal report dùng:

```python
max_token_size=global_config["best_model_max_token_size"]
```

Nguồn:

- [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1945)

Nếu giá trị này là `65536`, còn slot thật cũng chỉ `65536`, thì:

- không còn headroom cho wrapper prompt
- không còn headroom cho output tokens
- không có biên an toàn cho chênh lệch tokenizer estimate

### 6.2 `truncate_list_by_token_size()` chỉ là heuristic

Helper truncate đang dùng:

- [truncate_list_by_token_size()](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/utils/helpers.py:88)
- [encode_string_by_tiktoken()](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/utils/helpers.py:63)

Nó không phải server-side exact guard.

Vì vậy ngay cả sau khi fix bug index, vẫn nên set budget build thấp hơn `65536` khá rõ, thay vì pack sát trần.

---

## 7. Trả Lời Trực Tiếp: Lỗi `v3` Là Do Code Hay Do Cấu Hình?

### Kết luận chính xác

Lỗi `v3` là do **cả hai**, nhưng mức độ ảnh hưởng không ngang nhau:

1. **Code bug** trong temporal community packing là nguyên nhân gốc mạnh nhất
2. **Cấu hình budget/context** sát trần slot làm lỗi càng dễ bộc lộ

Nếu chỉ giảm `parallel`:

- `fresh-v2`: từ slot `32768` lên `65536` là có cải thiện
- nhưng `v3` vẫn fail vì prompt temporal community đang bị pack sai logic

Do đó:

- `p2` là hướng đúng
- nhưng `p2` **không thể tự chữa** bug code trong `_pack_single_timestamp_describe()`

---

## 8. Vì Sao Lần Chạy `v3` Không Có File Log Build Text?

### 8.1 `build_graph.py` không tự tạo file log

`build_graph.py` hiện chỉ:

- cấu hình `logging.basicConfig(...)`
- `print(...)` ra stdout

Nguồn:

- [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:77)
- [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:521)

Nó **không có**:

- `logging.FileHandler(...)`
- tự ghi `logs/build_graph/<run>.log`

### 8.2 Cái đang có là usage log, không phải build text log

Code hiện hỗ trợ usage JSONL qua env `TG_RAG_USAGE_LOG`:

- [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:292)
- [_append_usage_log()](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/completion.py:58)

Nghĩa là:

- bạn có [results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3.jsonl](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v3.jsonl:1)
- nhưng không có `logs/build_graph/...v3.log`

### 8.3 Suy ra gì

Run `v3` gần như chắc chắn đã được chạy theo kiểu:

- stdout chỉ hiện trong tmux/session terminal
- không `tee` hoặc redirect ra `logs/build_graph/...log`

Vì vậy sau khi session kết thúc:

- output build còn trên disk
- usage JSONL còn trên disk
- nhưng build text log thì mất

---

## 9. Kết Luận Thực Dụng

`v3` chứng minh 3 điều:

1. giảm `parallel 4 -> 2` là đúng hướng
2. nhưng vẫn chưa đủ để temporal community sạch
3. bug code ở temporal report packing đang là blocker thật

Nếu tiếp tục chỉ tune config mà không sửa code:

- bạn có thể giảm số case fail
- nhưng vẫn sẽ gặp overflow ở các year/quarter lớn

---

## 10. Hướng Fix Đúng

Theo thứ tự:

1. sửa bug temporal pack trong [tgrag/src/core/building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1478)
   - truncate temporal edges theo `description`, không phải `target`
   - sửa mapping temporal edge trong nhánh sub-community fallback
2. giảm `best_model_max_token_size` xuống dưới slot `65536`
3. thêm build manifest để query/demo biết build-time runtime
4. thêm file logging chuẩn cho `build_graph.py` hoặc luôn chạy qua shell `tee`

---

## 11. Trạng Thái Hiện Tại

Ở thời điểm viết file này:

- output `v3` tồn tại và query được
- community artifact của `v3` **không sạch**
- query branch đã được vá riêng ở local query/runtime/demo
- bước tiếp theo hợp lý là dùng chính output `v3` để test query path đã vá, rồi mới quay lại patch build/community
