# CLI Resume Build Graph

Tài liệu này hướng dẫn chạy resume cho giai đoạn `build_graph.py` trong repo:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
```

Scope của cơ chế hiện tại:

- Chạy theo range docs bằng `--doc_start` / `--doc_end`.
- Ghi manifest trạng thái bằng `--resume_manifest`.
- Cache kết quả extraction từng chunk bằng `--enable_chunk_extraction_cache`.
- Cho phép build graph/vector trước và bỏ qua community bằng `--skip_community_reports`.
- Cho phép rebuild community reports từ graph đã persist bằng `--rebuild_communities_only`.

Mục tiêu thực tế là giảm rủi ro khi build ECT-QA 384 docs bằng local LLM: nếu lỗi sau khi đã extract chunks, lần sau không phải gọi lại toàn bộ LLM extraction.

---

## 1. Khi Nào Dùng Resume

| Tình huống | CLI nên dùng | Ý nghĩa |
|---|---|---|
| Muốn build 384 docs theo nhiều batch | `--doc_start`, `--doc_end`, cùng `--output_dir` | Batch sau chỉ thêm docs mới vào output hiện có |
| Sợ lỗi sau nhiều giờ extraction | `--enable_chunk_extraction_cache` | Mỗi chunk extract xong sẽ ghi cache riêng |
| Muốn tránh lỗi community prompt quá dài trong build chính | `--skip_community_reports` | Build docs/chunks/graph/vector trước, community xử lý sau |
| Graph/vector đã có, chỉ cần tạo lại community | `--rebuild_communities_only` | Không load docs, không chạy extraction lại |
| Muốn biết run nào completed/failed | `--resume_manifest` | Ghi JSON manifest để đối chiếu |

---

## 2. Các Arg Resume Mới

| Arg | Dùng khi nào | Giải thích |
|---|---|---|
| `--doc_start 0` | Build theo range | Index bắt đầu trong `ect-qa/corpus/base.jsonl.gz`, zero-based |
| `--doc_end 50` | Build theo range | Index kết thúc, exclusive; `0..50` nghĩa là 50 docs đầu |
| `--resume_manifest outputs/.../resume_manifest.json` | Luôn nên dùng cho run dài | Ghi trạng thái `running/completed/failed`, range docs, model, embedding |
| `--enable_chunk_extraction_cache` | Nên dùng cho local LLM | Ghi kết quả parsed entity/relation từng chunk |
| `--chunk_extraction_cache_path outputs/.../kv_store_chunk_extractions.json` | Nên đặt cố định theo run | Cache này có thể reuse nếu run fail trước persist cuối |
| `--skip_community_reports` | Build graph/vector trước | Tránh community report làm fail hoặc tạo error report ở cuối |
| `--rebuild_communities_only` | Sau khi graph/vector đã có | Load graph/hierarchy từ `--output_dir` rồi rebuild community |

Lưu ý: `--doc_end` là exclusive. Ví dụ:

```text
--doc_start 0 --doc_end 50    -> docs 0..49
--doc_start 50 --doc_end 100  -> docs 50..99
--doc_start 100 --doc_end 384 -> docs 100..383
```

---

## 3. Profile Khuyến Nghị Cho 7B Resume

Profile này giả định đã start server 7B:

```text
alias: qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072
URL:   http://localhost:8080/v1
```

Nếu muốn an toàn hơn về community context, dùng server p1/p2 theo `md/CLI/start_server.md`. Với workflow resume dưới đây, build chính dùng `--skip_community_reports`, nên p4 chủ yếu ảnh hưởng extraction throughput, không bị community chặn ở cuối.

---

## 4. Build Graph/Vector Theo Batch Và Skip Community

Tạo tmux:

```bash
tmux new -s BUILD_resume_qwen25_7b_hf_nomic_graph_vector_000_384
```

Trong tmux:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false

RUN_NAME=tq_7b_hf_nomic_resume_384_graph_vector
OUTPUT_DIR=outputs/build_graph/${RUN_NAME}
MANIFEST=${OUTPUT_DIR}/resume_manifest.json
CHUNK_CACHE=${OUTPUT_DIR}/kv_store_chunk_extractions.json

mkdir -p logs/build_graph results/usage "$OUTPUT_DIR"

for RANGE in 0:50 50:100 100:384; do
  START=${RANGE%:*}
  END=${RANGE#*:}
  LABEL=$(printf "%03d_%03d" "$START" "$END")

  export TG_RAG_USAGE_LOG=results/usage/${RUN_NAME}_${LABEL}.jsonl

  python -u build_graph.py \
    --output_dir "$OUTPUT_DIR" \
    --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider huggingface \
    --embedding_model nomic-ai/nomic-embed-text-v1.5 \
    --embedding_dim 768 \
    --embedding_max_tokens 7500 \
    --embedding_max_chars 24000 \
    --embedding_device cuda \
    --embedding_batch_size 8 \
    --embedding_batch_num 16 \
    --embedding_max_async 1 \
    --embedding_prefix "search_document: " \
    --chunk_size 1200 \
    --chunk_overlap 100 \
    --doc_start "$START" \
    --doc_end "$END" \
    --num_docs "$((END - START))" \
    --llm_max_async 4 \
    --llm_timeout 900 \
    --entity_extraction_timeout 43200 \
    --skip_community_reports \
    --enable_chunk_extraction_cache \
    --chunk_extraction_cache_path "$CHUNK_CACHE" \
    --resume_manifest "$MANIFEST" \
    2>&1 | tee logs/build_graph/${RUN_NAME}_${LABEL}.log
done
```

Giải thích ngay trong lệnh:

- `OUTPUT_DIR` giữ cố định cho toàn bộ 384 docs; batch sau thêm docs mới vào graph/vector hiện có.
- `MANIFEST` ghi trạng thái từng batch để biết range nào đã completed/failed.
- `CHUNK_CACHE` giữ cố định để nếu fail sau extraction, rerun có thể dùng lại extraction theo chunk.
- `--doc_start/--doc_end` chia corpus thành batch thật, không phải lần nào cũng load từ đầu.
- `--skip_community_reports` bỏ qua community ở build chính để tránh lỗi prompt quá dài làm bẩn report.
- `--enable_chunk_extraction_cache` ghi parsed entities/relations từng chunk.
- `--embedding_device cuda` nhanh hơn CPU, nhưng nếu VRAM căng thì đổi thành `cpu`.
- `--llm_max_async 4` phải khớp server `--parallel 4`. Nếu server p2 thì đổi thành 2; server p1 thì đổi thành 1.

Nếu một batch fail sau khi đã xử lý nhiều chunks, chạy lại đúng batch đó với cùng:

```text
OUTPUT_DIR
CHUNK_CACHE
MANIFEST
doc_start/doc_end
model
chunk_size/chunk_overlap
```

Các chunk đã có trong `CHUNK_CACHE` sẽ hiện:

```text
[cache]
chunk LLM extraction + parsing: 0.00s
```

---

## 5. Rebuild Community Reports Sau Khi Graph/Vector Đã Có

Sau khi batch 0:50, 50:100, 100:384 pass graph/vector, chạy community-only.

Tạo tmux:

```bash
tmux new -s BUILD_resume_qwen25_7b_hf_nomic_community_only
```

Trong tmux:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

RUN_NAME=tq_7b_hf_nomic_resume_384_graph_vector
OUTPUT_DIR=outputs/build_graph/${RUN_NAME}
MANIFEST=${OUTPUT_DIR}/resume_manifest.json

mkdir -p logs/build_graph results/usage
export TG_RAG_USAGE_LOG=results/usage/${RUN_NAME}_community_only.jsonl

python -u build_graph.py \
  --output_dir "$OUTPUT_DIR" \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cuda \
  --embedding_batch_size 8 \
  --embedding_batch_num 16 \
  --embedding_max_async 1 \
  --embedding_prefix "search_document: " \
  --llm_max_async 4 \
  --llm_timeout 900 \
  --rebuild_communities_only \
  --resume_manifest "$MANIFEST" \
  2>&1 | tee logs/build_graph/${RUN_NAME}_community_only.log
```

Giải thích:

- `--rebuild_communities_only` không load docs, không chunk, không extraction.
- Source load `graph_chunk_entity_relation.graphml` và `graph_temporal_hierarchy.graphml` từ `OUTPUT_DIR`.
- Sau đó drop và rebuild `kv_store_community_reports.json`.
- Nếu community prompt vẫn vượt context, đổi server sang p1 hoặc cần code giới hạn/split community payload.

---

## 6. Check Sau Khi Chạy

### 6.1 Check manifest

```bash
python - <<'PY'
import json
from pathlib import Path

manifest = Path("outputs/build_graph/tq_7b_hf_nomic_resume_384_graph_vector/resume_manifest.json")
data = json.load(open(manifest, encoding="utf-8"))
for run in data.get("runs", []):
    print(run["stage"], run["status"], run.get("doc_start"), run.get("doc_end"), run.get("updated_at"))
PY
```

Kỳ vọng:

```text
insert completed 0 50
insert completed 50 100
insert completed 100 384
community-only completed ...
```

### 6.2 Check output counts

```bash
python - <<'PY'
import json
from pathlib import Path

base = Path("outputs/build_graph/tq_7b_hf_nomic_resume_384_graph_vector")
for name in [
    "kv_store_full_docs.json",
    "kv_store_text_chunks.json",
    "kv_store_community_reports.json",
    "kv_store_llm_response_cache.json",
]:
    p = base / name
    print(name, len(json.load(open(p, encoding="utf-8"))) if p.exists() else "MISSING")

for name in ["vdb_entities.json", "vdb_entities_new.json", "vdb_relations.json"]:
    p = base / name
    if p.exists():
        data = json.load(open(p, encoding="utf-8"))
        print(name, len(data.get("data", {})))
    else:
        print(name, "MISSING")
PY
```

### 6.3 Check community errors

```bash
grep -o "Failed to generate report\\|Error Report\\|Report generation failed" \
  outputs/build_graph/tq_7b_hf_nomic_resume_384_graph_vector/kv_store_community_reports.json | sort | uniq -c
```

Clean pass community thì command này không nên in ra lỗi.

### 6.4 Check chunk cache hit

```bash
grep -E "chunk extraction cache enabled|\\[cache\\]|chunk LLM extraction \\+ parsing" \
  logs/build_graph/tq_7b_hf_nomic_resume_384_graph_vector_*.log
```

Nếu rerun sau fail và cache hoạt động, log sẽ có:

```text
entries=<số chunk đã cache>
[cache]
chunk LLM extraction + parsing: 0.00s
```

---

## 7. Smoke Test Đã Chạy

Đã test trên server hiện có:

```text
qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072
```

Kết quả:

| Test | Kết quả | Log |
|---|---|---|
| Build doc range `0..1`, skip community, chunk cache | Pass | `logs/build_graph/resume_smoke_20260525_194908_source.log` |
| Rebuild output mới từ cùng chunk cache | Pass, 5/5 chunks cache hit | `logs/build_graph/resume_smoke_20260525_194908_cache_reuse.log` |
| Community-only rebuild | Pass, 3 reports | `logs/build_graph/resume_smoke_20260525_194908_community_only.log` |
| Build tiếp doc range `1..2` vào cùng output | Pass, output có 2 docs / 9 chunks | `logs/build_graph/resume_smoke_20260525_194908_doc_range_001_002.log` |

Điểm quan trọng từ smoke:

```text
chunk LLM extraction + parsing: 157.68s  # lần đầu
chunk LLM extraction + parsing: 0.00s    # rerun dùng chunk cache
```

---

## 8. Giới Hạn Hiện Tại

Cơ chế này đã giúp resume thực tế tốt hơn, nhưng chưa phải transaction system hoàn chỉnh.

| Giới hạn | Ý nghĩa |
|---|---|
| Chunk cache chỉ cache extraction parsed result | Vector upsert và community vẫn rebuild |
| `--rebuild_communities_only` rebuild toàn bộ community | Chưa có mode chỉ rebuild 10 community lỗi |
| Community prompt quá lớn vẫn có thể fail | Cần thêm cap/split community payload nếu full 384 vẫn lỗi context |
| Nếu đổi model/prompt/chunk_size nên dùng cache mới | Cache key có model/prompt/content hash, nhưng vận hành sạch nhất vẫn là cache riêng mỗi profile |
| Nếu đổi embedding model/dim không reuse vector output cũ | Phải build lại vector DB |

Với full 384 docs, hướng ổn định là:

1. Build graph/vector theo batch với `--skip_community_reports`.
2. Luôn bật `--enable_chunk_extraction_cache`.
3. Sau khi graph/vector hoàn tất, chạy `--rebuild_communities_only`.
4. Nếu community còn lỗi context, fix tiếp bằng giới hạn/split community prompt, không chạy lại extraction từ đầu.

