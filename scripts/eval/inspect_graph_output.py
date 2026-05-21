#!/usr/bin/env python3
"""Inspect Temporal-GraphRAG output artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def print_json_kv(path: Path, label: str) -> None:
    if not path.exists():
        print(f"[missing] {path.name}")
        return
    data = load_json(path)
    print(f"[{label}] {path.name}: {len(data)} records")
    if data:
        first_key = next(iter(data))
        first_value = data[first_key]
        print(f"  first_id: {first_key}")
        if isinstance(first_value, dict):
            print(f"  fields: {sorted(first_value.keys())}")
            content = first_value.get("content") or first_value.get("doc") or ""
            if content:
                print(f"  content_preview: {str(content)[:240].replace(chr(10), ' ')}")


def print_vdb(path: Path, label: str) -> None:
    if not path.exists():
        print(f"[missing] {path.name}")
        return
    data = load_json(path)
    rows = data.get("data", {})
    embeddings = data.get("embeddings", {})
    print(f"[{label}] {path.name}: {len(rows)} rows, {len(embeddings)} embeddings")
    if rows:
        first_key = next(iter(rows))
        print(f"  first_id: {first_key}")
        print(f"  fields: {sorted(rows[first_key].keys())}")
        if first_key in embeddings:
            print(f"  embedding_dim: {len(embeddings[first_key])}")


def print_graph(path: Path, label: str) -> None:
    if not path.exists():
        print(f"[missing] {path.name}")
        return
    try:
        import networkx as nx
    except ImportError:
        print(f"[{label}] {path.name}: install networkx to inspect graph counts")
        return
    graph = nx.read_graphml(path)
    print(f"[{label}] {path.name}: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    for node, attrs in list(graph.nodes(data=True))[:3]:
        print(f"  node: {node} fields={sorted(attrs.keys())}")
    for src, dst, attrs in list(graph.edges(data=True))[:3]:
        print(f"  edge: {src} -> {dst} fields={sorted(attrs.keys())}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print counts and previews for graph output files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--working_dir", required=True)
    args = parser.parse_args()

    working_dir = Path(args.working_dir)
    if not working_dir.exists():
        raise SystemExit(f"Working directory does not exist: {working_dir}")

    print(f"[working_dir] {working_dir.resolve()}")
    print("[files]")
    for path in sorted(working_dir.iterdir()):
        if path.is_file():
            print(f"  {path.name} ({path.stat().st_size / 1024:.1f} KiB)")

    print()
    print_json_kv(working_dir / "kv_store_full_docs.json", "full_docs")
    print_json_kv(working_dir / "kv_store_text_chunks.json", "text_chunks")
    print_json_kv(working_dir / "kv_store_llm_response_cache.json", "llm_cache")
    print_json_kv(working_dir / "kv_store_community_reports.json", "community_reports")
    print_vdb(working_dir / "vdb_entities.json", "entities_vdb")
    print_vdb(working_dir / "vdb_entities_new.json", "entities_vdb_new")
    print_vdb(working_dir / "vdb_relations.json", "relations_vdb")
    print_vdb(working_dir / "vdb_chunks.json", "chunks_vdb")
    print_graph(working_dir / "graph_chunk_entity_relation.graphml", "entity_relation_graph")
    print_graph(working_dir / "graph_temporal_hierarchy.graphml", "temporal_hierarchy_graph")


if __name__ == "__main__":
    main()
