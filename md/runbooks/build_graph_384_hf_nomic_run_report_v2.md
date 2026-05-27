# build_graph_384_hf_nomic_run_report_v2

> Canonical versioned path cho báo cáo run 7B.

Tài liệu đầy đủ hiện được duy trì tại:

- `md/runbooks/build_graph_384_hf_nomic_run_report.md`

Ghi chú chuẩn hóa:

- File này tồn tại để thống nhất naming convention theo hậu tố version (`_v2`).
- Trong các tài liệu mới, ưu tiên trỏ link đến file này.
- Legacy path vẫn giữ để tránh vỡ liên kết cũ.

## Snapshot nhanh

- Model: `qwen25-7b` (TurboQuant local serving)
- Corpus: 384 docs
- Build status: pass kỹ thuật (graph/vector/docs persisted)
- Community reports: còn lỗi context overflow ở một số community lớn
- Neo4j export evidence (v2):
  - `md/export_graphdb-neo4j/neo4j_export_results_7b_v2.md`
