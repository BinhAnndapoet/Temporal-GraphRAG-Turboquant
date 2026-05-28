# 7B Community Context Fix v2

> Ghi chú thay đổi cho branch `test/7b-community-context-fix`.
>
> Mục tiêu của branch này không phải đổi core pipeline, mà là làm cho build 7B ổn định hơn ở **community report stage** bằng cách giữ prompt dưới ngưỡng context của từng slot `llama-server`.

---

## 1) Vấn đề được xác nhận từ log v2

Build 7B `fresh-v2` đã đi qua extraction khá ổn, nhưng vẫn fail ở community report.

### Tín hiệu chính

- Server đang chạy `-c 131072 --parallel 4`
- Mỗi slot thực tế chỉ còn khoảng `32768` context
- Trong `kv_store_community_reports.json` có đúng **2** report lỗi:
  - `"2021"` → request `34777 tokens`
  - `"2022"` → request `38243 tokens`
- Cả hai đều vượt slot context nên server trả lỗi:
  - `exceed_context_size_error`

### Kết luận ngắn

Lỗi không nằm ở decode speed hay timeout tổng của build.
Lỗi nằm ở **community prompt packing quá dài** so với context mỗi slot.

---

## 2) Hướng cải tiến của branch

Branch này đi theo hướng:

1. **Hạ `best_model_max_token_size`** để community prompt được truncate sớm hơn.
2. **Giảm noise của extraction** bằng cách tắt gleaning trong preset test.
3. **Tắt entity summarization** để tránh thêm LLM call không cần thiết.
4. **Giữ throughput test nguyên trạng** ở `--parallel 4` để kiểm tra xem chỉ chỉnh context packing đã đủ hay chưa.

### Preset test đã tạo

File:

- `tgrag/configs/config_7b_v2_community_fix.yaml`

Giá trị chính:

- `best_model_max_token_size: 24000`
- `entity_extract_max_gleaning: 0`
- `disable_entity_summarization: true`
- `max_graph_cluster_size: 8`

---

## 3) File thay đổi trong branch

### `tgrag/configs/config_7b_v2_community_fix.yaml`

Preset riêng cho run test 7B v2.

Mục đích:

- không đụng `config.yaml` gốc
- dễ so sánh trước/sau
- dễ rollback nếu cần

### `md/runbooks/7b_community_context_fix_v2.md`

File note này để:

- ghi lại root cause
- mô tả hướng cải tiến
- lưu lại lệnh chạy tmux
- giữ một bản mô tả có thể đọc nhanh khi quay lại sau

---

## 4) Server/build CLI đề xuất để test

### Start server

```bash
tmux new -s SERVER_llama_server_qwen25_7b_p4_c131072_ctx24k

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
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_qwen25_7b_p4_c131072_ctx24k_$(date +%Y%m%d_%H%M%S).log
```

### Build graph

```bash
tmux new -s BUILD_qwen25_7b_p4_c131072_ctx24k_v1

conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false
export TG_RAG_USAGE_LOG=results/usage/BUILD_qwen25_7b_p4_c131072_ctx24k_v1.jsonl

mkdir -p logs/build_graph outputs/build_graph results/usage

python -u build_graph.py \
  --config tgrag/configs/config_7b_v2_community_fix.yaml \
  --output_dir outputs/build_graph/BUILD_qwen25_7b_p4_c131072_ctx24k_v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --num_docs 384 \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --entity_extraction_timeout 43200 \
  2>&1 | tee logs/build_graph/BUILD_qwen25_7b_p4_c131072_ctx24k_v1.log
```

---

## 5) Kỳ vọng khi test

Nếu fix đúng:

- không còn `Error Report for Unknown`
- community report không vượt `32768` tokens / slot
- build vẫn giữ được throughput của `--parallel 4`
- output cuối cùng sạch hơn so với `fresh-v2`

Nếu vẫn fail:

- hạ tiếp `--parallel 4` → `--parallel 2`
- hoặc giảm `best_model_max_token_size` thêm xuống `20000`

---

## 6) Ghi chú nhanh

- Branch test hiện tại: `test/7b-community-context-fix`
- Preset test riêng: `config_7b_v2_community_fix.yaml`
- Root cause đã xác nhận từ log: **community prompt overflow**, không phải decode chậm
