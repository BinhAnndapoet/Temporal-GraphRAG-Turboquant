# Cấu Hình Khuyến Nghị Theo GPU / Args / ECT-QA

File này gom lại các profile cấu hình thực dụng để chạy `Temporal-GraphRAG-Turboquant` với dataset ECT-QA.

Mục tiêu:

- chọn nhanh profile theo máy
- biết khi nào dùng `p1`, `p2`, `p4`
- biết khi nào dùng `huggingface` embedding
- biết bộ câu hỏi nào nên dùng để test trước

---

## 1. Dataset ECT-QA cần nhớ gì

Repo hiện có:

- corpus base: `ect-qa/corpus/base.jsonl.gz`
- corpus new: `ect-qa/corpus/new.jsonl.gz`
- local questions base: `ect-qa/questions/local_base.jsonl`
- local questions new: `ect-qa/questions/local_new.jsonl`
- global questions base: `ect-qa/questions/global_base.jsonl`
- global questions new: `ect-qa/questions/global_new.jsonl`

Ý nghĩa thực dụng:

- `base` = tập chính để build và test local/global
- `new` = tập update/incremental
- `local_*` = fact QA / temporal QA chi tiết
- `global_*` = summary / abstract QA

Khuyến nghị khi debug:

1. build `base` trước
2. test `local_base` hoặc `local_new` trước
3. chỉ test `global_*` sau khi community artifact sạch

---

## 2. Rule quan trọng nhất: slot context mới là context thật

Với `llama-server`:

```text
slot_context ~= -c / --parallel
```

Ví dụ:

- `-c 131072 --parallel 4` -> khoảng `32768` / slot
- `-c 131072 --parallel 2` -> khoảng `65536` / slot
- `-c 32768 --parallel 2` -> khoảng `16384` / slot

Với build Temporal GraphRAG, đây là thứ quyết định:

- community report có overflow hay không
- extraction có bị truncate hay không
- output có bị cụt hay không

---

## 3. Rule thứ hai: `--llm_max_async` phải khớp `--parallel`

Khuyến nghị:

```text
llama-server --parallel N
build_graph.py --llm_max_async N
```

Nếu query chỉ chạy 1 câu/lần:

```text
query_graph.py --llm_max_async 1
run_batch_queries.py --llm_max_async 1
```

---

## 4. Rule thứ ba: với graph build bằng HF embedding, query cũng nên giữ HF embedding

Nếu build dùng:

```text
--embedding_provider huggingface
--embedding_model nomic-ai/nomic-embed-text-v1.5
```

thì query nên giữ như vậy nếu bạn muốn so sánh sạch generator:

- local TurboQuant
- Gemini

Không nên:

```text
build bằng HF
nhưng query lại để embedding mặc định sang Ollama
```

---

## 5. Profile theo GPU

## 5.1 Máy 16GB VRAM, Qwen2.5 7B Q8 local TurboQuant

Đây là case gần nhất với máy bạn.

### Profile build an toàn

```text
model: Qwen2.5 7B Q8
-c 131072
--parallel 2
--n-predict 3072
embedding: huggingface / nomic-ai/nomic-embed-text-v1.5
```

Dùng khi:

- build 384 docs
- ưu tiên sạch community hơn throughput

### Profile query an toàn

```text
query_graph.py / run_batch_queries.py
--llm_max_async 1
embedding giữ HuggingFace nếu graph build bằng HF
```

### Khi nào mới dùng `p4`

Chỉ dùng `p4` nếu:

- bạn đã có bằng chứng profile đó không overflow community
- hoặc bạn chỉ smoke test nhanh query

Nếu build full ECT-QA base 384 docs:

```text
ưu tiên p2 trước p4
```

## 5.2 Máy 16GB VRAM, Qwen3 14B Q5 local TurboQuant

Khuyến nghị:

```text
-c 32768
--parallel 2
--n-predict 4096
embedding: HF hoặc model embedding riêng nhẹ hơn
```

Dùng khi:

- muốn generator local mạnh hơn 7B
- chấp nhận build chậm hơn

Không nên nhảy thẳng lên:

```text
14B + parallel cao + context lớn
```

trừ khi bạn đã có smoke log sạch.

## 5.3 Nếu VRAM dư hoặc máy mạnh hơn

Ưu tiên tăng theo thứ tự:

1. tăng `-c`
2. giữ `--parallel` vừa phải
3. chỉ tăng `--n-predict` khi thực sự thấy output bị cắt

Không ưu tiên tăng `--parallel` trước.

---

## 6. Profile theo mục tiêu

## 6.1 Mục tiêu: build sạch để test local query

Khuyến nghị:

```text
7B Q8
p2
HF Nomic
384 docs
```

Mẫu:

```text
server: -c 131072 --parallel 2 --n-predict 3072
build : --llm_max_async 2
query : --llm_max_async 1
```

## 6.2 Mục tiêu: so local TurboQuant vs Gemini trên cùng graph

Khuyến nghị:

- build một lần
- giữ nguyên `working_dir`
- giữ nguyên embedding query
- chỉ đổi generator

Đây là benchmark sạch nhất cho query.

## 6.3 Mục tiêu: test demo

Khuyến nghị:

```text
demo chỉ dùng smoke test
không dùng benchmark nghiêm túc nếu graph build bằng HF embedding
```

---

## 7. Profile theo kích thước test

## 7.1 Smoke test nhỏ

Dùng để kiểm:

- server sống
- build chạy
- retrieval path không gãy

Khuyến nghị:

```text
1 docs
5 docs
10 docs
```

## 7.2 Mid-scale test

Dùng để kiểm:

- extraction
- community
- thời gian chạy

Khuyến nghị:

```text
50 docs
100 docs
```

## 7.3 Full-scale test

Dùng để kiểm chính thức:

```text
384 docs base corpus
```

Chỉ nên chạy khi:

- server profile đã ổn ở 50/100 docs
- query path đã được fix

---

## 8. Cấu hình embedding khuyến nghị cho ECT-QA

## 8.1 Khi nào dùng HuggingFace Nomic

Ưu tiên:

```text
--embedding_provider huggingface
--embedding_model nomic-ai/nomic-embed-text-v1.5
--embedding_dim 768
--embedding_batch_size 16
--embedding_max_tokens 7500
```

Lý do thực dụng:

- repo hiện kiểm soát `embedding_max_tokens` rõ ở nhánh HF
- prefix `search_document:` / `search_query:` kiểm soát được rõ
- phù hợp để benchmark retrieval tái lập

## 8.2 Khi nào dùng Ollama embedding

Dùng khi:

- bạn chỉ smoke test local stack thật nhanh
- chấp nhận ít khả năng kiểm soát hơn ở app layer

Không nên dùng làm baseline so sánh sạch với graph đã build bằng HF.

---

## 9. Chunk / token budget khuyến nghị cho ECT-QA

Với ECT-QA transcript:

- không nên tăng `chunk_size` quá sớm
- `chunk_size=1200`, `chunk_overlap=100` hiện là điểm khởi đầu hợp lý

Ở query side:

- `local_max_token_for_text_unit=4000` hiện hơi chật
- nếu query path đã fix context builder, nên test thêm:
  - `6000`
  - `8000`

Nhưng trước hết phải fix logic query trước đã.

---

## 10. Bảng chọn nhanh

| Mục tiêu | Khuyến nghị |
|---|---|
| Build 384 docs an toàn trên máy 16GB | `7B Q8`, `-c 131072`, `--parallel 2`, HF Nomic |
| Query local thực tế | giữ `working_dir`, `--llm_max_async 1`, giữ HF embedding nếu graph build bằng HF |
| So TurboQuant với Gemini | cùng `working_dir`, cùng embedding query, chỉ đổi generator |
| Test demo | chỉ smoke test UI/runtime |
| Test global metric cuối | chỉ làm sau khi build sạch community |

---

## 11. Checklist trước khi chạy

- [ ] Alias model query khớp `llama-server --alias`
- [ ] `--llm_max_async` khớp `--parallel` ở build
- [ ] Query batch dùng `--llm_max_async 1`
- [ ] Nếu build bằng HF thì query cũng truyền lại HF embedding
- [ ] `working_dir` trỏ đúng `outputs/build_graph/BUILD_*`
- [ ] Với `global` benchmark, xác nhận community artifact không có `Error Report for Unknown`
