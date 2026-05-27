# Naming & Versioning Convention for `md/`

Mục tiêu: giúp đọc nhanh tài liệu nào là bản mới nhất, tránh nhầm file cũ/mới.

> File này được đặt ở `md/` gốc có chủ đích, vì đây là quy ước áp dụng cho **toàn bộ** tài liệu con trong `md/`.

---

## 1) Quy tắc tên file chuẩn

### 1.1. Nhóm tài liệu vận hành chuẩn (stable)

Dùng khi nội dung là tài liệu nền, cập nhật liên tục:

- `snake_case.md`
- Ví dụ: `build_graph.md`, `query_graph.md`, `inference_config.md`

### 1.2. Nhóm report/runbook theo phiên bản

Dùng khi nội dung là kết quả theo đợt chạy, milestone, hoặc revision rõ ràng:

- `*_report_v{N}.md`
- `*_results_v{N}.md`
- `*_runbook_v{N}.md`

Ví dụ:

- `build_graph_384_hf_nomic_run_report_v2.md`
- `neo4j_export_results_7b_v2.md`

---

## 2) Quy tắc tăng version

Tăng phiên bản `v{N+1}` khi có một trong các thay đổi sau:

- thay đổi kết luận kỹ thuật chính
- thay đổi dataset/run_id/model config dùng để báo cáo
- thay đổi metric framework hoặc cách diễn giải kết quả
- bổ sung evidence mới có thể ảnh hưởng quyết định

Nếu chỉ sửa typo/link/format nhỏ: **không cần tăng version**, chỉ cập nhật tại chỗ.

---

## 3) Quy tắc “canonical + compatibility”

- File có hậu tố version (vd `*_v2.md`) là **canonical** để review.
- File cũ không version có thể giữ tạm để tương thích link cũ, nhưng phải ghi rõ:
  - `Deprecated path`
  - đường dẫn canonical mới

---

## 4) Trạng thái chuẩn hóa hiện tại

| Loại | File | Trạng thái |
|---|---|---|
| Run report 7B | `md/runbooks/build_graph_384_hf_nomic_run_report_v2.md` | Canonical |
| Run report 7B (legacy path) | `md/runbooks/build_graph_384_hf_nomic_run_report.md` | Compatibility path |
| Neo4j export results 7B | `md/export_graphdb-neo4j/neo4j_export_results_7b_v2.md` | Canonical |

---

## 5) Quy ước review nhanh

Khi review kỹ thuật, ưu tiên theo thứ tự:

1. file có hậu tố version cao nhất (`v3` > `v2` > `v1`)
2. file được README trỏ trực tiếp
3. file có `graph_run_id`/`run_id` và timestamp rõ ràng
