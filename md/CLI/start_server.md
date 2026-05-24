# CLI Start llama-server Cho Local LLM + TurboQuant

Tài liệu này hướng dẫn start `llama-server` từ repo:

```text
/home/guest/Projects/Research/llama-cpp-turboquant
```

Server này chỉ phục vụ **LLM extraction/community report** qua OpenAI-compatible API:

```text
http://localhost:8080/v1
```

Embedding có thể chạy riêng qua Ollama hoặc HuggingFace trong `build_graph.py`; không cần start bằng `llama-server` nếu dùng HuggingFace embedding.

---

## 1. Chọn Profile Nào?

Với GPU RTX 5070 Ti 16GB, ưu tiên như sau:

| Mục tiêu | Model | File GGUF | Profile nên dùng | Lý do |
|---|---|---|---|---|
| Test nhanh, local TurboQuant 7B | Qwen2.5 7B Q8 | `qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf` | `p2/c64k/np3072` | 7B nhẹ hơn, context slot khoảng 32K khi `--parallel 2`, phù hợp test 1/5/10/50 docs |
| Chất lượng local cao hơn | Qwen3 14B Q5 | `Qwen3-14B-Q5_0.gguf` | `p2/c32k/np4096` | 14B Q5 vừa hơn 14B Q8 trên 16GB VRAM; đã tránh OOM Q8 |
| Khi community report lỗi context | 7B hoặc 14B | giữ model hiện tại | `p1` | `--parallel` càng cao thì context bị chia slot; p1 cho slot lớn hơn |
| Không nên dùng trên 16GB | Qwen3 14B Q8 | `Qwen3-14B-Q8_0.gguf` | không khuyến nghị | Log cũ có `cudaMalloc failed` / KV cache OOM |

Quy tắc đồng bộ:

```text
llama-server --parallel N
build_graph.py --llm_max_async N
```

Nếu server alias là `qwen25-...-p2...` thì `build_graph.py --model` phải dùng đúng alias đó.

---

## 2. Quick Start 7B: Qwen2.5 7B Q8, p2/c64k/np3072

Dùng profile này để test local LLM + TurboQuant ổn định trước. Đây là profile khuyến nghị cho 7B sau khi TH1 cũ p4 gây lỗi context community.

Tạo tmux:

```bash
tmux new -s srv_tq_turbo_7b_p2c64k_hf_nomic
```

Trong tmux:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 65536 \
  --parallel 2 \
  --n-predict 3072 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_7b_p2c64k_hf_nomic_$(date +%Y%m%d_%H%M%S).log
```

Giải thích nhanh ngay tại lệnh:

- `-m ...qwen2.5-7b...gguf`: chọn model 7B Q8 để test nhanh local LLM trên GPU 16GB.
- `--alias qwen25-7b-...-p2-np3072`: tên model mà `build_graph.py --model` phải dùng đúng y hệt.
- `-ctk q8_0 -ctv turbo3`: bật profile KV TurboQuant đã dùng trong các TH local.
- `-c 65536 --parallel 2`: tổng context 64K, chia 2 slot, mỗi slot khoảng 32K; cân bằng giữa throughput và context.
- `--n-predict 3072`: giới hạn output mỗi request để giảm thời gian decode và tránh output quá dài.
- `--log-file ...`: bắt buộc giữ lại để đối chiếu `n_ctx_slot`, `truncated`, tốc độ decode và lỗi context.


Kỳ vọng trong server log:

```text
n_ctx = 65536
n_ctx_slot ~= 32768
truncated = 0
POST /v1/chat/completions ... 200
```

---

## 3. Quick Start 14B: Qwen3 14B Q5, p2/c32k/np4096

Dùng profile này khi muốn test chất lượng local cao hơn 7B. Không dùng Q8 trên 16GB VRAM nếu chưa có bằng chứng đủ VRAM.

Tạo tmux:

```bash
tmux new -s srv_tq_turbo_14bq5_p2c32k_hf_nomic
```

Trong tmux:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server

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
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_14bq5_p2c32k_hf_nomic_$(date +%Y%m%d_%H%M%S).log
```

Giải thích nhanh ngay tại lệnh:

- `-m ...Qwen3-14B-Q5_0.gguf`: dùng 14B Q5 vì Q8 đã có rủi ro OOM trên 16GB VRAM.
- `--alias qwen3-14b-q5-...-p2-np4096`: tên này phải khớp với `build_graph.py --model` khi build graph.
- `-c 32768 --parallel 2`: tổng context 32K, chia 2 slot, mỗi slot khoảng 16K; phù hợp test 1/5/10 trước, nhưng có thể thiếu cho community prompt lớn.
- `--n-predict 4096`: cho 14B thêm khoảng output dài hơn khi extraction/community cần mô tả nhiều.
- `-ctk q8_0 -ctv turbo3 -fa on -ngl 99`: giữ profile TurboQuant + GPU offload như các TH local đã test.
- Nếu log báo context vượt slot, giữ model Q5 nhưng đổi sang profile `p1` ở mục 4.


Kỳ vọng:

```text
model load OK
POST /v1/chat/completions ... 200
truncated = 0
```

Lưu ý quan trọng:

- Với `-c 32768 --parallel 2`, mỗi slot chỉ khoảng 16K context.
- Nếu community report lỗi `request (...) exceeds the available context size`, đổi sang profile p1 ở mục dưới.

---

## 4. Fallback p1 Khi Community Prompt Vượt Context

Lỗi community cũ đã gặp:

```text
request (...) exceeds the available context size
```

Nguyên nhân thường không phải model hỏng, mà do:

```text
context tổng -c bị chia theo --parallel
```

### 4.1 7B p1/c64k

Tạo tmux:

```bash
tmux new -s srv_tq_turbo_7b_p1c64k_hf_nomic
```

Lệnh:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p1-np3072 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 65536 \
  --parallel 1 \
  --n-predict 3072 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_7b_p1c64k_hf_nomic_$(date +%Y%m%d_%H%M%S).log
```

Giải thích nhanh ngay tại lệnh:

- Khác profile 7B p2 ở chỗ `--parallel 1`.
- `-c 65536 --parallel 1` cho một slot gần đủ 64K context, giảm nguy cơ community prompt vượt context.
- Đổi `--alias` sang `...p1...` để tránh nhầm với server p2 trong build log/cache.
- Khi dùng server này, build graph phải đổi `--llm_max_async 1` để không gửi song song quá khả năng slot.


Build graph phải đổi theo:

```text
--model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p1-np3072
--llm_max_async 1
```

### 4.2 14B Q5 p1/c32k

Tạo tmux:

```bash
tmux new -s srv_tq_turbo_14bq5_p1c32k_hf_nomic
```

Lệnh:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/Qwen3-14B-Q5_0.gguf \
  --alias qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p1-np4096 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 1 \
  --n-predict 4096 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_14bq5_p1c32k_hf_nomic_$(date +%Y%m%d_%H%M%S).log
```

Giải thích nhanh ngay tại lệnh:

- Khác profile 14B p2 ở chỗ `--parallel 1` để không chia nhỏ context slot.
- `-c 32768 --parallel 1` cho slot khoảng 32K, ổn định hơn p2/c32k cho community report.
- `--alias ...p1...` phải được dùng lại trong `build_graph.py --model`.
- Đổi build graph sang `--llm_max_async 1`; nếu không, client vẫn có thể đẩy nhiều request hơn slot server.


Build graph phải đổi theo:

```text
--model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p1-np4096
--llm_max_async 1
```

---

## 5. Bảng Giải Thích Arg llama-server

| Arg | Ví dụ | Ý nghĩa | Khi nào chỉnh |
|---|---|---|---|
| `-m` | `models/Qwen3-14B-Q5_0.gguf` | File model GGUF | Đổi 7B/14B/Q5/Q8 |
| `--alias` | `qwen3-14b-q5-...` | Tên model mà `build_graph.py --model` gọi tới | Phải khớp tuyệt đối với lệnh build |
| `--host` | `127.0.0.1` | Chỉ bind local máy | Giữ mặc định local |
| `--port` | `8080` | Port OpenAI-compatible server | Đổi nếu port bận |
| `-ctk q8_0` | `q8_0` | Kiểu KV key cache | Giữ để dùng TurboQuant theo profile đã test |
| `-ctv turbo3` | `turbo3` | Kiểu KV value cache TurboQuant | Đây là phần TurboQuant chính |
| `-fa on` | `on` | Flash attention | Nên bật nếu build hỗ trợ |
| `-ngl 99` | `99` | Offload layers lên GPU | Với 1 GPU, giữ 99 để dùng GPU tối đa |
| `-c` | `65536` hoặc `32768` | Context tổng của server | 7B dùng 64K; 14B Q5 dùng 32K cho an toàn VRAM |
| `--parallel` | `2` | Số slot request song song | Tăng throughput nhưng chia context; nếu community lỗi context thì giảm |
| `--n-predict` | `3072` hoặc `4096` | Giới hạn output tokens mỗi request | Giảm để tiết kiệm thời gian/context nếu output không cần dài |
| `--log-file` | `logs/llama_server/...log` | Ghi server log | Luôn dùng để kiểm `truncated`, `n_ctx_slot`, lỗi |

---

## 6. Kiểm Tra Server Đã Sẵn Sàng

Trong terminal khác:

```bash
curl http://127.0.0.1:8080/props | head
```

Kiểm tra model alias:

```bash
curl http://127.0.0.1:8080/v1/models
```

Kiểm server log:

```bash
grep -E "n_ctx|n_ctx_slot|truncated|POST /v1/chat/completions|exceeds|error" \
  /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_*hf_nomic*.log
```

Khi chạy tốt, cần thấy:

```text
POST /v1/chat/completions ... 200
truncated = 0
```

Nếu thấy:

```text
request (...) exceeds the available context size
```

thì giảm `--parallel`, hoặc giảm prompt/chunk/community payload.

---

## 7. Tmux Cơ Bản

Liệt kê session:

```bash
tmux ls
```

Attach session:

```bash
tmux attach -t srv_tq_turbo_7b_p2c64k_hf_nomic
```

Detach khỏi tmux:

```text
Ctrl-b rồi d
```

Stop server trong tmux:

```text
Ctrl-c
```

Kill session:

```bash
tmux kill-session -t srv_tq_turbo_7b_p2c64k_hf_nomic
```

Kiểm port 8080:

```bash
lsof -i :8080
```

---

## 8. Lưu Ý Khi Chạy Ollama 14B / Embedding

Không chạy song song các workload cùng tranh GPU nếu muốn benchmark sạch:

- `llama-server` 14B Q5 đang giữ GPU.
- Ollama `qwen3:14b` cũng muốn giữ GPU.
- HuggingFace embedding nếu dùng `--embedding_device cuda` cũng tranh VRAM.

Mặc định ổn định nhất:

```text
LLM: llama-server TurboQuant trên GPU
Embedding: HuggingFace trên CPU
```

Nếu muốn thử embedding CUDA:

```text
--embedding_device cuda
--embedding_max_async 1
--embedding_batch_size 8 hoặc 16
```

Chỉ thử sau khi CPU pass 1/5/10 docs và `nvidia-smi` còn dư VRAM rõ ràng.

---

## 9. Quyết Định Cấu Hình Cho 384 Docs

Trước khi chạy 384 docs:

1. 7B phải pass 50/100 docs không còn community error.
2. 14B Q5 phải pass 50/100 docs không còn embedding error.
3. Build log phải dùng `embedding_provider=huggingface`.
4. Server log phải có `truncated = 0`.
5. Output phải có đủ `full_docs`, `text_chunks`, `vdb_entities`, `vdb_relations`, `community_reports`, GraphML.

Không nên gọi một run là ổn định chỉ vì có `kv_store_llm_response_cache.json`; cache có thể tồn tại dù build chết giữa chừng.

