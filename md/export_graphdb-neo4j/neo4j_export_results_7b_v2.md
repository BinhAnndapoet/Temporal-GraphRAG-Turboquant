# Neo4j Export Results (v2) — 7B / 384 docs

Tài liệu này tóm tắt **kết quả export thực tế** sang package Neo4j cho run 7B mới nhất.

---

## 1) Export package được xác nhận

- `graph_run_id`: `BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2_neo4j_20260526_235707`
- Thư mục:  
  `outputs/database_exports/BUILD_qwen25_7b_p4_c131072_hf_nomic_cuda_384docs_fresh-v2_neo4j_20260526_235707`
- Thời gian sinh package: `2026-05-26T23:57:08`

---

## 2) Kết quả manifest (đã verify)

Nguồn: `manifest.json`

| Thành phần | Số lượng |
|---|---:|
| docs | 384 |
| chunks | 1462 |
| entity_nodes | 18722 |
| entity_relationships | 15222 |
| node_chunk_links | 35861 |

=> Export package hợp lệ cho import Neo4j (đủ bảng node/edge/provenance).

---

## 3) Temporal evidence (đã kiểm chứng từ CSV)

Nguồn: `entity_nodes.csv` + `entity_relationships.csv`

- Tổng node: `18722`
- Temporal node (`DATE|MONTH|QUARTER|YEAR`): `195`
  - `YEAR`: 32
  - `QUARTER`: 66
  - `DATE`: 94
  - `MONTH`: 3
- Tổng quan hệ: `15222`
- Quan hệ chạm temporal nodes: `517`

Top temporal hubs (degree trong `entity_relationships.csv`):

1. `2022` → 62
2. `2021-Q4` → 36
3. `2022-QQ3` → 34
4. `2021-Q1` → 28
5. `2023-Q2` → 26

### Nhận định nhanh

- Có temporal nodes và temporal-linked edges ở mức đáng kể.
- Chưa thấy 1 temporal node “nuốt toàn graph” kiểu siêu hub mất kiểm soát trong export này.
- Nên tiếp tục theo dõi khi bật/tắt chiến lược upsert temporal edges ở các branch khác.

---

## 4) Các file export quan trọng

Trong thư mục export có các file chính:

- `docs.csv`
- `chunks.csv`
- `entity_nodes.csv`
- `entity_relationships.csv`
- `node_chunk_links.csv`
- `neo4j_import.cypher`
- `manifest.json`

---

## 5) Truy vấn Neo4j kiểm tra sau import (quick sanity)

```cypher
MATCH (d:TGRAGDocument {graph_run_id: $run_id}) RETURN count(d) AS docs;
MATCH (c:TGRAGChunk {graph_run_id: $run_id}) RETURN count(c) AS chunks;
MATCH (e:TGRAGEntity {graph_run_id: $run_id}) RETURN count(e) AS entities;
MATCH (:TGRAGEntity {graph_run_id: $run_id})-[r:RELATED {graph_run_id: $run_id}]->(:TGRAGEntity {graph_run_id: $run_id}) RETURN count(r) AS rels;
```

Kỳ vọng: docs/chunks/entities/rels khớp xấp xỉ manifest (chênh lệch chỉ khi bạn import nhiều run_id cùng DB nhưng query thiếu filter `graph_run_id`).

---

## 6) Liên kết tài liệu liên quan

- Hướng dẫn export/import end-to-end: `md/export_graphdb-neo4j/export_graphdb_Neo4j.md`
- Run report build 7B v2: `md/runbooks/build_graph_384_hf_nomic_run_report_v2.md`
