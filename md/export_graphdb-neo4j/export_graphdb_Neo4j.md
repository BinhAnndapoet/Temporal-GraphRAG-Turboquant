# Temporal-GraphRAG → Neo4j Import Guide

README này mô tả quy trình đưa output của **Temporal-GraphRAG** vào **Neo4j** theo 4 giai đoạn:

1. Chuẩn bị thư mục và môi trường.
2. Tạo/kiểm tra script converter.
3. Export dữ liệu GraphRAG sang CSV/Cypher.
4. Khởi động Neo4j và import dữ liệu.

Phiên bản này đã được chỉnh lại theo lỗi thực tế đã gặp:

- `database_exports` bị đổi quyền thành `7474:7474` khi bind mount trực tiếp vào Neo4j container.
- Neo4j container bị `Exited (1)` khi mount `database_exports` dạng read-only `:ro` vì image Neo4j cố `chown` `/var/lib/neo4j/import`.
- Neo4j Browser mở được nhưng connect thất bại vì dùng sai Bolt port `7687` thay vì host-mapped port `17687`.
- User `guest` cần chạy độc lập bằng **rootless Docker**, không dùng system Docker của admin.

---

## 0. Mô hình chạy đúng

### Mục tiêu

User `guest` tự chạy toàn bộ workflow mà không cần admin `khoibui` sửa quyền sau mỗi lần chạy.

### Cách đúng sau khi fix

Không bind mount thư mục export vào Neo4j nữa. Thay vào đó:

```text
outputs/build_graph/<BUILD_CASE>/
        |
        v
export_temporal_graphrag_to_tables.py
        |
        +--> outputs/database_exports/<GRAPH_RUN_ID>/
        |
        +--> logs/graphdb_export/<GRAPH_RUN_ID>.log
        |
        | docker cp
        v
Neo4j container:/var/lib/neo4j/import/<GRAPH_RUN_ID>/
        |
        | cypher-shell -f neo4j_import.cypher
        v
Neo4j Graph Database
```

Quy ước mới: các package export mới nằm trong `outputs/database_exports/`. Folder root `database_exports/` chỉ còn là dữ liệu legacy nếu từng chạy theo hướng dẫn cũ; không cần xoá folder đó.

### Vì sao không bind mount trực tiếp?

Cách cũ:

```bash
-v "$(pwd)/database_exports:/var/lib/neo4j/import"
```

có thể làm Neo4j container thay đổi ownership/permission của thư mục host thành UID/GID nội bộ của Neo4j, ví dụ `7474:7474`. Khi đó user `guest` sẽ bị:

```bash
ls: cannot open directory 'database_exports': Permission denied
```

Cách read-only:

```bash
-v "$(pwd)/database_exports:/var/lib/neo4j/import:ro"
```

cũng không ổn với image Neo4j hiện tại, vì lúc startup Neo4j cố `chown` thư mục import và sẽ fail:

```text
chown: changing ownership of '/var/lib/neo4j/import/...': Read-only file system
```

Vì vậy workflow ổn định nhất là:

1. Start Neo4j container **không mount thư mục export**.
2. Dùng `docker cp` để copy CSV/Cypher vào container.
3. Import bằng `cypher-shell`.

---

## 1. Điều kiện trước khi chạy

Tất cả lệnh dưới đây chạy bằng user `guest`, tại thư mục project:

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant
```

### 1.1. Kiểm tra user hiện tại

```bash
whoami
id
```

Kết quả đúng:

```text
guest
uid=1001(guest) gid=1001(guest) groups=1001(guest),100(users),...
```

`guest` không cần nằm trong group `docker` của system Docker nữa nếu đã dùng rootless Docker.

### 1.2. Kiểm tra Docker rootless

```bash
echo "DOCKER_HOST=$DOCKER_HOST"
docker info | grep -Ei 'rootless|Docker Root Dir'
```

Kết quả đúng:

```text
DOCKER_HOST=unix:///run/user/1001/docker.sock
  rootless
Docker Root Dir: /home/guest/.local/share/docker
```

Giải thích:

- `DOCKER_HOST=unix:///run/user/1001/docker.sock`: Docker CLI của `guest` đang dùng socket riêng.
- `rootless`: Docker daemon chạy dưới user `guest`, không phải root/system daemon.
- `Docker Root Dir: /home/guest/.local/share/docker`: image/container/volume nằm trong home của `guest`, không dùng `/var/lib/docker`.

Nếu kết quả là:

```text
DOCKER_HOST=unix:///var/run/docker.sock
Docker Root Dir: /var/lib/docker
```

thì đang dùng nhầm system Docker. Cần logout/login lại user `guest`, hoặc kiểm tra lại `~/.bashrc`.

### 1.3. Kiểm tra output Temporal-GraphRAG

Giai đoạn export cần 3 file bắt buộc trong output build graph. Với luồng TurboQuant hiện tại, dùng `outputs/build_graph/<BUILD_CASE>` thay vì `output_ollama` ở root.

Ví dụ với run 7B p4 c64k:

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant

export BUILD_CASE=turboquant_384_qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096
export WORKING_DIR=outputs/build_graph/${BUILD_CASE}

ls -la ${WORKING_DIR}/graph_chunk_entity_relation.graphml
ls -la ${WORKING_DIR}/kv_store_full_docs.json
ls -la ${WORKING_DIR}/kv_store_text_chunks.json
```

Ý nghĩa:

| File | Vai trò |
|---|---|
| `graph_chunk_entity_relation.graphml` | Graph entity/relation đã build từ Temporal-GraphRAG |
| `kv_store_full_docs.json` | Full document store |
| `kv_store_text_chunks.json` | Text chunk store, dùng để tạo chunk node và provenance |

Nếu thiếu một trong ba file này, script export sẽ dừng với lỗi `FileNotFoundError`.


---

## 2. Xử lý thư mục legacy `database_exports` nếu từng bị lỗi quyền


> Luồng mới không ghi export vào root `database_exports/` nữa. Chỉ dùng phần này khi cần đọc/cứu dữ liệu cũ hoặc folder cũ đang bị lỗi quyền. Không xoá folder `database_exports` hiện có nếu còn cần đối chiếu kết quả cũ.

Chỉ cần làm phần này nếu gặp lỗi:

```bash
ls: cannot open directory 'database_exports': Permission denied
```

hoặc kiểm tra thấy:

```bash
drwx------ 3 7474 7474 ... database_exports
```

### 2.1. Kiểm tra quyền thư mục

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant

ls -ld database_exports
stat -c 'path=%n owner=%U uid=%u group=%G gid=%g perm=%A mode=%a' database_exports
```

Kết quả đúng phải là:

```text
owner=guest uid=1001 group=guest gid=1001
```

### 2.2. Quarantine folder hỏng rồi tạo lại folder sạch

Nếu thư mục cũ đang thuộc `7474:7474` và thật sự cần dùng lại tên `database_exports`, có thể quarantine bằng cách đổi tên. Thao tác này không xoá dữ liệu cũ, nhưng chỉ nên chạy khi cần cứu folder legacy:

```bash
BROKEN_DIR="database_exports_broken_7474_$(date +%Y%m%d_%H%M%S)"

mv database_exports "$BROKEN_DIR"

mkdir -p database_exports
chmod 700 database_exports
```

Giải thích:

- `mv database_exports "$BROKEN_DIR"`: đổi tên folder hỏng sang tên backup/quarantine.
- `mkdir -p database_exports`: tạo lại folder export sạch.
- `chmod 700 database_exports`: chỉ user `guest` được đọc/ghi/truy cập.

### 2.3. Test khả năng ghi

```bash
mkdir -p database_exports/test_write
touch database_exports/test_write/ok.txt
ls -la database_exports/test_write
rm -rf database_exports/test_write
```

Nếu tạo được `ok.txt`, user `guest` đã ghi được vào `database_exports`.

---

# Giai đoạn 1: Chuẩn bị thư mục và môi trường

## Mục tiêu

Tạo cấu trúc thư mục cần thiết và cài thư viện Python phục vụ export dữ liệu sang CSV.

## Input

- Project root: `~/Projects/Research/Temporal-GraphRAG-Turboquant`
- Python environment hiện tại, ví dụ `(turboquant)`
- Output build graph trong `outputs/build_graph/<BUILD_CASE>`

## Output

- Thư mục `scripts/graph_database/cypher`
- Thư mục `outputs/database_exports`
- Thư mục `logs/graphdb_export`
- File `requirements-graphdb.txt`
- Python packages: `networkx`, `pandas`

## Lệnh thực hiện

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant

echo "===== USER CHECK ====="
whoami
id

echo "===== DOCKER CHECK ====="
echo "DOCKER_HOST=$DOCKER_HOST"
docker info | grep -Ei 'rootless|Docker Root Dir'

echo "===== CREATE DIRS ====="
mkdir -p scripts/graph_database/cypher
mkdir -p outputs/database_exports
mkdir -p logs/graphdb_export

echo "===== CREATE REQUIREMENTS ====="
cat > requirements-graphdb.txt <<'EOF'
networkx>=3.0
pandas>=2.0.0
EOF

echo "===== INSTALL REQUIREMENTS ====="
pip install -r requirements-graphdb.txt

echo "===== VERIFY ====="
ls -ld scripts scripts/graph_database scripts/graph_database/cypher outputs outputs/database_exports logs logs/graphdb_export
cat requirements-graphdb.txt
```

## Giải thích lệnh

| Lệnh | Dùng để làm gì |
|---|---|
| `mkdir -p scripts/graph_database/cypher` | Tạo thư mục chứa script/cypher liên quan đến graph database |
| `mkdir -p outputs/database_exports` | Tạo thư mục lưu CSV, Cypher và manifest export cho các lần chạy mới |
| `mkdir -p logs/graphdb_export` | Tạo thư mục lưu log export/import để debug từng bước |
| `cat > requirements-graphdb.txt` | Tạo file khai báo thư viện cần cài |
| `pip install -r requirements-graphdb.txt` | Cài `networkx` để đọc GraphML và `pandas` để ghi CSV |
| `ls -ld ...` | Kiểm tra thư mục đã tạo và quyền owner |
| `docker info ...` | Kiểm tra đang dùng Docker rootless của `guest` |

## Kiểm tra giai đoạn 1 đã đúng chưa

Chạy:

```bash
ls -ld outputs/database_exports logs/graphdb_export
stat -c 'path=%n owner=%U uid=%u group=%G gid=%g perm=%A mode=%a' outputs/database_exports logs/graphdb_export

python - <<'PY'
import networkx as nx
import pandas as pd
print("networkx:", nx.__version__)
print("pandas:", pd.__version__)
PY
```

Kết quả mong muốn:

```text
owner=guest uid=1001 group=guest gid=1001
networkx: ...
pandas: ...
```


---

# Giai đoạn 2: Viết hoặc kiểm tra Script Converter

## Mục tiêu

Tạo script:

```text
scripts/graph_database/export_temporal_graphrag_to_tables.py
```

Script này đọc output Temporal-GraphRAG gồm GraphML và JSON, rồi tạo các file CSV/Cypher để import vào Neo4j.

## Input

Trong `outputs/build_graph/<BUILD_CASE>` cần có:

```text
graph_chunk_entity_relation.graphml
kv_store_full_docs.json
kv_store_text_chunks.json
```

## Output

Trong `outputs/database_exports/<GRAPH_RUN_ID>/` sẽ tạo:

```text
docs.csv
chunks.csv
entity_nodes.csv
entity_relationships.csv
node_chunk_links.csv
neo4j_import.cypher
manifest.json
```

## Tạo script nếu chưa có

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant

mkdir -p scripts/graph_database

cat > scripts/graph_database/export_temporal_graphrag_to_tables.py <<'PY'
import argparse
import json
import networkx as nx
import pandas as pd
from pathlib import Path
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description="Export Temporal-GraphRAG output to CSV for Neo4j")
    parser.add_argument("--working_dir", required=True, help="Folder output graph đã build, ví dụ ./outputs/build_graph/<BUILD_CASE>")
    parser.add_argument("--export_dir", required=True, help="Folder lưu CSV/Cypher export")
    parser.add_argument("--graph_run_id", required=True, help="ID định danh cho lần export/import này")
    parser.add_argument("--overwrite", action="store_true", help="Ghi đè nếu folder export đã tồn tại")
    return parser.parse_args()

def safe_load_json(path: Path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def main():
    args = parse_args()
    work_dir = Path(args.working_dir)
    export_dir = Path(args.export_dir)

    # 1. Validate input
    req_files = [
        "graph_chunk_entity_relation.graphml",
        "kv_store_full_docs.json",
        "kv_store_text_chunks.json",
    ]

    for f in req_files:
        if not (work_dir / f).exists():
            raise FileNotFoundError(f"[Error] Thiếu file bắt buộc: {work_dir / f}")

    if export_dir.exists() and not args.overwrite:
        raise FileExistsError(f"Folder {export_dir} đã tồn tại. Dùng --overwrite để ghi đè.")

    export_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Đang đọc dữ liệu từ: {work_dir}")

    # 2. Read GraphML and JSON
    entity_graph = nx.read_graphml(work_dir / "graph_chunk_entity_relation.graphml")
    full_docs = safe_load_json(work_dir / "kv_store_full_docs.json")
    text_chunks = safe_load_json(work_dir / "kv_store_text_chunks.json")

    # 3. Build CSV tables

    # 3.1. Documents
    docs_data = [
        {
            "graph_run_id": args.graph_run_id,
            "id": str(k),
            "title": f"Doc {k}",
            "doc": str(v),
        }
        for k, v in full_docs.items()
    ]

    # 3.2. Chunks
    chunks_data = [
        {
            "graph_run_id": args.graph_run_id,
            "id": str(k),
            "full_doc_id": str(v.get("full_doc_id", "doc_0")),
            "tokens": int(v.get("tokens", 0)),
            "content": v.get("content", ""),
        }
        for k, v in text_chunks.items()
    ]

    # 3.3. Entity nodes and node-chunk provenance links
    nodes_data = []
    node_chunk_links = []

    for node_id, data in entity_graph.nodes(data=True):
        node_id_str = str(node_id)

        nodes_data.append(
            {
                "graph_run_id": args.graph_run_id,
                "id": node_id_str,
                "name": data.get("id", node_id_str),
                "entity_type": data.get("entity_type", "UNKNOWN"),
                "description": data.get("description", ""),
                "source_id": data.get("source_id", ""),
            }
        )

        sources = str(data.get("source_id", "")).split("<SEP>")
        for src in sources:
            src = src.strip()
            if src:
                node_chunk_links.append(
                    {
                        "graph_run_id": args.graph_run_id,
                        "node_id": node_id_str,
                        "chunk_id": src,
                    }
                )

    # 3.4. Entity relationships
    edges_data = []

    for u, v, data in entity_graph.edges(data=True):
        edges_data.append(
            {
                "graph_run_id": args.graph_run_id,
                "source_id": str(u),
                "target_id": str(v),
                "relationship_type": "RELATED",
                "description_json": data.get("description", ""),
                "source_id_json": data.get("source_id", ""),
            }
        )

    # 4. Write CSV files
    print(f"[*] Đang ghi CSV ra: {export_dir}")

    pd.DataFrame(docs_data).to_csv(export_dir / "docs.csv", index=False)
    pd.DataFrame(chunks_data).to_csv(export_dir / "chunks.csv", index=False)
    pd.DataFrame(nodes_data).to_csv(export_dir / "entity_nodes.csv", index=False)
    pd.DataFrame(edges_data).to_csv(export_dir / "entity_relationships.csv", index=False)
    pd.DataFrame(node_chunk_links).to_csv(export_dir / "node_chunk_links.csv", index=False)

    # 5. Write Neo4j import Cypher
    cypher_script = f"""// 1. Constraints
CREATE CONSTRAINT tgrag_entity_key IF NOT EXISTS FOR (n:TGRAGEntity) REQUIRE (n.graph_run_id, n.id) IS UNIQUE;

// 2. Load Docs
LOAD CSV WITH HEADERS FROM 'file:///{args.graph_run_id}/docs.csv' AS row
MERGE (d:TGRAGDocument {{graph_run_id: row.graph_run_id, id: row.id}})
SET d.title = row.title, d.doc = row.doc;

// 3. Load Chunks and Link to Docs
LOAD CSV WITH HEADERS FROM 'file:///{args.graph_run_id}/chunks.csv' AS row
MERGE (c:TGRAGChunk {{graph_run_id: row.graph_run_id, id: row.id}})
SET c.content = row.content,
    c.tokens = toInteger(row.tokens),
    c.full_doc_id = row.full_doc_id
WITH row, c
MATCH (d:TGRAGDocument {{graph_run_id: row.graph_run_id, id: row.full_doc_id}})
MERGE (d)-[:HAS_CHUNK]->(c);

// 4. Load Entity Nodes
LOAD CSV WITH HEADERS FROM 'file:///{args.graph_run_id}/entity_nodes.csv' AS row
MERGE (e:TGRAGEntity {{graph_run_id: row.graph_run_id, id: row.id}})
SET e.name = row.name,
    e.entity_type = row.entity_type,
    e.description = row.description;

// 5. Load Entity Relationships
LOAD CSV WITH HEADERS FROM 'file:///{args.graph_run_id}/entity_relationships.csv' AS row
MATCH (s:TGRAGEntity {{graph_run_id: row.graph_run_id, id: row.source_id}})
MATCH (t:TGRAGEntity {{graph_run_id: row.graph_run_id, id: row.target_id}})
MERGE (s)-[r:RELATED {{graph_run_id: row.graph_run_id, source_id: row.source_id, target_id: row.target_id}}]->(t)
SET r.description_json = row.description_json;

// 6. Link Entity to Chunk, also known as provenance
LOAD CSV WITH HEADERS FROM 'file:///{args.graph_run_id}/node_chunk_links.csv' AS row
MATCH (e:TGRAGEntity {{graph_run_id: row.graph_run_id, id: row.node_id}})
MATCH (c:TGRAGChunk {{graph_run_id: row.graph_run_id, id: row.chunk_id}})
MERGE (e)-[:MENTIONED_IN]->(c);
"""

    with open(export_dir / "neo4j_import.cypher", "w", encoding="utf-8") as f:
        f.write(cypher_script)

    # 6. Write manifest
    manifest = {
        "graph_run_id": args.graph_run_id,
        "generated_at": datetime.now().isoformat(),
        "counts": {
            "docs": len(docs_data),
            "chunks": len(chunks_data),
            "entity_nodes": len(nodes_data),
            "entity_relationships": len(edges_data),
            "node_chunk_links": len(node_chunk_links),
        },
    }

    with open(export_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4, ensure_ascii=False)

    print("[Success] Export thành công! Đã tạo manifest.json và neo4j_import.cypher.")

if __name__ == "__main__":
    main()
PY
```

## Giải thích script

| Thành phần | Chức năng |
|---|---|
| `argparse` | Nhận tham số CLI: `--working_dir`, `--export_dir`, `--graph_run_id`, `--overwrite` |
| `networkx.read_graphml()` | Đọc entity/relation graph từ GraphML |
| `safe_load_json()` | Đọc JSON nếu tồn tại, tránh lỗi khi file rỗng/thiếu |
| `docs.csv` | Bảng document node |
| `chunks.csv` | Bảng chunk node |
| `entity_nodes.csv` | Bảng entity node |
| `entity_relationships.csv` | Bảng relationship giữa entity |
| `node_chunk_links.csv` | Bảng provenance: entity được nhắc trong chunk nào |
| `neo4j_import.cypher` | Script `LOAD CSV` để import vào Neo4j |
| `manifest.json` | File thống kê số lượng record đã export |

## Kiểm tra script

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant

export BUILD_CASE=turboquant_384_qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096
export WORKING_DIR=outputs/build_graph/${BUILD_CASE}

echo "===== SCRIPT CHECK ====="
ls -la scripts/graph_database/export_temporal_graphrag_to_tables.py

echo "===== SYNTAX CHECK ====="
python -m py_compile scripts/graph_database/export_temporal_graphrag_to_tables.py

echo "===== REQUIRED INPUT FILES CHECK ====="
ls -la ${WORKING_DIR}/graph_chunk_entity_relation.graphml
ls -la ${WORKING_DIR}/kv_store_full_docs.json
ls -la ${WORKING_DIR}/kv_store_text_chunks.json
```

Nếu `python -m py_compile` không in lỗi gì và 3 file input tồn tại, script hợp lệ.

---

# Giai đoạn 3: Chạy export dữ liệu

## Mục tiêu

Chạy script converter để tạo CSV/Cypher import package cho Neo4j và ghi log từng bước để dễ kiểm tra lại.

## Input

- `outputs/build_graph/<BUILD_CASE>/graph_chunk_entity_relation.graphml`
- `outputs/build_graph/<BUILD_CASE>/kv_store_full_docs.json`
- `outputs/build_graph/<BUILD_CASE>/kv_store_text_chunks.json`

## Output

Một folder export mới:

```text
outputs/database_exports/<GRAPH_RUN_ID>/
```

Một file log tương ứng:

```text
logs/graphdb_export/<GRAPH_RUN_ID>.log
```

Bên trong export folder có:

```text
chunks.csv
docs.csv
entity_nodes.csv
entity_relationships.csv
manifest.json
neo4j_import.cypher
node_chunk_links.csv
```

## Lệnh export

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant

set -euo pipefail

export BUILD_CASE=turboquant_384_qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096
export WORKING_DIR=outputs/build_graph/${BUILD_CASE}

RUN_ID=$(date +%Y%m%d_%H%M%S)
export GRAPH_RUN_ID="${BUILD_CASE}_neo4j_${RUN_ID}"
export EXPORT_ROOT=outputs/database_exports
export EXPORT_DIR=${EXPORT_ROOT}/${GRAPH_RUN_ID}
export EXPORT_LOG=logs/graphdb_export/${GRAPH_RUN_ID}.log

mkdir -p ${EXPORT_ROOT} logs/graphdb_export
echo "${GRAPH_RUN_ID}" > .last_graph_run_id

{
  echo "===== GRAPH_RUN_ID ====="
  echo "GRAPH_RUN_ID=${GRAPH_RUN_ID}"
  echo "WORKING_DIR=${WORKING_DIR}"
  echo "EXPORT_DIR=${EXPORT_DIR}"
  echo "EXPORT_LOG=${EXPORT_LOG}"

  echo
  echo "===== PRE-EXPORT INPUT CHECK ====="
  ls -la ${WORKING_DIR}/graph_chunk_entity_relation.graphml
  ls -la ${WORKING_DIR}/kv_store_full_docs.json
  ls -la ${WORKING_DIR}/kv_store_text_chunks.json

  echo
  echo "===== PRE-EXPORT DIR CHECK ====="
  stat -c 'path=%n owner=%U uid=%u group=%G gid=%g perm=%A mode=%a' ${EXPORT_ROOT} logs/graphdb_export

  echo
  echo "===== RUN EXPORT SCRIPT ====="
  python scripts/graph_database/export_temporal_graphrag_to_tables.py \
    --working_dir ${WORKING_DIR} \
    --export_dir ${EXPORT_DIR} \
    --graph_run_id ${GRAPH_RUN_ID} \
    --overwrite

  echo
  echo "===== VERIFY EXPORT OUTPUT ====="
  ls -la ${EXPORT_DIR}

  echo
  echo "===== MANIFEST ====="
  cat ${EXPORT_DIR}/manifest.json
} 2>&1 | tee ${EXPORT_LOG}
```

## Giải thích lệnh

| Lệnh | Dùng để làm gì |
|---|---|
| `BUILD_CASE=...` | Tên output build graph đã chạy, thường trùng model/parallel/context để dễ truy vết |
| `WORKING_DIR=outputs/build_graph/${BUILD_CASE}` | Nơi chứa output Temporal-GraphRAG cần export |
| `GRAPH_RUN_ID="${BUILD_CASE}_neo4j_${RUN_ID}"` | Định danh lần export/import, có cả build case và timestamp |
| `EXPORT_DIR=outputs/database_exports/${GRAPH_RUN_ID}` | Nơi ghi package export mới |
| `EXPORT_LOG=logs/graphdb_export/${GRAPH_RUN_ID}.log` | Nơi ghi log export/import để debug |
| `echo "${GRAPH_RUN_ID}" > .last_graph_run_id` | Lưu run id mới nhất để Giai đoạn 4 dùng lại |
| `--graph_run_id ${GRAPH_RUN_ID}` | Gắn run id vào từng row CSV để phân biệt các lần chạy |
| `--overwrite` | Cho phép ghi đè nếu folder export đã tồn tại |
| `2>&1 | tee ${EXPORT_LOG}` | Vừa hiển thị terminal vừa lưu log |

Log là cần thiết ở giai đoạn này vì export/import có nhiều bước rời nhau: kiểm tra input, ghi CSV, copy vào container, rồi import Cypher. Khi lỗi, file `logs/graphdb_export/<GRAPH_RUN_ID>.log` giúp biết lỗi xảy ra ở bước nào mà không cần đoán từ terminal scrollback.

## Kiểm tra giai đoạn 3 đã đúng chưa

```bash
GRAPH_RUN_ID=$(cat .last_graph_run_id)
EXPORT_DIR=outputs/database_exports/${GRAPH_RUN_ID}
EXPORT_LOG=logs/graphdb_export/${GRAPH_RUN_ID}.log

ls -la ${EXPORT_DIR}
cat ${EXPORT_DIR}/manifest.json
ls -lh ${EXPORT_LOG}
```

Kết quả cần có đủ:

```text
docs.csv
chunks.csv
entity_nodes.csv
entity_relationships.csv
node_chunk_links.csv
neo4j_import.cypher
manifest.json
```

Ví dụ manifest thành công:

```json
{
  "graph_run_id": "turboquant_384_qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096_neo4j_20260522_021500",
  "generated_at": "2026-05-22T02:15:00.833583",
  "counts": {
    "docs": 384,
    "chunks": 1462,
    "entity_nodes": 12345,
    "entity_relationships": 6789,
    "node_chunk_links": 17000
  }
}
```


---

# Giai đoạn 4: Khởi động Neo4j và import dữ liệu

## Mục tiêu

Chạy Neo4j bằng Docker rootless của `guest`, copy export package vào container, rồi import dữ liệu bằng `cypher-shell`.

## Input

- `outputs/database_exports/<GRAPH_RUN_ID>/neo4j_import.cypher`
- Các file CSV trong cùng folder
- Log tiếp tục ghi vào `logs/graphdb_export/<GRAPH_RUN_ID>.log`

## Output

Neo4j database có các node/relationship:

| Label/Relationship | Ý nghĩa |
|---|---|
| `TGRAGDocument` | Document gốc |
| `TGRAGChunk` | Chunk văn bản |
| `TGRAGEntity` | Entity được trích xuất |
| `HAS_CHUNK` | Document chứa chunk |
| `RELATED` | Quan hệ giữa entity |
| `MENTIONED_IN` | Entity được nhắc trong chunk nào |

## Lưu ý quan trọng

Không dùng lệnh cũ này nữa:

```bash
docker run -d \
  --name tgrag-neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/tgrag-local-2026 \
  -v "$(pwd)/database_exports:/var/lib/neo4j/import" \
  neo4j:5-community
```

Lý do:

- Bind mount có thể làm hỏng quyền `database_exports` trên host.
- Mount `:ro` làm Neo4j startup fail vì image cố `chown` thư mục import.
- Cách an toàn là start Neo4j không mount, sau đó dùng `docker cp`.

## 4.1. Xóa container cũ nếu có

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant

docker rm -f tgrag-neo4j 2>/dev/null || true
```

Giải thích:

- Xóa container cũ để tránh trùng tên `tgrag-neo4j`.
- Chỉ xóa container trong Docker rootless của `guest`, không đụng system Docker của admin.

## 4.2. Chạy Neo4j container

```bash
docker run -d \
  --name tgrag-neo4j \
  -p 17474:7474 \
  -p 17687:7687 \
  -e NEO4J_AUTH=neo4j/tgrag-local-2026 \
  neo4j:5-community
```

Giải thích port:

| Host port | Container port | Dùng để làm gì |
|---:|---:|---|
| `17474` | `7474` | Neo4j Browser HTTP UI |
| `17687` | `7687` | Bolt connection protocol |

Không dùng host port `7474/7687` để tránh đụng container/system service cũ.

## 4.3. Kiểm tra container và log

```bash
docker ps -a --filter name=tgrag-neo4j
docker logs --tail 80 tgrag-neo4j
```

Kết quả đúng:

```text
STATUS: Up ...
HTTP enabled on 0.0.0.0:7474
Bolt enabled on 0.0.0.0:7687
Started.
```

## 4.4. Đợi Neo4j sẵn sàng

Dùng block này thay vì chỉ `sleep 20`, vì nó kiểm tra thật bằng `cypher-shell`:

```bash
until docker exec tgrag-neo4j cypher-shell -u neo4j -p tgrag-local-2026 "RETURN 1;" >/dev/null 2>&1; do
  if [ "$(docker inspect -f '{{.State.Running}}' tgrag-neo4j)" != "true" ]; then
    echo "Neo4j container stopped. Logs:"
    docker logs --tail 120 tgrag-neo4j
    exit 1
  fi

  echo "Waiting for Neo4j..."
  sleep 2
done

echo "Neo4j is ready"
```

Giải thích:

- `cypher-shell "RETURN 1;"`: kiểm tra database đã nhận query chưa.
- `docker inspect -f '{{.State.Running}}'`: nếu container chết thì in log và dừng.
- Tránh lỗi `Ctrl+C` rồi shell vẫn in `Neo4j is ready` giả.

## 4.5. Copy file export vào container

```bash
GRAPH_RUN_ID=$(cat .last_graph_run_id)
EXPORT_DIR=outputs/database_exports/${GRAPH_RUN_ID}
EXPORT_LOG=logs/graphdb_export/${GRAPH_RUN_ID}.log

echo "GRAPH_RUN_ID=${GRAPH_RUN_ID}"
echo "EXPORT_DIR=${EXPORT_DIR}"

{
  echo "===== COPY EXPORT INTO CONTAINER ====="
  docker exec tgrag-neo4j mkdir -p /var/lib/neo4j/import/${GRAPH_RUN_ID}

  docker cp ${EXPORT_DIR}/. \
    tgrag-neo4j:/var/lib/neo4j/import/${GRAPH_RUN_ID}/

  docker exec tgrag-neo4j ls -la /var/lib/neo4j/import/${GRAPH_RUN_ID}
} 2>&1 | tee -a ${EXPORT_LOG}
```

Giải thích:

| Lệnh | Dùng để làm gì |
|---|---|
| `GRAPH_RUN_ID=$(cat .last_graph_run_id)` | Lấy lại run id mới nhất từ Giai đoạn 3 |
| `EXPORT_DIR=outputs/database_exports/${GRAPH_RUN_ID}` | Trỏ đúng package export mới trong `outputs/` |
| `docker exec ... mkdir -p` | Tạo thư mục import bên trong container |
| `docker cp ${EXPORT_DIR}/.` | Copy CSV/Cypher từ host vào container |
| `docker exec ... ls -la` | Kiểm tra file đã vào container chưa |
| `tee -a ${EXPORT_LOG}` | Ghi tiếp log copy vào cùng log export |


## 4.6. Import dữ liệu bằng Cypher Shell

```bash
GRAPH_RUN_ID=$(cat .last_graph_run_id)
EXPORT_LOG=logs/graphdb_export/${GRAPH_RUN_ID}.log

{
  echo "===== IMPORT CYPHER ====="
  docker exec -i tgrag-neo4j \
    cypher-shell -u neo4j -p tgrag-local-2026 \
    -f /var/lib/neo4j/import/${GRAPH_RUN_ID}/neo4j_import.cypher
} 2>&1 | tee -a ${EXPORT_LOG}
```

Giải thích:

- `docker exec -i tgrag-neo4j`: chạy lệnh bên trong container Neo4j.
- `cypher-shell`: CLI của Neo4j để chạy Cypher.
- `-u neo4j -p tgrag-local-2026`: thông tin đăng nhập Neo4j.
- `-f .../neo4j_import.cypher`: chạy toàn bộ script import đã tạo ở Giai đoạn 3.
- `tee -a ${EXPORT_LOG}`: ghi tiếp log import vào cùng file log export.

Nếu lệnh này không in lỗi, import đã chạy xong.


## 4.7. Kiểm tra dữ liệu đã import

```bash
GRAPH_RUN_ID=$(cat .last_graph_run_id)
EXPORT_LOG=logs/graphdb_export/${GRAPH_RUN_ID}.log

{
  echo "===== CHECK COUNTS ====="
  docker exec -i tgrag-neo4j \
    cypher-shell -u neo4j -p tgrag-local-2026 \
    "MATCH (n:TGRAGEntity {graph_run_id: '${GRAPH_RUN_ID}'}) RETURN count(n) AS entity_count;"

  docker exec -i tgrag-neo4j \
    cypher-shell -u neo4j -p tgrag-local-2026 \
    "MATCH (:TGRAGEntity {graph_run_id: '${GRAPH_RUN_ID}'})-[r:RELATED {graph_run_id: '${GRAPH_RUN_ID}'}]->(:TGRAGEntity {graph_run_id: '${GRAPH_RUN_ID}'}) RETURN count(r) AS related_count;"

  docker exec -i tgrag-neo4j \
    cypher-shell -u neo4j -p tgrag-local-2026 \
    "MATCH (c:TGRAGChunk {graph_run_id: '${GRAPH_RUN_ID}'}) RETURN count(c) AS chunk_count;"
} 2>&1 | tee -a ${EXPORT_LOG}
```

Kết quả mong muốn khớp hoặc gần khớp với `manifest.json`. Ví dụ:

```text
entity_count
133

related_count
128

chunk_count
5
```

---

# Mở Neo4j Browser qua Tailscale hoặc SSH Tunnel

## 1. Port mapping cần nhớ

Khi chạy container bằng lệnh:

```bash
-p 17474:7474
-p 17687:7687
```

nghĩa là:

| Thành phần | Trong container | Trên server/Tailscale |
|---|---:|---:|
| Neo4j Browser HTTP | `7474` | `17474` |
| Neo4j Bolt | `7687` | `17687` |

Do đó:

- Mở web UI bằng `http://<server-ip>:17474`
- Connect database bằng `neo4j://<server-ip>:17687`

Không dùng `neo4j://<server-ip>:7687` nếu container đang map host port là `17687`.

## 2. Mở qua Tailscale IP

Trên server, lấy Tailscale IP:

```bash
tailscale ip -4
```

Ví dụ:

```text
100.69.255.87
```

Trên máy Windows, mở trình duyệt:

```text
http://100.69.255.87:17474
```

Trong màn hình Neo4j Browser, connection URL nhập:

```text
neo4j://100.69.255.87:17687
```

Credentials:

```text
Username: neo4j
Password: tgrag-local-2026
```

## 3. Kiểm tra port từ Windows

Trong PowerShell:

```powershell
Test-NetConnection 100.69.255.87 -Port 17474
Test-NetConnection 100.69.255.87 -Port 17687
```

Kết quả đúng:

```text
TcpTestSucceeded : True
```

Nếu `17474=True` nhưng `17687=False`, web UI có thể mở nhưng login/connect sẽ fail vì Bolt port bị chặn.

## 4. Mở bằng SSH tunnel nếu Tailscale/Firewall chặn port

Trên Windows PowerShell, chạy:

```powershell
ssh -N -L 17474:127.0.0.1:17474 -L 17687:127.0.0.1:17687 guest-ubuntu
```

Cửa sổ này đứng yên là đúng. Sau đó mở browser:

```text
http://localhost:17474
```

Trong Neo4j Browser, connection URL nhập:

```text
neo4j://localhost:17687
```

Credentials:

```text
Username: neo4j
Password: tgrag-local-2026
```

Giải thích:

- `-L 17474:127.0.0.1:17474`: forward local port `17474` trên Windows đến port `17474` trên Ubuntu server.
- `-L 17687:127.0.0.1:17687`: forward local Bolt port `17687` đến server.
- Browser Windows truy cập `localhost`, nhưng traffic đi qua SSH tunnel đến server.

---

# Query trực quan hóa trong Neo4j Browser

## Xem graph entity relationship

```cypher
MATCH p=(n:TGRAGEntity)-[r:RELATED]-(m:TGRAGEntity)
RETURN p
LIMIT 100;
```

## Xem entity được trích xuất từ chunk nào

```cypher
MATCH p=(e:TGRAGEntity)-[:MENTIONED_IN]->(c:TGRAGChunk)
RETURN p
LIMIT 50;
```

## Xem document và chunk

```cypher
MATCH p=(d:TGRAGDocument)-[:HAS_CHUNK]->(c:TGRAGChunk)
RETURN p
LIMIT 50;
```

## Xem thống kê nhanh

```cypher
MATCH (e:TGRAGEntity)
RETURN e.entity_type AS entity_type, count(*) AS count
ORDER BY count DESC;
```

---

# Troubleshooting

## Lỗi 1: `database_exports: Permission denied`

### Triệu chứng

```bash
ls -la database_exports
# ls: cannot open directory 'database_exports': Permission denied
```

hoặc:

```bash
drwx------ 3 7474 7474 ... database_exports
```

### Nguyên nhân

Thư mục `database_exports` từng bị container Neo4j/system Docker đổi owner sang UID/GID nội bộ, ví dụ `7474:7474`.

### Cách xử lý không cần admin

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant

BROKEN_DIR="database_exports_broken_7474_$(date +%Y%m%d_%H%M%S)"

mv database_exports "$BROKEN_DIR"

mkdir -p database_exports
chmod 700 database_exports
```

Kiểm tra:

```bash
stat -c 'path=%n owner=%U uid=%u group=%G gid=%g perm=%A mode=%a' database_exports
```

Kết quả đúng:

```text
owner=guest uid=1001 group=guest gid=1001
```

---

## Lỗi 2: Neo4j container `Exited (1)` với `Read-only file system`

### Triệu chứng

```bash
docker ps -a --filter name=tgrag-neo4j
# Exited (1)
```

```bash
docker logs --tail 200 tgrag-neo4j
# chown: changing ownership of '/var/lib/neo4j/import/...': Read-only file system
```

### Nguyên nhân

Đã mount `database_exports` vào container dạng read-only:

```bash
-v "$(pwd)/database_exports:/var/lib/neo4j/import:ro"
```

Image Neo4j cố `chown` thư mục import khi startup nên fail.

### Cách xử lý

Không mount. Chạy Neo4j không volume rồi dùng `docker cp`:

```bash
docker rm -f tgrag-neo4j 2>/dev/null || true

docker run -d \
  --name tgrag-neo4j \
  -p 17474:7474 \
  -p 17687:7687 \
  -e NEO4J_AUTH=neo4j/tgrag-local-2026 \
  neo4j:5-community
```

Sau đó copy file:

```bash
GRAPH_RUN_ID=$(cat .last_graph_run_id)
EXPORT_DIR=outputs/database_exports/${GRAPH_RUN_ID}

docker exec tgrag-neo4j mkdir -p /var/lib/neo4j/import/${GRAPH_RUN_ID}

docker cp ${EXPORT_DIR}/. \
  tgrag-neo4j:/var/lib/neo4j/import/${GRAPH_RUN_ID}/
```

---

## Lỗi 3: Neo4j Browser mở được nhưng connect instance failed

### Triệu chứng

Neo4j Browser báo:

```text
Connection to instance failed
```

URL connection đang là:

```text
neo4j://<tailscale-ip>:7687
```

### Nguyên nhân

Bạn đang dùng sai host Bolt port. Container map:

```bash
-p 17687:7687
```

Nên từ ngoài server phải connect qua port `17687`, không phải `7687`.

### Cách xử lý

Dùng:

```text
neo4j://<tailscale-ip>:17687
```

Ví dụ:

```text
neo4j://100.69.255.87:17687
```

---

## Lỗi 4: `GRAPH_RUN_ID` bị rỗng

### Triệu chứng

```bash
echo "$GRAPH_RUN_ID"
# không in gì
```

hoặc import path sai:

```text
/var/lib/neo4j/import//neo4j_import.cypher
```

### Nguyên nhân

Biến shell chỉ tồn tại trong session hiện tại. Nếu mở terminal mới, biến bị mất.

### Cách xử lý

Luôn lưu và đọc lại run id:

```bash
echo "$GRAPH_RUN_ID" > .last_graph_run_id
GRAPH_RUN_ID=$(cat .last_graph_run_id)
```

Hoặc lấy run mới nhất:

```bash
GRAPH_RUN_ID=$(basename "$(ls -td outputs/database_exports/*_neo4j_* | head -1)")
echo "$GRAPH_RUN_ID" > .last_graph_run_id
```

---

## Lỗi 5: Docker đang dùng nhầm system daemon

### Triệu chứng

```bash
docker info | grep -Ei 'rootless|Docker Root Dir'
```

ra:

```text
Docker Root Dir: /var/lib/docker
```

### Nguyên nhân

`guest` đang dùng system Docker qua `/var/run/docker.sock`, không phải rootless Docker.

### Cách xử lý

Kiểm tra `~/.bashrc` có:

```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock
```

Reload:

```bash
source ~/.bashrc
```

Kiểm tra lại:

```bash
echo "$DOCKER_HOST"
docker info | grep -Ei 'rootless|Docker Root Dir'
```

Kết quả đúng:

```text
DOCKER_HOST=unix:///run/user/1001/docker.sock
rootless
Docker Root Dir: /home/guest/.local/share/docker
```

---

# One-command workflow sau khi setup xong

Sau khi Giai đoạn 1 và 2 đã ổn, có thể chạy nhanh toàn bộ export + Neo4j import bằng block sau. Lệnh này dùng `outputs/database_exports/` cho export mới và ghi log vào `logs/graphdb_export/`.

```bash
cd ~/Projects/Research/Temporal-GraphRAG-Turboquant

set -euo pipefail

export BUILD_CASE=turboquant_384_qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096
export WORKING_DIR=outputs/build_graph/${BUILD_CASE}

RUN_ID=$(date +%Y%m%d_%H%M%S)
export GRAPH_RUN_ID="${BUILD_CASE}_neo4j_${RUN_ID}"
export EXPORT_ROOT=outputs/database_exports
export EXPORT_DIR=${EXPORT_ROOT}/${GRAPH_RUN_ID}
export EXPORT_LOG=logs/graphdb_export/${GRAPH_RUN_ID}.log

mkdir -p ${EXPORT_ROOT} logs/graphdb_export
echo "${GRAPH_RUN_ID}" > .last_graph_run_id

{
  echo "===== CHECK ROOTLESS DOCKER ====="
  echo "DOCKER_HOST=$DOCKER_HOST"
  docker info | grep -Ei 'rootless|Docker Root Dir'

  echo
  echo "===== PRE-EXPORT INPUT CHECK ====="
  ls -la ${WORKING_DIR}/graph_chunk_entity_relation.graphml
  ls -la ${WORKING_DIR}/kv_store_full_docs.json
  ls -la ${WORKING_DIR}/kv_store_text_chunks.json

  echo
  echo "===== EXPORT ====="
  python scripts/graph_database/export_temporal_graphrag_to_tables.py \
    --working_dir ${WORKING_DIR} \
    --export_dir ${EXPORT_DIR} \
    --graph_run_id ${GRAPH_RUN_ID} \
    --overwrite

  echo
  echo "===== MANIFEST ====="
  cat ${EXPORT_DIR}/manifest.json

  echo
  echo "===== START NEO4J ====="
  docker rm -f tgrag-neo4j 2>/dev/null || true

  docker run -d \
    --name tgrag-neo4j \
    -p 17474:7474 \
    -p 17687:7687 \
    -e NEO4J_AUTH=neo4j/tgrag-local-2026 \
    neo4j:5-community

  echo
  echo "===== WAIT NEO4J ====="
  until docker exec tgrag-neo4j cypher-shell -u neo4j -p tgrag-local-2026 "RETURN 1;" >/dev/null 2>&1; do
    if [ "$(docker inspect -f '{{.State.Running}}' tgrag-neo4j)" != "true" ]; then
      echo "Neo4j container stopped. Logs:"
      docker logs --tail 120 tgrag-neo4j
      exit 1
    fi
    echo "Waiting for Neo4j..."
    sleep 2
  done

  echo
  echo "===== COPY EXPORT INTO CONTAINER ====="
  docker exec tgrag-neo4j mkdir -p /var/lib/neo4j/import/${GRAPH_RUN_ID}

  docker cp ${EXPORT_DIR}/. \
    tgrag-neo4j:/var/lib/neo4j/import/${GRAPH_RUN_ID}/

  docker exec tgrag-neo4j ls -la /var/lib/neo4j/import/${GRAPH_RUN_ID}

  echo
  echo "===== IMPORT ====="
  docker exec -i tgrag-neo4j \
    cypher-shell -u neo4j -p tgrag-local-2026 \
    -f /var/lib/neo4j/import/${GRAPH_RUN_ID}/neo4j_import.cypher

  echo
  echo "===== CHECK COUNTS ====="
  docker exec -i tgrag-neo4j \
    cypher-shell -u neo4j -p tgrag-local-2026 \
    "MATCH (n:TGRAGEntity {graph_run_id: '${GRAPH_RUN_ID}'}) RETURN count(n) AS entity_count;"

  docker exec -i tgrag-neo4j \
    cypher-shell -u neo4j -p tgrag-local-2026 \
    "MATCH (:TGRAGEntity {graph_run_id: '${GRAPH_RUN_ID}'})-[r:RELATED {graph_run_id: '${GRAPH_RUN_ID}'}]->(:TGRAGEntity {graph_run_id: '${GRAPH_RUN_ID}'}) RETURN count(r) AS related_count;"

  docker exec -i tgrag-neo4j \
    cypher-shell -u neo4j -p tgrag-local-2026 \
    "MATCH (c:TGRAGChunk {graph_run_id: '${GRAPH_RUN_ID}'}) RETURN count(c) AS chunk_count;"

  echo
  echo "===== DONE ====="
  echo "GRAPH_RUN_ID=${GRAPH_RUN_ID}"
  echo "EXPORT_DIR=${EXPORT_DIR}"
  echo "EXPORT_LOG=${EXPORT_LOG}"
  echo "Neo4j Browser HTTP: http://<tailscale-ip>:17474"
  echo "Neo4j Bolt URL:     neo4j://<tailscale-ip>:17687"
  echo "Username:           neo4j"
  echo "Password:           tgrag-local-2026"
} 2>&1 | tee ${EXPORT_LOG}
```


---

# Tóm tắt quyết định kỹ thuật quan trọng

| Vấn đề | Quyết định fix |
|---|---|
| `guest` không nên ảnh hưởng system Docker/admin | Dùng rootless Docker của `guest` |
| Root `database_exports` bị đổi owner `7474:7474` | Dùng `outputs/database_exports` cho run mới; root `database_exports` chỉ là legacy |
| Neo4j fail khi mount `:ro` | Không mount folder export; dùng `docker cp` từ `outputs/database_exports/<GRAPH_RUN_ID>` |
| Web UI mở được nhưng login fail | Dùng đúng Bolt URL `neo4j://<tailscale-ip>:17687` |
| Port `7474/7687` dễ trùng | Dùng host port `17474/17687` |
| `GRAPH_RUN_ID` mất khi mở terminal mới | Lưu vào `.last_graph_run_id`; log nằm ở `logs/graphdb_export/<GRAPH_RUN_ID>.log` |
