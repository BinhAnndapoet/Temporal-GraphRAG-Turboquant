import argparse
import json
import csv
import logging
import networkx as nx
import pandas as pd
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("tgrag.graphdb_export")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export Temporal-GraphRAG output to CSV for Neo4j"
    )
    parser.add_argument(
        "--working_dir",
        required=True,
        help="Folder output graph đã build (VD: ./output_ollama)",
    )
    parser.add_argument("--export_dir", required=True, help="Folder lưu CSV export")
    parser.add_argument(
        "--graph_run_id", required=True, help="ID định danh cho lần chạy này"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Ghi đè nếu folder export đã tồn tại"
    )
    parser.add_argument(
        "--log_file",
        help="File log cho riêng bước Python export; workflow shell vẫn nên dùng tee để capture Docker/Cypher",
    )
    return parser.parse_args()


def setup_logging(log_file=None):
    handlers = [logging.StreamHandler()]
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, mode="a", encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def file_info(path: Path) -> str:
    stat = path.stat()
    return f"{path} size={stat.st_size} bytes mtime={datetime.fromtimestamp(stat.st_mtime).isoformat()}"


def normalize_csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def df_from_rows(rows):
    return pd.DataFrame(rows)


def write_csv(df, path: Path):
    df.to_csv(
        path,
        index=False,
        encoding="utf-8",
        quoting=csv.QUOTE_ALL,
        escapechar="\\",
    )


def safe_load_json(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    args = parse_args()
    setup_logging(args.log_file)

    start_time = datetime.now()
    logger.info("===== START GRAPHDB EXPORT =====")
    logger.info("graph_run_id=%s", args.graph_run_id)
    logger.info("working_dir=%s", args.working_dir)
    logger.info("export_dir=%s", args.export_dir)
    if args.log_file:
        logger.info("log_file=%s", args.log_file)

    work_dir = Path(args.working_dir)
    export_dir = Path(args.export_dir)

    # 1. Validate Input
    req_files = [
        "graph_chunk_entity_relation.graphml",
        "kv_store_full_docs.json",
        "kv_store_text_chunks.json",
    ]
    logger.info("Checking required input files")
    for f in req_files:
        path = work_dir / f
        if not path.exists():
            logger.error("Missing required file: %s", path)
            raise FileNotFoundError(f"[Error] Thiếu file bắt buộc: {path}")
        logger.info("input %s", file_info(path))

    if export_dir.exists() and not args.overwrite:
        raise FileExistsError(
            f"Folder {export_dir} đã tồn tại. Dùng --overwrite để ghi đè."
        )
    export_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Export directory ready: %s", export_dir)

    logger.info("Reading graph and KV stores from: %s", work_dir)

    # 2. Đọc GraphML & JSON
    entity_graph = nx.read_graphml(work_dir / "graph_chunk_entity_relation.graphml")
    full_docs = safe_load_json(work_dir / "kv_store_full_docs.json")
    text_chunks = safe_load_json(work_dir / "kv_store_text_chunks.json")
    logger.info(
        "Loaded graph nodes=%s edges=%s full_docs=%s text_chunks=%s",
        entity_graph.number_of_nodes(),
        entity_graph.number_of_edges(),
        len(full_docs),
        len(text_chunks),
    )

    # 3. Chuẩn bị dữ liệu cho CSV
    # 3.1. Documents & Chunks
    docs_data = [
        {
            "graph_run_id": args.graph_run_id,
            "id": normalize_csv_value(k),
            "title": normalize_csv_value(f"Doc {k}"),
            "doc": normalize_csv_value(v),
        }
        for k, v in full_docs.items()
    ]
    chunks_data = [
        {
            "graph_run_id": args.graph_run_id,
            "id": normalize_csv_value(k),
            "full_doc_id": normalize_csv_value(v.get("full_doc_id", "doc_0")),
            "tokens": int(v.get("tokens", 0) or 0),
            "content": normalize_csv_value(v.get("content", "")),
        }
        for k, v in text_chunks.items()
    ]

    # 3.2. Entity Nodes
    nodes_data = []
    node_chunk_links = []
    for node_id, data in entity_graph.nodes(data=True):
        nodes_data.append(
            {
                "graph_run_id": args.graph_run_id,
                "id": normalize_csv_value(node_id),
                "name": normalize_csv_value(data.get("id", str(node_id))),
                "entity_type": normalize_csv_value(data.get("entity_type", "UNKNOWN")),
                "description": normalize_csv_value(data.get("description", "")),
                "source_id": normalize_csv_value(data.get("source_id", "")),
            }
        )
        # Parse provenance
        sources = str(data.get("source_id", "")).split("<SEP>")
        for src in sources:
            if src.strip():
                node_chunk_links.append(
                    {
                        "graph_run_id": args.graph_run_id,
                        "node_id": normalize_csv_value(node_id),
                        "chunk_id": normalize_csv_value(src.strip()),
                    }
                )

    # 3.3. Entity Relationships
    edges_data = []
    for u, v, data in entity_graph.edges(data=True):
        description_value = data.get("description", "")
        source_id_value = data.get("source_id", "")
        if isinstance(description_value, (dict, list)):
            description_value = json.dumps(description_value, ensure_ascii=False)
        if isinstance(source_id_value, (dict, list)):
            source_id_value = json.dumps(source_id_value, ensure_ascii=False)

        edges_data.append(
            {
                "graph_run_id": args.graph_run_id,
                "source_id": normalize_csv_value(u),
                "target_id": normalize_csv_value(v),
                "relationship_type": "RELATED",
                "description_json": normalize_csv_value(description_value),
                "source_id_json": normalize_csv_value(source_id_value),
            }
        )

    logger.info(
        "Prepared rows docs=%s chunks=%s entity_nodes=%s entity_relationships=%s node_chunk_links=%s",
        len(docs_data),
        len(chunks_data),
        len(nodes_data),
        len(edges_data),
        len(node_chunk_links),
    )

    # 4. Ghi CSV
    logger.info("Writing CSV files to: %s", export_dir)
    write_csv(df_from_rows(docs_data), export_dir / "docs.csv")
    write_csv(df_from_rows(chunks_data), export_dir / "chunks.csv")
    write_csv(df_from_rows(nodes_data), export_dir / "entity_nodes.csv")
    write_csv(df_from_rows(edges_data), export_dir / "entity_relationships.csv")
    write_csv(df_from_rows(node_chunk_links), export_dir / "node_chunk_links.csv")
    for csv_name in [
        "docs.csv",
        "chunks.csv",
        "entity_nodes.csv",
        "entity_relationships.csv",
        "node_chunk_links.csv",
    ]:
        logger.info("output %s", file_info(export_dir / csv_name))

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
    cypher_path = export_dir / "neo4j_import.cypher"
    with open(cypher_path, "w", encoding="utf-8") as f:
        f.write(cypher_script)
    logger.info("output %s", file_info(cypher_path))

    # 6. Tạo Manifest
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
    manifest_path = export_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
    logger.info("output %s", file_info(manifest_path))

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(
        "[Success] Export thành công! Đã tạo manifest và neo4j_import.cypher. elapsed_seconds=%.2f",
        elapsed,
    )


if __name__ == "__main__":
    main()
