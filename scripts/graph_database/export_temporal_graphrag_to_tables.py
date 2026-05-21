import argparse
import os
import json
import networkx as nx
import pandas as pd
from pathlib import Path
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description="Export Temporal-GraphRAG output to CSV for Neo4j")
    parser.add_argument("--working_dir", required=True, help="Folder output graph đã build (VD: ./output_ollama)")
    parser.add_argument("--export_dir", required=True, help="Folder lưu CSV export")
    parser.add_argument("--graph_run_id", required=True, help="ID định danh cho lần chạy này")
    parser.add_argument("--overwrite", action="store_true", help="Ghi đè nếu folder export đã tồn tại")
    return parser.parse_args()

def safe_load_json(path):
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def main():
    args = parse_args()
    work_dir = Path(args.working_dir)
    export_dir = Path(args.export_dir)

    # 1. Validate Input
    req_files = [
        "graph_chunk_entity_relation.graphml",
        "kv_store_full_docs.json",
        "kv_store_text_chunks.json"
    ]
    for f in req_files:
        if not (work_dir / f).exists():
            raise FileNotFoundError(f"[Error] Thiếu file bắt buộc: {f}")

    if export_dir.exists() and not args.overwrite:
        raise FileExistsError(f"Folder {export_dir} đã tồn tại. Dùng --overwrite để ghi đè.")
    export_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Đang đọc dữ liệu từ: {work_dir}")
    
    # 2. Đọc GraphML & JSON
    entity_graph = nx.read_graphml(work_dir / "graph_chunk_entity_relation.graphml")
    full_docs = safe_load_json(work_dir / "kv_store_full_docs.json")
    text_chunks = safe_load_json(work_dir / "kv_store_text_chunks.json")

    # 3. Chuẩn bị dữ liệu cho CSV
    # 3.1. Documents & Chunks
    docs_data = [{"graph_run_id": args.graph_run_id, "id": k, "title": f"Doc {k}", "doc": str(v)} for k, v in full_docs.items()]
    chunks_data = [{"graph_run_id": args.graph_run_id, "id": k, "full_doc_id": v.get("full_doc_id", "doc_0"), "tokens": v.get("tokens", 0), "content": v.get("content", "")} for k, v in text_chunks.items()]

    # 3.2. Entity Nodes
    nodes_data = []
    node_chunk_links = []
    for node_id, data in entity_graph.nodes(data=True):
        nodes_data.append({
            "graph_run_id": args.graph_run_id,
            "id": str(node_id),
            "name": data.get("id", str(node_id)),
            "entity_type": data.get("entity_type", "UNKNOWN"),
            "description": data.get("description", ""),
            "source_id": data.get("source_id", "")
        })
        # Parse provenance
        sources = str(data.get("source_id", "")).split("<SEP>")
        for src in sources:
            if src.strip():
                node_chunk_links.append({"graph_run_id": args.graph_run_id, "node_id": str(node_id), "chunk_id": src.strip()})

    # 3.3. Entity Relationships
    edges_data = []
    for u, v, data in entity_graph.edges(data=True):
        edges_data.append({
            "graph_run_id": args.graph_run_id,
            "source_id": str(u),
            "target_id": str(v),
            "relationship_type": "RELATED",
            "description_json": data.get("description", ""),
            "source_id_json": data.get("source_id", "")
        })

    # 4. Ghi CSV
    print(f"[*] Đang ghi CSV ra: {export_dir}")
    pd.DataFrame(docs_data).to_csv(export_dir / "docs.csv", index=False)
    pd.DataFrame(chunks_data).to_csv(export_dir / "chunks.csv", index=False)
    pd.DataFrame(nodes_data).to_csv(export_dir / "entity_nodes.csv", index=False)
    pd.DataFrame(edges_data).to_csv(export_dir / "entity_relationships.csv", index=False)
    pd.DataFrame(node_chunk_links).to_csv(export_dir / "node_chunk_links.csv", index=False)

    # 5. Tạo file neo4j_import.cypher
    cypher_script = f"""// 1. Constraints
CREATE CONSTRAINT tgrag_entity_key IF NOT EXISTS FOR (n:TGRAGEntity) REQUIRE (n.graph_run_id, n.id) IS UNIQUE;

// 2. Load Docs
LOAD CSV WITH HEADERS FROM 'file:///{args.graph_run_id}/docs.csv' AS row
MERGE (d:TGRAGDocument {{graph_run_id: row.graph_run_id, id: row.id}})
SET d.title = row.title, d.doc = row.doc;

// 3. Load Chunks & Link to Doc
LOAD CSV WITH HEADERS FROM 'file:///{args.graph_run_id}/chunks.csv' AS row
MERGE (c:TGRAGChunk {{graph_run_id: row.graph_run_id, id: row.id}})
SET c.content = row.content, c.tokens = toInteger(row.tokens), c.full_doc_id = row.full_doc_id
WITH row, c
MATCH (d:TGRAGDocument {{graph_run_id: row.graph_run_id, id: row.full_doc_id}})
MERGE (d)-[:HAS_CHUNK]->(c);

// 4. Load Entity Nodes
LOAD CSV WITH HEADERS FROM 'file:///{args.graph_run_id}/entity_nodes.csv' AS row
MERGE (e:TGRAGEntity {{graph_run_id: row.graph_run_id, id: row.id}})
SET e.name = row.name, e.entity_type = row.entity_type, e.description = row.description;

// 5. Load Relationships
LOAD CSV WITH HEADERS FROM 'file:///{args.graph_run_id}/entity_relationships.csv' AS row
MATCH (s:TGRAGEntity {{graph_run_id: row.graph_run_id, id: row.source_id}})
MATCH (t:TGRAGEntity {{graph_run_id: row.graph_run_id, id: row.target_id}})
MERGE (s)-[r:RELATED {{graph_run_id: row.graph_run_id, source_id: row.source_id, target_id: row.target_id}}]->(t)
SET r.description_json = row.description_json;

// 6. Link Entity to Chunk (Provenance)
LOAD CSV WITH HEADERS FROM 'file:///{args.graph_run_id}/node_chunk_links.csv' AS row
MATCH (e:TGRAGEntity {{graph_run_id: row.graph_run_id, id: row.node_id}})
MATCH (c:TGRAGChunk {{graph_run_id: row.graph_run_id, id: row.chunk_id}})
MERGE (e)-[:MENTIONED_IN]->(c);
"""
    with open(export_dir / "neo4j_import.cypher", "w", encoding="utf-8") as f:
        f.write(cypher_script)

    # 6. Tạo Manifest
    manifest = {
        "graph_run_id": args.graph_run_id,
        "generated_at": datetime.now().isoformat(),
        "counts": {
            "docs": len(docs_data),
            "chunks": len(chunks_data),
            "entity_nodes": len(nodes_data),
            "entity_relationships": len(edges_data),
            "node_chunk_links": len(node_chunk_links)
        }
    }
    with open(export_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)

    print(f"[Success] Export thành công! Đã tạo manifest và neo4j_import.cypher.")

if __name__ == "__main__":
    main()