# Inference Config Cho Local LLM + TurboQuant + Temporal-GraphRAG

File này giải thích cách chọn cấu hình inference khi build graph ECT-QA bằng:

- `llama-server` TurboQuant cho LLM extraction và community report.
- HuggingFace/Ollama embedding cho vector upsert.
- `build_graph.py` trong repo `Temporal-GraphRAG-Turboquant`.

Mục tiêu là hiểu rõ vì sao một cấu hình nhanh hoặc chậm, vì sao có lỗi context, và nên chọn profile nào cho full `384 docs`.

---

## 1. Kết Luận Cấu Hình Khuyến Nghị

### 1.1 7B full 384 docs, ưu tiên pass ổn định

Đây là profile nên dùng trước.

```text
llama-server:
model:        Qwen2.5 7B Q8 GGUF
-c:           65536
--parallel:   2
--n-predict:  3072
KV:           -ctk q8_0 -ctv turbo3

build_graph.py:
--llm_max_async:        2
--chunk_size:           1200
--chunk_overlap:        100
--embedding_provider:   huggingface
--embedding_model:      nomic-ai/nomic-embed-text-v1.5
--embedding_device:     cuda hoặc cpu
--embedding_batch_size: 8 nếu cuda, 16 nếu cpu
--embedding_max_async:  1
```

Lý do:

- `p2/c64k` cho mỗi slot khoảng `32K context`, tốt hơn `p4/c64k` chỉ khoảng `16K`.
- `p2` vẫn nhanh hơn `p1` ở chunk extraction vì chạy được 2 request song song.
- `chunk_size=1200` đủ nhỏ để prompt extraction không quá dài.
- HF embedding tránh lỗi context thấp của Ollama embedding.

### 1.2 7B fallback nếu community report lỗi context

Chỉ dùng khi `p2` có lỗi community context.

```text
llama-server:
-c:           65536
--parallel:   1
--n-predict:  3072

build_graph.py:
--llm_max_async: 1
```

Lý do:

- `p1/c64k` cho một slot gần `64K context`.
- Chậm hơn `p2`, nhưng ít lỗi context hơn cho community prompt dài.

### 1.3 14B Q5, ưu tiên ổn định trên 16GB VRAM

```text
llama-server:
model:        Qwen3 14B Q5 GGUF
-c:           32768
--parallel:   2 để test 1/5/10, hoặc 1 nếu community lỗi
--n-predict:  4096

build_graph.py:
--llm_max_async: 2 nếu server p2
--llm_max_async: 1 nếu server p1
--embedding_device: cpu trước, cuda chỉ khi còn dư VRAM rõ
```

Lý do:

- 14B Q8 đã có rủi ro OOM trên 16GB VRAM.
- 14B Q5 ổn hơn, nhưng context `c32k/p2` chỉ còn khoảng `16K/slot`.
- Nếu community prompt dài, `p1/c32k` ổn định hơn `p2/c32k`.

---

## 2. `--parallel` Của llama-server Là Gì

`--parallel` là số slot request mà `llama-server` có thể xử lý song song. Nó không phải tăng tốc miễn phí, vì context tổng `-c` bị chia cho các slot.

Ví dụ với 7B:

| Server config | Context tổng | Số slot | Context mỗi slot | Tốc độ | Rủi ro context |
|---|---:|---:|---:|---|---|
| `-c 65536 --parallel 1` | 65536 | 1 | khoảng 65536 | chậm hơn | thấp |
| `-c 65536 --parallel 2` | 65536 | 2 | khoảng 32768 | cân bằng | vừa |
| `-c 65536 --parallel 4` | 65536 | 4 | khoảng 16384 | có thể nhanh extraction | cao |

Với Temporal-GraphRAG, rủi ro lớn nhất không chỉ ở extraction mà còn ở community report. Community prompt thường dài hơn chunk prompt rất nhiều, nên cần slot context lớn.

---

## 3. `--llm_max_async` Trong build_graph.py Là Gì

`--llm_max_async` là số request LLM mà client `build_graph.py` được phép gửi song song.

Nên khớp với `llama-server --parallel`:

| llama-server | build_graph.py | Ý nghĩa |
|---|---|---|
| `--parallel 1` | `--llm_max_async 1` | ổn định, ít lỗi context, chậm hơn |
| `--parallel 2` | `--llm_max_async 2` | cân bằng, khuyến nghị cho 7B full 384 docs |
| `--parallel 4` | `--llm_max_async 4` | chỉ nên benchmark sau khi p2 đã pass sạch |

Không nên để:

```text
server --parallel 2
build  --llm_max_async 4
```

Vì client gửi nhiều hơn số slot server có thể xử lý. Kết quả thường là queue dài, timeout, hoặc không nhanh hơn.

---

## 4. Vì Sao p4 Có Thể Nhanh Nhưng Dễ Lỗi

`p4` có thể nhanh ở giai đoạn chunk extraction vì nhiều chunk prompt được xử lý song song hơn.

Nhưng với `-c 65536 --parallel 4`, mỗi request chỉ còn khoảng `16K context`. Khi đến community report, prompt có thể chứa:

- nhiều entity đã merge
- nhiều relation đã merge
- mô tả entity/relation dài
- temporal hierarchy
- yêu cầu viết report

Nếu prompt vượt slot context, log có thể có:

```text
request (...) exceeds the available context size
Failed to generate community report
Error Report
```

Trong các TH cũ, `p4/c64k` đã cho thấy rủi ro community context. Vì vậy không nên dùng `p4` cho run 384 đầu tiên.

---

## 5. Chunk Size Và Chunk Overlap

Hiện profile đang dùng:

```text
--chunk_size 1200
--chunk_overlap 100
```

### 5.1 Nếu tăng chunk size

Ví dụ:

```text
--chunk_size 2000
--chunk_overlap 200
```

Tác động:

- Số chunk ít hơn.
- Số request LLM extraction ít hơn.
- Có thể nhanh hơn về số request.
- Nhưng mỗi prompt dài hơn.
- Dễ vượt context hơn.
- LLM có thể extract thiếu hoặc output khó parse hơn.
- Description entity/relation có thể phình mạnh hơn sau merge.

### 5.2 Nếu giảm chunk size

Ví dụ:

```text
--chunk_size 800
--chunk_overlap 100
```

Tác động:

- Số chunk nhiều hơn.
- Nhiều request LLM hơn, chậm hơn.
- Mỗi prompt ngắn hơn, ít lỗi context hơn.
- Có thể ổn định hơn nếu model local hay output lỗi.

### 5.3 Khuyến nghị hiện tại

Giữ:

```text
--chunk_size 1200
--chunk_overlap 100
```

cho đến khi full 384 pass sạch. Chỉ tune chunk size sau khi đã có baseline ổn định.

---

## 6. Community Report Là Giai Đoạn Gì

Build graph không chỉ extract entity/relation. Sau khi có graph, source còn tạo community report:

```text
graph entities/relations
-> detect/community grouping
-> pack nodes/edges/descriptions into prompt
-> LLM generate report
-> kv_store_community_reports.json
```

Đây là nơi dễ gặp lỗi context vì prompt không còn là một chunk đơn lẻ, mà là một cụm graph lớn.

Một run có thể in:

```text
Graph building completed successfully
```

nhưng vẫn có community bị lỗi nếu source ghi `Error Report` vào `kv_store_community_reports.json`. Vì vậy phải kiểm community report, không chỉ nhìn dòng pass.

---

## 7. `--n-predict` Ảnh Hưởng Gì

`--n-predict` giới hạn số token output tối đa mỗi request.

| Giá trị | Khi dùng | Trade-off |
|---:|---|---|
| `2048` | muốn nhanh hơn, output ngắn hơn | có thể thiếu report/extraction dài |
| `3072` | 7B full 384 hiện tại | cân bằng tốc độ và độ dài output |
| `4096` | 14B hoặc report dài | chậm hơn, dùng thêm context/output budget |

Khuyến nghị:

```text
7B:  --n-predict 3072
14B: --n-predict 4096
```

Nếu community report quá dài hoặc decode quá lâu, có thể giảm `--n-predict`, nhưng cần kiểm chất lượng report.

---

## 8. Embedding CPU Và GPU

Embedding chỉ ảnh hưởng giai đoạn vector upsert, không thay đổi LLM extraction.

Lưu ý quan trọng: `embedding_max_async` là số batch embedding chạy song song, **không phải** số request LLM. Tăng nó chỉ có ích khi embedding đang là nút thắt cổ chai và máy còn tài nguyên rảnh.

### 8.1 CPU embedding

```text
--embedding_device cpu
--embedding_batch_size 16
--embedding_max_async 1
```

Ưu điểm:

- Không tranh VRAM với `llama-server`.
- Ổn định hơn cho 14B.
- Ít rủi ro OOM.
- Thường là lựa chọn an toàn nhất khi GPU đang phải phục vụ cả extraction/community report.

Nhược điểm:

- Embedding compute chậm hơn.
- Có thể làm `entity_vdb.upsert` và `relation_vdb.upsert` lâu hơn.
- Nếu chỉ nhìn riêng tốc độ embedding thì CPU thường chậm hơn GPU, nhưng tổng thể pipeline lại ổn hơn khi GPU đã bận.

### 8.2 GPU embedding

```text
--embedding_device cuda
--embedding_batch_size 8
--embedding_max_async 1
```

Ưu điểm:

- Embedding nhanh hơn CPU.
- Có lợi khi entity/relation nhiều.
- Chỉ đáng cân nhắc khi `llama-server` chưa ăn hết VRAM hoặc bạn benchmark thấy còn headroom rõ ràng.

Nhược điểm:

- Tranh VRAM với `llama-server`.
- Có rủi ro OOM hoặc làm GPU queue nặng hơn.
- Nếu GPU đã gần đầy vì LLM server, embedding trên GPU có thể làm cả pipeline chậm hơn hoặc bất ổn hơn do tranh tài nguyên.

Với trạng thái đã kiểm:

```text
RTX 5070 Ti 16GB
llama-server 7B đang dùng khoảng 9GB VRAM
còn khoảng 6.4GB VRAM
GPU util gần 97%
```

Khuyến nghị mặc định cho workflow này:

```text
--embedding_device cpu
--embedding_batch_size 8
--embedding_max_async 1
```

### 8.3 Nên để `embedding_max_async` bao nhiêu?

Khuyến nghị thực tế:

```text
GPU LLM server đang chạy: embedding_max_async = 1
CPU embedding:            embedding_max_async = 1 hoặc 2 nếu RAM/CPU còn dư
GPU embedding rảnh VRAM:   có thể thử 2, nhưng chỉ sau khi benchmark
```

Vì sao?

- `embedding_max_async = 1` giúp tránh nhiều batch embedding tranh tài nguyên với request LLM.
- Tăng lên `2` chỉ có ích khi embedding là nút thắt cổ chai rõ ràng; nếu không, nó chỉ tạo thêm queue và overhead.
- Với workflow của bạn, ưu tiên là pipeline ổn định trước, tối ưu sau.

Nếu bạn muốn giữ cấu hình cũ để chạy lại, nên giữ `embedding_device cpu` và `embedding_max_async 1` trước; sau đó mới test GPU embedding riêng biệt ở một run mới.

---

## 9. Cách Xác Định Nên Đổi Config Hay Không

### 9.1 Check server log

```bash
grep -E "n_ctx|n_ctx_slot|truncated|exceeds|error" logs/llama_server/*.log
```

Nếu thấy:

```text
n_ctx_slot = 32768
truncated = 0
```

là tốt.

Nếu thấy:

```text
exceeds the available context size
```

thì context slot thiếu. Giảm parallel:

```text
p2 -> p1
```

### 9.2 Check build log extraction

```bash
grep -E "new chunks|Processed .*chunks|chunk LLM extraction" logs/build_graph/*.log
```

Nếu extraction đạt `100% chunks` nhưng sau đó fail embedding, vấn đề không nằm ở `parallel`.

### 9.3 Check embedding

```bash
grep -E "embedding content lengths|Truncate embedding|Ollama embedding API error|entity_vdb|relation_vdb" logs/build_graph/*.log
```

Nếu dùng HF mà vẫn truncate rất nhiều, cần xem lại merge description hoặc giảm content trước embedding.

### 9.4 Check community

```bash
grep -E "Failed to generate community report|Error Report|Graph building completed" logs/build_graph/*.log
```

Nếu có community error:

- Không tăng `parallel`.
- Đổi về `p1`.
- Hoặc cần cơ chế rebuild community-only sau này.

---

## 10. Cây Quyết Định Nhanh

### Muốn chạy 384 lần đầu bằng 7B

```text
Dùng p2/c64k:
server --parallel 2
build  --llm_max_async 2
chunk  1200/100
embed  cuda batch 8 async 1
```

### Nếu lỗi community context

```text
Đổi p1/c64k:
server --parallel 1
build  --llm_max_async 1
```

### Nếu lỗi CUDA OOM ở embedding

```text
Giữ server p2
đổi embedding:
--embedding_batch_size 4
```

Nếu vẫn OOM:

```text
--embedding_device cpu
--embedding_batch_size 16
```

### Nếu extraction quá chậm nhưng không lỗi

Không tăng ngay lên `p4` cho 384. Trước tiên cần một baseline pass bằng `p2`. Sau đó mới benchmark:

```text
p4/c64k + llm_max_async 4
```

và phải kiểm community error thật kỹ.

---

## 11. Profile Nên Ghi Vào Tên Run

Tên run nên chứa đủ thông tin inference:

```text
cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_cuda_b8_384docs
```

Ý nghĩa:

| Thành phần | Nghĩa |
|---|---|
| `tq` | repo TurboQuant |
| `turbo` | LLM chạy qua llama-server TurboQuant |
| `7b` | model 7B |
| `p2c64k` | `--parallel 2`, context tổng 64K |
| `np3072` | `--n-predict 3072` |
| `hf_nomic` | HuggingFace Nomic embedding |
| `cuda_b8` | embedding GPU, batch size 8 |
| `384docs` | full dataset |

Dùng cùng `RUN_NAME` cho:

```text
outputs/build_graph/${RUN_NAME}
logs/build_graph/${RUN_NAME}.log
results/usage/${RUN_NAME}.jsonl
```

Như vậy khi đối chiếu output/log/usage sẽ không bị nhầm.

---

## 12. Lệnh Profile 7B Khuyến Nghị Hiện Tại

Server:

```text
-c 65536
--parallel 2
--n-predict 3072
-ctk q8_0
-ctv turbo3
```

Build:

```text
--llm_max_async 2
--chunk_size 1200
--chunk_overlap 100
--embedding_provider huggingface
--embedding_model nomic-ai/nomic-embed-text-v1.5
--embedding_device cuda
--embedding_batch_size 8
--embedding_batch_num 16
--embedding_max_async 1
--embedding_max_chars 24000
--num_docs 384
```

Đây là cấu hình cân bằng nhất hiện tại để kiểm tra full 384 docs với embedding mới.
