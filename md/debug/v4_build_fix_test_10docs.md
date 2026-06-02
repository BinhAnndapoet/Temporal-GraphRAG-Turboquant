# V4 Build Fix Test (10 Docs)

## Mục tiêu

Test lại nhánh build sau khi đã sửa lỗi community packing và bổ sung runtime budget guard cho `llama-server` local. Bài test này chỉ chạy trên `10` document đầu của ECT-QA để xác nhận:

1. build có ghi log text rõ ràng;
2. build tự suy ra budget an toàn từ `/props`;
3. temporal community report không còn fail do overflow trong case nhỏ;
4. output có manifest để query/demo dùng lại runtime đúng hơn.

## Phạm vi code đã sửa

### 1. `build_graph.py`

Các thay đổi chính:

- Đọc `llama-server /props` để lấy slot context thực tế: [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:44)
- Tự tính `best_model_max_token_size` an toàn theo `slot_n_ctx - community_token_headroom`: [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:163)
- Bổ sung CLI args:
  - `--best_model_max_token_size`
  - `--community_token_headroom`
  Nguồn: [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:720)
- Ghi `build_manifest.json` ngay từ lúc init và khi build hoàn tất/thất bại: [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:786)
- In rõ runtime quan trọng:
  - `Slot context`
  - `Community pack budget`
  Nguồn: [build_graph.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py:846)

### 2. `tgrag/src/core/building.py`

Các thay đổi chính:

- Sửa truncate edge payload theo đúng `description` field thay vì field sai: [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1412)
- Sửa key matching khi fallback theo sub-community để temporal edge được include/exclude đúng tuple `(timestamp, source, target)`: [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1442)
- Khi generate temporal community report, dùng `llm_extra_kwargs` đúng như config thay vì hardcode `response_format={'type': 'json_object'}`: [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:1954)
- Khi retry cạn, đặt label error report rõ hơn bằng `name/title/timestamp`: [building.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py:2015)

## Vì sao `v3` vẫn fail

`v3` không chỉ fail vì cấu hình `parallel`; nó còn dính lỗi logic ở phase community packing:

- app pack prompt theo budget logic nội bộ;
- edge truncation dùng sai field nên prompt phình quá lớn;
- fallback sub-community không match temporal edge đúng tuple;
- runtime local không biết slot context thật của `llama-server` nếu chỉ nhìn `best_model_max_token_size` trong config.

Kết quả là nhiều prompt temporal community vượt ngưỡng server, dù đã giảm từ `p4` xuống `p2`.

## Lệnh test thực tế đã chạy

### 1. Start server trong tmux

Session: `tq_v4_srv`

```bash
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
  --n-predict 3072 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log
```

### 2. Build trong tmux

Session: `tq_v4_build`

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false
export OPENAI_API_KEY=dummy
export TG_RAG_USAGE_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl

conda run --no-capture-output -n turboquant python -u build_graph.py \
  --output_dir /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4 \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --base_url http://127.0.0.1:8080/v1 \
  --corpus_path /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_batch_num 16 \
  --embedding_max_async 1 \
  --embedding_prefix "search_document: " \
  --chunk_size 1200 \
  --chunk_overlap 100 \
  --num_docs 10 \
  --llm_max_async 2 \
  --llm_timeout 900 \
  --entity_extraction_timeout 43200 \
  |& tee /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log
```

## Lưu ý quan trọng về build log

Lý do các run trước có thể không có file log text:

- `build_graph.py` hiện không tự tạo `logs/build_graph/*.log`;
- muốn có log text, shell phải tự `tee` hoặc redirect stdout/stderr;
- nếu dùng `conda run` mà không thêm `--no-capture-output`, output sẽ dễ bị nuốt hoặc không stream ra `tee` như kỳ vọng.

Nói ngắn:

- `usage jsonl` là do `TG_RAG_USAGE_LOG`;
- `build text log` là do shell command của người chạy;
- với tmux + conda, nên dùng `conda run --no-capture-output ... |& tee ...`.

## Artifact của bài test

- Output: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4)
- Build log: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:1)
- Server log: [SERVER_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:1)
- Usage log: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl:1)
- Manifest: [build_manifest.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4/build_manifest.json:1)

## Kết quả runtime đã xác nhận

Theo manifest:

- `build_status = completed`
- `wire_protocol = openai-compatible-local`
- `server_slot_tokens = 65536`
- `server_total_slots = 2`
- `best_model_max_token_size = 61440`
- `community_token_headroom = 4096`
- `budget_resolution = auto_from_server_props`

Nguồn: [build_manifest.json](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4/build_manifest.json:1)

Theo build log:

- `10` docs
- `39` chunks
- `437` entities
- `544` relations
- `20` temporal communities
- total build time `1009.58s`

Nguồn: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log:1)

Theo usage log:

- `101` dòng `api_success`
- `1` dòng `cache_hit`
- `0` dòng `api_error`
- request lớn nhất chỉ khoảng:
  - `prompt_tokens = 26233`
  - `total_tokens = 27140`

Nguồn: [BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl:1)

## Kiểm tra community output

Tôi đã grep các dấu hiệu lỗi thường gặp trong:

- build log
- usage log
- `kv_store_community_reports.json`

Không thấy:

- `Failed to generate community report`
- `Error Report for ...`
- `api_error`

Điều này xác nhận bài test `v4` 10-doc đã đi qua phase community sạch.

## Diễn giải kỹ thuật

Kết quả `v4` cho thấy nhánh build hiện đã sửa đúng hai lớp lỗi:

1. **lỗi code pack/truncate temporal community**
   - trước đây app có thể giữ lại quá nhiều edge text vì truncate sai field;
   - nay payload community nhỏ đi đúng theo `description`.

2. **lỗi runtime budget mismatch với `llama-server`**
   - trước đây app tin vào budget config logic;
   - nay app đọc thẳng slot context thật của server rồi tự clamp budget.

Trong test này, server slot là `65536`, nên build chọn budget `61440`. Với 10 docs đầu của ECT-QA, budget đó đủ để không sinh overflow.

## Giới hạn của bài test này

Đây chưa phải bằng chứng rằng build `384 docs` sẽ sạch hoàn toàn.

Lý do:

- 10 docs có cộng đồng nhỏ hơn nhiều;
- hierarchy/community density thấp hơn;
- request lớn nhất mới tới khoảng `26k prompt tokens`, còn cách khá xa `61k`.

Do đó, `v4` hiện mới chứng minh:

- fix đã đúng hướng;
- logging/runbook đã đúng;
- pipeline build local với TurboQuant + HF embedding có thể chạy sạch trong case nhỏ.

Nó chưa chứng minh chắc chắn rằng `384 docs` sẽ không còn community overflow hoặc degraded report quality.

## Đề xuất bước tiếp theo

1. Commit nhánh build hiện tại.
2. Chạy tiếp một batch trung gian, ví dụ `50` hoặc `100` docs, vẫn trên `p2`.
3. Nếu sạch, mới nâng lên full `384 docs`.
4. Sau khi có output full sạch, dùng lại nhánh query/demo đã sửa để benchmark:
   - local TurboQuant
   - Gemini
   - cùng một `working_dir`
   - cùng embedding runtime đúng theo manifest.
