# Add Runtime Logging Plan

Tài liệu này chỉ mô tả các điểm còn thiếu và hướng thêm log/runtime usage trong source. Đây chưa phải code triển khai.

## Mục Tiêu

Có hai nhóm log cần tách rõ:

| Nhóm | Mục tiêu | Trạng thái hiện tại |
|---|---|---|
| Export/import Neo4j log | Ghi lại từng bước export CSV, copy vào container, import Cypher, check count | Guide mới đã dùng `tee`; script Python hiện chỉ cần bổ sung log nội bộ nếu muốn |
| LLM usage runtime log | Ghi JSONL token usage theo `TG_RAG_USAGE_LOG` | Source hiện chưa có producer, chỉ có convention trong README |

---

# 1. Export/import Neo4j Log

## Vì Sao Cần Log

Giai đoạn export/import có nhiều điểm dễ lỗi:

- Thiếu file input trong `working_dir`.
- CSV export ra thiếu dòng hoặc schema sai.
- `docker cp` copy nhầm path.
- Neo4j container chưa ready.
- `cypher-shell` fail giữa chừng.
- Count trong Neo4j không khớp `manifest.json`.
- Quyền Docker/rootless sai.

Script export hiện có `print(...)`, nhưng nếu không ghi ra file thì chạy xong khó kiểm lại. Vì vậy workflow nên có log dạng:

```text
logs/graphdb_export/<GRAPH_RUN_ID>.log
```

## Cách Nên Log Ở Workflow Shell

Workflow shell nên dùng `tee` vì nó capture được cả các lệnh ngoài Python:

```bash
{
  echo "===== PRE-EXPORT INPUT CHECK ====="
  ls -la ${WORKING_DIR}/graph_chunk_entity_relation.graphml
  ls -la ${WORKING_DIR}/kv_store_full_docs.json
  ls -la ${WORKING_DIR}/kv_store_text_chunks.json

  echo "===== RUN EXPORT SCRIPT ====="
  python scripts/graph_database/export_temporal_graphrag_to_tables.py \
    --working_dir ${WORKING_DIR} \
    --export_dir ${EXPORT_DIR} \
    --graph_run_id ${GRAPH_RUN_ID} \
    --overwrite

  echo "===== VERIFY EXPORT OUTPUT ====="
  ls -la ${EXPORT_DIR}

  echo "===== MANIFEST ====="
  cat ${EXPORT_DIR}/manifest.json
} 2>&1 | tee ${EXPORT_LOG}
```

Import/copy cũng nên append vào cùng log:

```bash
{
  echo "===== COPY EXPORT INTO CONTAINER ====="
  docker cp ${EXPORT_DIR}/. \
    tgrag-neo4j:/var/lib/neo4j/import/${GRAPH_RUN_ID}/

  echo "===== IMPORT CYPHER ====="
  docker exec -i tgrag-neo4j \
    cypher-shell -u neo4j -p tgrag-local-2026 \
    -f /var/lib/neo4j/import/${GRAPH_RUN_ID}/neo4j_import.cypher
} 2>&1 | tee -a ${EXPORT_LOG}
```

## Source Hiện Tại

File:

```text
scripts/graph_database/export_temporal_graphrag_to_tables.py
```

Hiện source chủ yếu dùng `print(...)`:

```python
print(f"[*] Đang đọc dữ liệu từ: {work_dir}")
...
print(f"[*] Đang ghi CSV ra: {export_dir}")
...
print(f"[Success] Export thành công! Đã tạo manifest và neo4j_import.cypher.")
```

Điểm thiếu:

- Không có `--log_file`.
- Không ghi input file size.
- Không ghi số row chuẩn bị cho từng CSV.
- Không ghi path/size file output.
- Không ghi elapsed time.

## Patch Minh Họa Nếu Muốn Thêm Log Nội Bộ Python

Đây là diff minh họa, chưa phải yêu cầu bắt buộc vì `tee` ở workflow đã đủ để capture toàn bộ quá trình.

```diff
 import argparse
 import json
+import logging
 import networkx as nx
 import pandas as pd
 from pathlib import Path
 from datetime import datetime

+logger = logging.getLogger("tgrag.graphdb_export")
+
+def setup_logging(log_file=None):
+    handlers = [logging.StreamHandler()]
+    if log_file:
+        log_path = Path(log_file)
+        log_path.parent.mkdir(parents=True, exist_ok=True)
+        handlers.append(logging.FileHandler(log_path, mode="a", encoding="utf-8"))
+
+    logging.basicConfig(
+        level=logging.INFO,
+        format="%(asctime)s %(levelname)s %(message)s",
+        handlers=handlers,
+        force=True,
+    )
+
+def file_info(path: Path) -> str:
+    stat = path.stat()
+    return f"{path} size={stat.st_size} bytes mtime={datetime.fromtimestamp(stat.st_mtime).isoformat()}"
```

```diff
 def parse_args():
     parser = argparse.ArgumentParser(description="Export Temporal-GraphRAG output to CSV for Neo4j")
     parser.add_argument("--working_dir", required=True, help="Folder output graph đã build")
     parser.add_argument("--export_dir", required=True, help="Folder lưu CSV export")
     parser.add_argument("--graph_run_id", required=True, help="ID định danh cho lần chạy này")
     parser.add_argument("--overwrite", action="store_true", help="Ghi đè nếu folder export đã tồn tại")
+    parser.add_argument("--log_file", help="File log riêng cho Python export")
     return parser.parse_args()
```

```diff
 def main():
     args = parse_args()
+    setup_logging(args.log_file)
+
+    start_time = datetime.now()
+    logger.info("===== START GRAPHDB EXPORT =====")
+    logger.info("graph_run_id=%s", args.graph_run_id)
+    logger.info("working_dir=%s", args.working_dir)
+    logger.info("export_dir=%s", args.export_dir)
     work_dir = Path(args.working_dir)
     export_dir = Path(args.export_dir)
```

```diff
     for f in req_files:
-        if not (work_dir / f).exists():
-            raise FileNotFoundError(f"[Error] Thiếu file bắt buộc: {f}")
+        path = work_dir / f
+        if not path.exists():
+            logger.error("Missing required file: %s", path)
+            raise FileNotFoundError(f"[Error] Thiếu file bắt buộc: {path}")
+        logger.info("input %s", file_info(path))
```

```diff
     entity_graph = nx.read_graphml(work_dir / "graph_chunk_entity_relation.graphml")
     full_docs = safe_load_json(work_dir / "kv_store_full_docs.json")
     text_chunks = safe_load_json(work_dir / "kv_store_text_chunks.json")
+    logger.info(
+        "Loaded graph nodes=%s edges=%s full_docs=%s text_chunks=%s",
+        entity_graph.number_of_nodes(),
+        entity_graph.number_of_edges(),
+        len(full_docs),
+        len(text_chunks),
+    )
```

```diff
+    logger.info(
+        "Prepared rows docs=%s chunks=%s entity_nodes=%s entity_relationships=%s node_chunk_links=%s",
+        len(docs_data),
+        len(chunks_data),
+        len(nodes_data),
+        len(edges_data),
+        len(node_chunk_links),
+    )
+
     pd.DataFrame(docs_data).to_csv(export_dir / "docs.csv", index=False)
     pd.DataFrame(chunks_data).to_csv(export_dir / "chunks.csv", index=False)
     pd.DataFrame(nodes_data).to_csv(export_dir / "entity_nodes.csv", index=False)
     pd.DataFrame(edges_data).to_csv(export_dir / "entity_relationships.csv", index=False)
     pd.DataFrame(node_chunk_links).to_csv(export_dir / "node_chunk_links.csv", index=False)
+    for csv_name in [
+        "docs.csv",
+        "chunks.csv",
+        "entity_nodes.csv",
+        "entity_relationships.csv",
+        "node_chunk_links.csv",
+    ]:
+        logger.info("output %s", file_info(export_dir / csv_name))
```

```diff
     with open(export_dir / "manifest.json", "w", encoding="utf-8") as f:
         json.dump(manifest, f, indent=4)

-    print(f"[Success] Export thành công! Đã tạo manifest và neo4j_import.cypher.")
+    elapsed = (datetime.now() - start_time).total_seconds()
+    logger.info(
+        "[Success] Export thành công! Đã tạo manifest và neo4j_import.cypher. elapsed_seconds=%.2f",
+        elapsed,
+    )
```

## Lệnh Test Export Theo Guide Mới

Dùng output nhỏ đã build xong trước để smoke test:

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant

export BUILD_CASE=output_ollama
export WORKING_DIR=outputs/build_graph/${BUILD_CASE}
export RUN_ID=$(date +%Y%m%d_%H%M%S)
export GRAPH_RUN_ID="${BUILD_CASE}_neo4j_smoke_${RUN_ID}"
export EXPORT_ROOT=outputs/database_exports
export EXPORT_DIR=${EXPORT_ROOT}/${GRAPH_RUN_ID}
export EXPORT_LOG=logs/graphdb_export/${GRAPH_RUN_ID}.log

mkdir -p ${EXPORT_ROOT} logs/graphdb_export
echo "${GRAPH_RUN_ID}" > .last_graph_run_id

{
  echo "===== PRE-EXPORT INPUT CHECK ====="
  ls -la ${WORKING_DIR}/graph_chunk_entity_relation.graphml
  ls -la ${WORKING_DIR}/kv_store_full_docs.json
  ls -la ${WORKING_DIR}/kv_store_text_chunks.json

  echo "===== RUN EXPORT SCRIPT ====="
  python scripts/graph_database/export_temporal_graphrag_to_tables.py \
    --working_dir ${WORKING_DIR} \
    --export_dir ${EXPORT_DIR} \
    --graph_run_id ${GRAPH_RUN_ID} \
    --overwrite

  echo "===== VERIFY EXPORT OUTPUT ====="
  ls -la ${EXPORT_DIR}

  echo "===== MANIFEST ====="
  cat ${EXPORT_DIR}/manifest.json
} 2>&1 | tee ${EXPORT_LOG}
```

Kỳ vọng:

```text
outputs/database_exports/<GRAPH_RUN_ID>/
logs/graphdb_export/<GRAPH_RUN_ID>.log
```

---

# 2. Runtime LLM Usage Log

## Kết Luận Hiện Tại

`logs/usage` đang thiếu producer, không phải thiếu folder.

README có convention:

```bash
export TG_RAG_USAGE_LOG=logs/usage/<CASE>_<RUN_ID>.jsonl
```

Nhưng runtime source chưa đọc biến này và chưa ghi JSONL.

## Luồng Source Hiện Tại

Luồng LLM hiện tại:

1. `build_graph.py` tạo `TemporalGraphRAG` và truyền `base_url`.
2. `tgrag/src/build.py` tạo `llm_func`.
3. `tgrag/src/llm/completion.py` gọi `openai_complete_if_cache`.
4. `openai_complete_if_cache` gọi `chat.completions.create(...)`.
5. Sau đó source chỉ lấy `response.choices[0].message.content`.
6. `response.usage` bị bỏ qua.
7. Cache chỉ lưu `{"return": response_text, "model": model}`, không lưu usage.

Code hiện tại:

```python
response = await openai_client.chat.completions.create(
    model=model, messages=messages, timeout=request_timeout, **kwargs
)

response_text = response.choices[0].message.content

if hashing_kv is not None:
    await hashing_kv.upsert(
        {args_hash: {"return": response_text, "model": model}}
    )
    await hashing_kv.index_done_callback()

return response_text
```

## CostTracker Có Nhưng Chưa Được Nối

`CostTracker` đã có ý tưởng nhận usage:

```python
if isinstance(response, tuple) and len(response) >= 2 and isinstance(response[1], dict):
    usage = response[1]
    prompt_tokens = int(usage.get("prompt_tokens", 0))
    completion_tokens = int(usage.get("completion_tokens", 0))
```

Nhưng LLM function hiện trả string:

```python
return response_text
```

Vì vậy `CostTracker` không lấy được token usage nếu không đổi contract trả về hoặc thêm producer ghi log bên cạnh.

## Hướng Thêm Usage Log Ít Đụng Code Nhất

Không nên đổi return type của `openai_complete_if_cache` từ `str` sang `(str, usage)` ngay, vì nhiều nơi trong build/query đang kỳ vọng string.

Hướng ít rủi ro hơn:

- Giữ return type là `str`.
- Đọc env `TG_RAG_USAGE_LOG`.
- Nếu env tồn tại, append một dòng JSONL sau mỗi response thật.
- Với cache hit, có thể ghi event `cache_hit=true` nếu cache có usage; nếu cache chưa lưu usage thì ghi usage rỗng.

## Format JSONL Đề Xuất

Một dòng:

```json
{
  "ts": "2026-05-22T07:30:00.123456",
  "provider": "openai",
  "model": "qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096",
  "base_url": "http://localhost:8080/v1",
  "request_id": "uuid",
  "cache_hit": false,
  "prompt_chars": 12345,
  "response_chars": 6789,
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 567,
    "total_tokens": 1801
  }
}
```

Format này tương thích với `scripts/eval/summarize_usage.py`, vì script đang đọc:

```python
usage = row.get("usage", {})
model = f"{row.get('provider', '')}:{row.get('model', '')}"
```

## Patch Minh Họa Cho `completion.py`

Thêm import:

```diff
 import logging
+import os
+import json
 from typing import Optional, List, Any, Dict, Callable
+from datetime import datetime
```

Thêm helper:

```diff
+def _usage_to_dict(response: Any) -> Dict[str, Any]:
+    usage = getattr(response, "usage", None)
+    if usage is None:
+        return {}
+    if hasattr(usage, "model_dump"):
+        return usage.model_dump()
+    if isinstance(usage, dict):
+        return usage
+    return {
+        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
+        "completion_tokens": getattr(usage, "completion_tokens", 0),
+        "total_tokens": getattr(usage, "total_tokens", 0),
+    }
+
+
+def _append_usage_log(row: Dict[str, Any]) -> None:
+    usage_log = os.getenv("TG_RAG_USAGE_LOG")
+    if not usage_log:
+        return
+    path = Path(usage_log)
+    path.parent.mkdir(parents=True, exist_ok=True)
+    with path.open("a", encoding="utf-8") as f:
+        f.write(json.dumps(row, ensure_ascii=False) + "\n")
```

Lưu ý nếu thêm `Path` thì cần import:

```diff
+from pathlib import Path
```

Trong cache hit:

```diff
         if cached_response is not None:
             logger.debug(f"[{request_id}] Cache hit")
+            _append_usage_log({
+                "ts": datetime.now().isoformat(),
+                "provider": "openai",
+                "model": model,
+                "base_url": base_url or "default",
+                "request_id": request_id,
+                "cache_hit": True,
+                "prompt_chars": len(prompt),
+                "response_chars": len(cached_response.get("return", "")),
+                "usage": cached_response.get("usage", {}),
+            })
             return cached_response["return"]
```

Sau API call:

```diff
 response = await openai_client.chat.completions.create(
     model=model, messages=messages, timeout=request_timeout, **kwargs
 )

 response_text = response.choices[0].message.content
+usage = _usage_to_dict(response)
+
+_append_usage_log({
+    "ts": datetime.now().isoformat(),
+    "provider": "openai",
+    "model": model,
+    "base_url": base_url or "default",
+    "request_id": request_id,
+    "cache_hit": False,
+    "prompt_chars": len(prompt),
+    "response_chars": len(response_text or ""),
+    "usage": usage,
+})
```

Lưu usage vào cache:

```diff
 if hashing_kv is not None:
     await hashing_kv.upsert(
-        {args_hash: {"return": response_text, "model": model}}
+        {args_hash: {"return": response_text, "model": model, "usage": usage}}
     )
     await hashing_kv.index_done_callback()
```

## Vì Sao Không Nên Đổi Return Type Ngay

Không nên đổi:

```python
return response_text
```

thành:

```python
return response_text, usage
```

vì các chỗ gọi LLM trong build/query có thể đang xử lý response như string. Đổi contract sẽ có rủi ro làm hỏng parsing entity extraction, summarization hoặc query answer generation.

Nếu muốn nối với `CostTracker`, nên làm ở bước riêng sau khi đã có JSONL usage ổn định.

## Test Usage Log Đề Xuất

Sau khi code thật được thêm, test smoke:

```bash
export TG_RAG_USAGE_LOG=logs/usage/smoke_usage.jsonl

python -u build_graph.py \
  --output_dir outputs/build_graph/smoke_usage_test \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --num_docs 2 \
  --llm_max_async 1 \
  --llm_timeout 600
```

Kiểm tra:

```bash
ls -lh logs/usage/smoke_usage.jsonl
head -n 3 logs/usage/smoke_usage.jsonl

python scripts/eval/summarize_usage.py \
  --usage_log logs/usage/smoke_usage.jsonl
```

Kỳ vọng:

- File JSONL có dòng mới.
- `summarize_usage.py` đọc được.
- `prompt_tokens`, `completion_tokens`, `total_tokens` có số nếu backend trả `response.usage`.
- Nếu llama-server không trả usage theo OpenAI schema, JSONL vẫn có `prompt_chars` và `response_chars`, nhưng token usage có thể rỗng.

---

# 3. Thứ Tự Nên Làm

Khuyến nghị thứ tự:

1. Giữ workflow `tee ${EXPORT_LOG}` cho export/import vì capture được cả shell, Docker, Neo4j.
2. Nếu muốn, thêm `--log_file` vào Python export script để log nội bộ chi tiết hơn.
3. Thêm producer `TG_RAG_USAGE_LOG` trong `openai_complete_if_cache` nhưng giữ return type là `str`.
4. Test `summarize_usage.py` với run nhỏ `--num_docs 2`.
5. Sau khi JSONL usage ổn định mới cân nhắc nối `CostTracker`.

---

# 4. Checklist Review Trước Khi Code

- Có chấp nhận ghi usage JSONL từ cả cache hit không?
- Có cần log `prompt_chars`/`response_chars` để fallback khi backend không trả token usage không?
- Có muốn lưu usage vào `kv_store_llm_response_cache.json` không?
- Có cần bật/tắt bằng env riêng ngoài `TG_RAG_USAGE_LOG` không?
- Có cần truncate prompt/response preview trong usage log không? Mặc định không nên ghi full prompt/response để tránh log quá lớn.
