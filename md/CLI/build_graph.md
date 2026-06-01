# CLI Build Graph Cho Temporal-GraphRAG-Turboquant

Tài liệu này hướng dẫn chạy `build_graph.py` trong repo:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
```

Mục tiêu chính:

- Build graph ECT-QA bằng local LLM qua `llama-server` TurboQuant.
- Dùng HuggingFace embedding để tránh lỗi context của Ollama embedding.
- Có lệnh quick start cho 7B và 14B phù hợp GPU RTX 5070 Ti 16GB.
- Biết cách đọc log/output để kết luận run có thật sự pass hay không.

Đọc file này cùng với:

```text
md/CLI/start_server.md
md/debug/debug_localLLM_log_results.md
md/runbooks/resume_setup.md
```

---

## 1. Trạng Thái Ổn Định Hiện Tại

Kết luận hiện tại phải nói rõ:

```text
HF embedding đã pass smoke build 1/5/10 docs với 7B p2/c64k.
Chưa có bằng chứng HF embedding đã pass 50/100/384 docs.
Vì vậy chưa gọi là ổn định full 384, chỉ gọi là ổn định bước đầu.
```

Kết quả đã kiểm:

| Run | Backend LLM | Embedding | Docs | Chunks | Community error | Embedding error | Tổng thời gian |
|---|---|---|---:|---:|---:|---:|---:|
| `cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_001docs` | 7B TurboQuant | HF Nomic CPU | 1 | 5 | 0 | 0 | 131.58s |
| `cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_005docs` | 7B TurboQuant | HF Nomic CPU | 5 | 19 | 0 | 0 | 598.84s |
| `cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_010docs` | 7B TurboQuant | HF Nomic CPU | 10 | 39 | 0 | 0 | 1118.82s |

Các lỗi cũ cần tránh:

| Lỗi | Run kiểm chứng | Nguyên nhân | Hướng tránh |
|---|---|---|---|
| Community report vượt context | 7B p4 50 docs, 14B p2/c32k 50 docs | `--parallel` chia context thành slot nhỏ, prompt community dài | Dùng p2/c64k cho 7B; nếu còn lỗi thì p1 |

### One-command launcher cho 7B build

Nếu bạn muốn **một lệnh tạo 2 tmux session riêng** (`llm_srv` và `build_7b`) thì dùng:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
bash scripts/run_7b_build_stack.sh
```

Script này mặc định:

- server 7B Q8
- `--parallel 2`
- `-c 131072`
- HuggingFace embedding `nomic-ai/nomic-embed-text-v1.5`
- build output: `outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_fresh-v2`

Script cũng có chặn an toàn:

- nếu `--output-dir` đã tồn tại và không rỗng, nó sẽ dừng thay vì ghi đè
- nếu usage log cùng basename đã tồn tại, script sẽ cảnh báo để bạn đổi basename của output dir

Muốn đổi output dir (ví dụ `v2`):

```bash
bash scripts/run_7b_build_stack.sh \
  --output-dir outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v2
```

Lý do khuyến nghị `p2`:

- `p4` làm mỗi slot nhỏ hơn, prompt community level 0 dễ chạm trần hơn
- `p2` cho headroom tốt hơn để community report và JSON output ổn định hơn

### Manual workflow: 2 tmux session riêng, full CLI

Nếu bạn muốn nhìn rõ từng bước hơn, đây là cách chạy **thủ công** với **2 tmux session riêng**:

#### Bước 1: mở session server

```bash
tmux new -s llm_srv
```

Trong session đó, chạy server 7B:

```bash
conda activate turboquant
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
  --n-predict 3072
```

#### Bước 2: kiểm tra server đã sẵn sàng

```bash
curl -sS http://localhost:8080/v1/models
```

#### Bước 3: mở session build riêng

```bash
tmux new -s build_7b
```

Trong session build, chạy `build_graph.py` với output mới:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false
export TG_RAG_USAGE_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v2.jsonl

python -u build_graph.py \
  --output_dir outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v2 \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cpu \
  --embedding_batch_size 16 \
  --embedding_batch_num 16 \
  --embedding_max_async 1 \
  --embedding_prefix "search_document: " \
  --chunk_size 1200 \
  --chunk_overlap 100 \
  --num_docs 384 \
  --llm_max_async 2 \
  --llm_timeout 900 \
  --entity_extraction_timeout 43200
```

#### Ghi chú để không đụng run cũ

- `--output_dir` mới là thư mục graph output, không nên trỏ lại `fresh-v2` hoặc `v2` cũ nếu bạn muốn giữ nguyên run trước.
- `TG_RAG_USAGE_LOG` nên đổi theo basename của output dir để log không bị trộn.
- Nếu bạn muốn đổi `p`, `model`, hoặc `ctx`, hãy sửa trực tiếp các tham số `--parallel`, `--alias`, `-c`, `--n-predict` trong block server.

#### Tương ứng nhanh giữa tmux và CLI

| Session | Nhiệm vụ | CLI chính |
|---|---|---|
| `llm_srv` | chạy LLM server | `./build/bin/llama-server ...` |
| `build_7b` | chạy graph build | `python -u build_graph.py ...` |

---

## 2. Chuẩn Bị Môi Trường HuggingFace Embedding

Chạy một lần trong env `turboquant`.

```bash
tmux new -s setup_hf_embedding
```

Trong tmux:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

pip install sentence-transformers transformers huggingface_hub accelerate einops

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false
```

`einops` là cần thiết với `nomic-ai/nomic-embed-text-v1.5`; nếu thiếu sẽ gặp lỗi:


Giải thích nhanh ngay tại lệnh:

- `pip install ... einops`: cài stack HuggingFace embedding; `einops` bắt buộc cho Nomic HF model.
- `HF_HOME`: đặt cache model HF trong `/home/guest/Projects/Research/.cache` để không tải lại nhiều lần.
- `TRANSFORMERS_CACHE`: giữ cache transformers cùng vị trí, dễ kiểm soát dung lượng.
- `TOKENIZERS_PARALLELISM=false`: tránh warning và tránh tokenizer spawn quá nhiều thread khi build graph dài.

```text
ImportError: ... requires ... einops
```

### 1.1 Timeout 43200 cho entity extraction

Nếu bạn muốn giữ nguyên cấu hình cũ nhưng cho phép extraction chạy lâu hơn, chỉ cần tăng timeout stage này lên `43200` giây.

```bash
python -u build_graph.py \
  --output_dir outputs/build_graph/BUILD_qwen25_7b_p2c64k_np3072_hf_nomic_384docs_timeout43200 \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cpu \
  --embedding_batch_size 16 \
  --embedding_batch_num 16 \
  --embedding_max_async 1 \
  --embedding_prefix "search_document: " \
  --chunk_size 1200 \
  --chunk_overlap 100 \
  --num_docs 384 \
  --llm_max_async 2 \
  --llm_timeout 1200 \
  --entity_extraction_timeout 43200
```

Lưu ý quan trọng:

- Dùng đúng `--entity_extraction_timeout 43200`.
- Không viết `- entity_extraction_timeout 43200` vì dấu `-` tách rời sẽ bị coi là arg lỗi.
- Nếu bạn muốn giữ đúng cấu hình cũ, chỉ thay timeout này; còn server alias, `--parallel`, `--llm_max_async`, chunk size và embedding vẫn giữ nguyên.

Giải thích nhanh ngay tại lệnh:

- `--embedding_batch_size 16 --embedding_batch_num 16 --embedding_max_async 1`: giới hạn embedding concurrency để tránh nghẽn RAM/CPU hoặc tranh GPU.
- `--entity_extraction_timeout 43200`: cho phép phase extract chạy tối đa 12 giờ trước khi dừng.

Smoke test:

```bash
python - <<'PY'
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(
    "nomic-ai/nomic-embed-text-v1.5",
    trust_remote_code=True,
    device="cpu",
)
model.max_seq_length = 7500
vec = model.encode(
    ["search_document: test temporal graph embedding"],
    normalize_embeddings=True,
)
print(vec.shape)
PY
```

Kỳ vọng:

```text
(1, 768)
```

---

## 3. Quick Start 7B: Build 1/5/10 Docs

Trước khi chạy block này, start server 7B theo `md/CLI/start_server.md`:

```text
server alias: qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072
server URL:   http://localhost:8080/v1
```

Tạo tmux:

```bash
tmux new -s bld_tq_turbo_7b_p2c64k_hf_nomic_001_010docs
```

Trong tmux:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false

mkdir -p logs/build_graph outputs/build_graph results/usage

for D in 1 5 10; do
  L=$(printf "%03ddocs" "$D")
  export TG_RAG_USAGE_LOG=results/usage/cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_${L}.jsonl

  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_${L} \
    --model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider huggingface \
    --embedding_model nomic-ai/nomic-embed-text-v1.5 \
    --embedding_dim 768 \
    --embedding_max_tokens 7500 \
    --embedding_max_chars 24000 \
    --embedding_device cpu \
    --embedding_batch_size 16 \
    --embedding_batch_num 16 \
    --embedding_max_async 1 \
    --embedding_prefix "search_document: " \
    --chunk_size 1200 \
    --chunk_overlap 100 \
    --num_docs "$D" \
    --llm_max_async 2 \
    --llm_timeout 900 \
    2>&1 | tee logs/build_graph/cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_${L}.log
done
```


Giải thích nhanh ngay tại lệnh:

- `TG_RAG_USAGE_LOG=results/usage/...${L}.jsonl`: ghi usage/token/request timing cho đúng run name; tên này khớp với `logs/build_graph/...${L}.log` và `outputs/build_graph/...${L}`.
- `--output_dir outputs/build_graph/...${L}`: nơi ghi toàn bộ graph/vector/cache của run; không reuse output cũ khi đổi embedding/model/dim.
- `--model qwen25-...-p2-np3072`: phải khớp `--alias` của `llama-server` 7B đang chạy.
- `--base_url http://localhost:8080/v1`: gọi `llama-server` qua OpenAI-compatible API.
- `--local_llm_backend turboquant`: bật đường local LLM/TurboQuant, không dùng Gemini/Ollama LLM.
- `--embedding_provider huggingface`: dùng HF embedding thay Ollama embedding để tránh lỗi input length của Ollama.
- `--embedding_model nomic-ai/nomic-embed-text-v1.5 --embedding_dim 768`: cùng họ với `nomic-embed-text`, giữ vector dim 768.
- `--embedding_max_tokens 7500 --embedding_max_chars 24000`: chặn entity/relation description quá dài trước khi embed.
- `--embedding_device cpu`: ưu tiên GPU cho `llama-server`; sau khi ổn mới cân nhắc `cuda`.
- `--embedding_batch_size 16 --embedding_batch_num 16 --embedding_max_async 1`: giới hạn embedding concurrency để tránh nghẽn RAM/CPU hoặc tranh GPU.
- `--embedding_prefix "search_document: "`: prefix đúng kiểu Nomic cho document embedding.
- `--chunk_size 1200 --chunk_overlap 100`: chunk vừa phải cho ECT-QA, tránh prompt extraction quá dài.
- `--llm_max_async 2`: khớp server `--parallel 2`; nếu dùng server p1 thì đổi thành `1`.
- `--llm_timeout 900`: timeout dài hơn cho local decode chậm, nhất là community report.


Khi pass, build log phải có:

```text
[runtime] embedding_provider=huggingface
[runtime] embedding_model=nomic-ai/nomic-embed-text-v1.5
Graph building completed successfully
```

---

## 4. Quick Start 14B Q5: Build 1/5/10 Docs

Trước khi chạy block này, stop server 7B và start server 14B Q5 theo `md/CLI/start_server.md`:

```text
server alias: qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096
server URL:   http://localhost:8080/v1
```

Tạo tmux:

```bash
tmux new -s bld_tq_turbo_14bq5_p2c32k_hf_nomic_001_010docs
```

Trong tmux:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false

mkdir -p logs/build_graph outputs/build_graph results/usage

for D in 1 5 10; do
  L=$(printf "%03ddocs" "$D")
  export TG_RAG_USAGE_LOG=results/usage/cmp_tq_turbo_14bq5_p2c32knp4096_hf_nomic_${L}.jsonl

  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_hf_nomic_${L} \
    --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider huggingface \
    --embedding_model nomic-ai/nomic-embed-text-v1.5 \
    --embedding_dim 768 \
    --embedding_max_tokens 7500 \
    --embedding_max_chars 24000 \
    --embedding_device cpu \
    --embedding_batch_size 16 \
    --embedding_batch_num 16 \
    --embedding_max_async 1 \
    --embedding_prefix "search_document: " \
    --chunk_size 1200 \
    --chunk_overlap 100 \
    --num_docs "$D" \
    --llm_max_async 2 \
    --llm_timeout 1200 \
    2>&1 | tee logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_hf_nomic_${L}.log
done
```


Giải thích nhanh ngay tại lệnh:

- `--model qwen3-14b-q5-...-p2-np4096`: phải khớp alias server 14B Q5; không dùng Q8 trên 16GB nếu chưa kiểm VRAM.
- `--llm_timeout 1200`: 14B local decode lâu hơn 7B nên timeout phải cao hơn.
- `--llm_max_async 2`: chỉ dùng khi server 14B đang chạy `--parallel 2`; nếu context lỗi, đổi cả server sang p1 và build sang `--llm_max_async 1`.
- Các arg HuggingFace embedding giữ giống 7B để so sánh LLM 7B/14B công bằng, không đổi embedding space.
- `--chunk_size 1200 --chunk_overlap 100`: giữ cùng chunking để kết quả entity/relation có thể so với 7B.


Nếu community report lỗi context ở 14B p2/c32k, đổi sang server p1 và build:

```text
--model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p1-np4096
--llm_max_async 1
```

---

## 5. Chạy Tiếp 50/100/384 Docs

### 5.1 Cách khuyến nghị hiện tại

Vì source hiện tại chưa có resume theo `doc_start/doc_end`, không nên nhảy thẳng 384. Chạy tăng dần:

```text
1/5/10 -> 50 -> 100 -> 384
```

Nếu mục tiêu là benchmark sạch, dùng output folder riêng cho từng mốc:

```text
outputs/build_graph/..._050docs
outputs/build_graph/..._100docs
outputs/build_graph/..._384docs
```

Nếu mục tiêu là tiết kiệm thời gian và mốc trước đã pass hoàn toàn, có thể dùng cùng `output_dir` và tăng `--num_docs`, nhưng cần nhớ:

- `--num_docs` luôn đọc từ đầu corpus.
- Source sẽ skip docs đã có trong `kv_store_full_docs.json`.
- Cách này chỉ an toàn nếu mốc trước đã pass đủ output.
- Community reports có thể bị drop/rebuild vì config mặc định `enable_incremental=false`.

### 5.2 Lệnh 7B chạy 50/100/384 độc lập

```bash
tmux new -s bld_tq_turbo_7b_p2c64k_hf_nomic_050_384docs
```

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false

mkdir -p logs/build_graph outputs/build_graph results/usage

for D in 50 100 384; do
  L=$(printf "%03ddocs" "$D")
  export TG_RAG_USAGE_LOG=results/usage/cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_${L}.jsonl

  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_${L} \
    --model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider huggingface \
    --embedding_model nomic-ai/nomic-embed-text-v1.5 \
    --embedding_dim 768 \
    --embedding_max_tokens 7500 \
    --embedding_max_chars 24000 \
    --embedding_device cpu \
    --embedding_batch_size 16 \
    --embedding_batch_num 16 \
    --embedding_max_async 1 \
    --embedding_prefix "search_document: " \
    --chunk_size 1200 \
    --chunk_overlap 100 \
    --num_docs "$D" \
    --llm_max_async 2 \
    --llm_timeout 900 \
    2>&1 | tee logs/build_graph/cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_${L}.log
done
```

Giải thích nhanh ngay tại lệnh:

- Đây là run độc lập từng mốc `50/100/384`, mỗi mốc có `output_dir`, build log và usage log riêng.
- Ưu điểm: dễ so sánh kết quả và không bị trạng thái run trước làm nhiễu run sau.
- Nhược điểm: không tiết kiệm thời gian vì mỗi mốc build lại từ đầu corpus.
- Dùng cách này để benchmark sạch; nếu mục tiêu là tiết kiệm thời gian thì xem `md/runbooks/resume_setup.md`.
- Nếu 50 hoặc 100 fail, không chạy tiếp 384; đọc log trước để biết fail ở extraction, embedding hay community.

### 5.3 Lệnh 14B Q5 chạy 50/100 trước

Không khuyến nghị chạy thẳng 384 với 14B Q5 nếu 50/100 chưa pass sạch.

```bash
tmux new -s bld_tq_turbo_14bq5_p2c32k_hf_nomic_050_100docs
```

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false

mkdir -p logs/build_graph outputs/build_graph results/usage

for D in 50 100; do
  L=$(printf "%03ddocs" "$D")
  export TG_RAG_USAGE_LOG=results/usage/cmp_tq_turbo_14bq5_p2c32knp4096_hf_nomic_${L}.jsonl

  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_hf_nomic_${L} \
    --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider huggingface \
    --embedding_model nomic-ai/nomic-embed-text-v1.5 \
    --embedding_dim 768 \
    --embedding_max_tokens 7500 \
    --embedding_max_chars 24000 \
    --embedding_device cpu \
    --embedding_batch_size 16 \
    --embedding_batch_num 16 \
    --embedding_max_async 1 \
    --embedding_prefix "search_document: " \
    --chunk_size 1200 \
    --chunk_overlap 100 \
    --num_docs "$D" \
    --llm_max_async 2 \
    --llm_timeout 1200 \
    2>&1 | tee logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_hf_nomic_${L}.log
done
```


Giải thích nhanh ngay tại lệnh:

- Chỉ chạy `50 100` trước vì 14B Q5 local chậm và 384 docs chưa có bằng chứng pass sạch.
- `--model qwen3-14b-q5-...-p2-np4096`: phải đúng alias server 14B Q5 đang chạy.
- `--llm_timeout 1200`: giữ timeout cao hơn 7B vì 14B decode lâu hơn.
- `--llm_max_async 2`: chỉ giữ nếu server đang `--parallel 2`; nếu community context lỗi thì đổi server p1 và arg này thành `1`.
- Các arg HF embedding giữ giống 7B để lỗi embedding được kiểm soát bằng `embedding_max_chars` và để so sánh công bằng.
- Nếu `050docs` fail thì không chạy `100docs`; đọc log để xác định fail ở extraction, embedding hay community.

Nếu 50/100 pass sạch, mới chạy 384:

```bash
D=384
L=$(printf "%03ddocs" "$D")
export TG_RAG_USAGE_LOG=results/usage/cmp_tq_turbo_14bq5_p2c32knp4096_hf_nomic_${L}.jsonl

python -u build_graph.py \
  --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_hf_nomic_${L} \
  --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cpu \
  --embedding_batch_size 16 \
  --embedding_batch_num 16 \
  --embedding_max_async 1 \
  --embedding_prefix "search_document: " \
  --chunk_size 1200 \
  --chunk_overlap 100 \
  --num_docs "$D" \
  --llm_max_async 2 \
  --llm_timeout 1200 \
  2>&1 | tee logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_hf_nomic_${L}.log
```

---

## 6. Bảng Giải Thích Arg build_graph.py

### 6.1 LLM/backend args

| Arg | Ví dụ | Ý nghĩa | Khi nào chỉnh |
|---|---|---|---|
| `--local_llm_backend` | `turboquant` | Ép source dùng local OpenAI-compatible server | Dùng khi chạy `llama-server` TurboQuant |
| `--model` | `qwen25-7b-q8-...` | Alias model trên server | Phải khớp `llama-server --alias` |
| `--base_url` | `http://localhost:8080/v1` | URL server LLM | Đổi nếu port server khác |
| `--llm_max_async` | `2` | Số request LLM song song từ Python | Khớp `llama-server --parallel`; giảm xuống 1 nếu context lỗi |
| `--llm_timeout` | `900`, `1200` | Timeout mỗi request LLM | 14B nên cao hơn 7B |

### 6.2 Embedding args

| Arg | Ví dụ | Ý nghĩa | Khi nào chỉnh |
|---|---|---|---|
| `--embedding_provider` | `huggingface` | Dùng HF local embedding | Khuyến nghị hiện tại để tránh lỗi Ollama context |
| `--embedding_model` | `nomic-ai/nomic-embed-text-v1.5` | Model embedding HF | Nomic giữ dim 768, ít phá schema hơn |
| `--embedding_dim` | `768` | Vector dimension | Phải khớp model; BGE-M3 là 1024 |
| `--embedding_max_tokens` | `7500` | Giới hạn token model embedding | Nomic HF hỗ trợ dài hơn Ollama |
| `--embedding_max_chars` | `24000` | Cắt content quá dài trước embedding | Bắt buộc để tránh entity description phình |
| `--embedding_device` | `cpu` | Device chạy embedding | CPU ổn định nhất khi GPU đang chạy LLM |
| `--embedding_batch_size` | `16` | Batch bên trong SentenceTransformer | Giảm xuống 8 nếu dùng CUDA và thiếu VRAM |
| `--embedding_batch_num` | `16` | Số text mỗi batch vector store | Giảm nếu RAM/VRAM căng |
| `--embedding_max_async` | `1` | Số batch embedding chạy song song | Giữ 1 để tránh tranh tài nguyên |
| `--embedding_prefix` | `search_document: ` | Prefix Nomic document embedding | Nomic khuyến nghị prefix này |

### 6.3 Dataset/chunk/output args

| Arg | Ví dụ | Ý nghĩa | Khuyến nghị |
|---|---|---|---|
| `--corpus_path` | `ect-qa/corpus/base.jsonl.gz` | Corpus ECT-QA base 2020-2023 | Dùng base cho build graph chính |
| `--num_docs` | `1`, `5`, `10`, `50`, `100`, `384` | Số docs đầu tiên trong corpus | Chạy tăng dần, không nhảy thẳng 384 |
| `--chunk_size` | `1200` | Token mỗi chunk | Baseline hiện tại |
| `--chunk_overlap` | `100` | Overlap giữa chunks | Baseline hiện tại |
| `--output_dir` | `outputs/build_graph/...` | Folder output graph/vector/cache | Không reuse folder khi đổi embedding model/dim |
| `--config` | `tgrag/configs/config.yaml` | File config gốc | CLI override sẽ thay các giá trị quan trọng |

---

## 7. Config.yaml Và CLI Override

`tgrag/configs/config.yaml` hiện mặc định:

```yaml
building:
  provider: "gemini"
  model: "gemini-2.5-flash-lite"
  embedding_provider: "ollama"
  chunk_size: 1200
  chunk_overlap: 100
  enable_community_summary: true
```

Vì vậy khi chạy local LLM + TurboQuant, **phải dùng CLI override**:

```text
--local_llm_backend turboquant
--model <server-alias>
--base_url http://localhost:8080/v1
--embedding_provider huggingface
```

Không được chỉ nhìn GPU/VRAM để kết luận build dùng local LLM. Phải kiểm:

1. Dòng `[runtime]` trong build log.
2. Server log có `POST /v1/chat/completions`.
3. `kv_store_llm_response_cache.json` có model alias Qwen, không phải Gemini.

---

## 8. Check Sau Khi Chạy

### 8.1 Check build log

```bash
grep -E "runtime|embedding_provider|embedding_model|new chunks|extract_entities started|Processed .*chunks|chunk LLM extraction|embedding content lengths|Truncate embedding|Ollama embedding API error|Failed to generate community report|Graph building completed|Total elapsed" \
  /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_*hf_nomic_*.log
```

### 8.2 Check server log

```bash
grep -E "n_ctx|n_ctx_slot|truncated|POST /v1/chat/completions|exceeds|error" \
  /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_*hf_nomic_*.log
```

### 8.3 Check output count

Đổi `RUN_DIR` theo output cần kiểm:

```bash
export RUN_DIR=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_010docs

python - <<'PY'
import json
import os
from pathlib import Path

d = Path(os.environ["RUN_DIR"])

def load(name):
    p = d / name
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

full_docs = load("kv_store_full_docs.json")
text_chunks = load("kv_store_text_chunks.json")
communities = load("kv_store_community_reports.json")
entities = load("vdb_entities.json").get("data", {})
relations = load("vdb_relations.json").get("data", {})

community_errors = 0
for value in communities.values():
    raw = json.dumps(value, ensure_ascii=False)
    if "Failed to generate report" in raw or "Error Report" in raw:
        community_errors += 1

print("docs", len(full_docs))
print("chunks", len(text_chunks))
print("communities", len(communities))
print("community_errors", community_errors)
print("entities", len(entities))
print("relations", len(relations))
print("has_entity_graph", (d / "graph_chunk_entity_relation.graphml").exists())
print("has_temporal_graph", (d / "graph_temporal_hierarchy.graphml").exists())
PY
```

Một run được tính là pass khi:

```text
Graph building completed successfully
docs đúng bằng num_docs
chunks > 0
entities > 0
relations > 0
community_errors = 0 hoặc đã chấp nhận rõ lý do
GraphML có đủ
Không có Ollama embedding API error
```

---

## 9. Khi Nào Được Chạy 384?

Chỉ chạy 384 khi:

1. 1/5/10 pass.
2. 50 pass, không community error, không embedding error.
3. 100 pass, không community error, không embedding error.
4. Server log không có `truncated` hoặc context error.
5. Output count hợp lệ.

Nếu 50/100 có `Truncate embedding content` ít:

- Có thể tiếp tục, nhưng phải ghi nhận entity nào bị truncate.

Nếu truncate rất nhiều hoặc community prompt vẫn lỗi:

- Chưa nên chạy 384.
- Cần sửa merge description/community prompt hoặc dùng p1.

---

## 10. Lỗi Thường Gặp

| Lỗi | Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|---|
| Thiếu `einops` | `ImportError ... einops` | Nomic HF remote code cần dependency này | `pip install einops` |
| HF warning unauthenticated | `Warning: unauthenticated requests` | Chưa set HF token | Không fatal; set `HF_TOKEN` nếu bị rate-limit |
| Không kết nối server | TurboQuant healthcheck fail | Chưa start server hoặc sai port | Start `llama-server`, kiểm `/props` |
| Alias không khớp | model not found hoặc request lỗi | `--model` khác `--alias` | Sửa `--model` đúng alias server |
| Community context lỗi | `request (...) exceeds context size` | `--parallel` chia context slot quá nhỏ | Dùng p1 hoặc giảm prompt/community payload |
| Ollama embedding error | `Ollama embedding API error` | Đang dùng Ollama embedding hoặc config override sai | Kiểm `[runtime] embedding_provider=huggingface` |
| Output rỗng | có cache nhưng `full_docs=0` | Fail trước persist cuối | Không dùng output đó làm benchmark |

---

## 11. Tùy Chỉnh Nâng Cao

### 11.1 Chạy embedding trên CUDA

Chỉ thử khi GPU còn dư VRAM:

```text
--embedding_device cuda
--embedding_batch_size 8
--embedding_max_async 1
```

Không khuyến nghị mặc định cho 14B Q5 vì LLM server đã giữ GPU.

### 11.2 Thử chunk size khác

Baseline:

```text
--chunk_size 1200
--chunk_overlap 100
```

Test sau khi 50 docs ổn:

```text
--chunk_size 1600 --chunk_overlap 150
--chunk_size 2000 --chunk_overlap 150
```

Không tăng quá mạnh ngay vì:

- Prompt extraction dài hơn.
- Output extraction dễ vượt `--n-predict`.
- Temporal relation dễ bị trộn giữa nhiều sự kiện/quý.
- Community prompt có thể càng dài.

### 11.3 Đổi sang BGE-M3 sau này

Chỉ làm sau khi HF Nomic pass:

```text
--embedding_provider huggingface
--embedding_model BAAI/bge-m3
--embedding_dim 1024
--embedding_max_tokens 7500
--embedding_max_chars 24000
```

Không reuse output folder cũ vì vector dimension đổi từ 768 sang 1024.

---

## 12. Liên Hệ Với Resume

Hiện `build_graph.py` chưa có `--doc_start` / `--doc_end`, nên chưa có resume sạch theo doc range. Xem:

```text
md/runbooks/resume_setup.md
```

Trước khi chạy 384 nhiều lần, nên cân nhắc thêm:

- `--doc_start`
- `--doc_end`
- `--resume_manifest`
- chunk extraction checkpoint
- community rebuild-only

Nếu chưa có resume, 384 fail ở cuối sẽ tốn rất nhiều thời gian chạy lại.

