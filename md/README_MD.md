# README_MD — Lộ trình đọc tài liệu trong `md/`

File này giúp bạn biết nên đọc gì trước, theo đúng mục tiêu làm việc.

---

## 1) Nếu bạn mới vào project (đọc theo thứ tự này)

1. `md/metrics/tgrag_metrics_turboquant_evaluation.md`  
   → Tổng quan framework metric TG-RAG + TurboQuant.

2. `md/runbooks/turboquant_intervention_modes_cli.md`  
   → TurboQuant can thiệp từng phần hay toàn bộ, kèm CLI mode rõ ràng.

3. `md/metrics/tgrag_metrics_execution_runbook.md`  
   → Cách chạy để sinh kết quả metric thực tế (bao gồm p95/p99, CI, disagreement).

4. `md/runbooks/experiment_matrix_turboquant_vs_baseline.md`  
   → Ma trận thí nghiệm đề xuất để so sánh baseline vs turboquant công bằng.

---

## 2) Nếu mục tiêu là chạy build/query ngay

- Server + build/query CLI: đọc `md/CLI/start_server.md`, `md/CLI/build_graph.md`, `md/CLI/query_graph.md`
- Tuning inference: đọc `md/CLI/inference_config.md`
- Can thiệp mode TurboQuant: đọc `md/runbooks/turboquant_intervention_modes_cli.md`

---

## 3) Nếu mục tiêu là đánh giá chất lượng + hiệu năng

Đọc theo flow:

1. `md/metrics/tgrag_metrics_turboquant_evaluation.md` (định nghĩa metric)
2. `md/metrics/tgrag_metrics_execution_runbook.md` (cách chạy sinh metric)
3. `md/runbooks/experiment_matrix_turboquant_vs_baseline.md` (thiết kế thí nghiệm)

---

## 4) Nếu mục tiêu là xử lý build dài / resume

- `md/runbooks/resume_setup.md`
- `md/runbooks/build_graph_384_hf_nomic_run_report_v2.md`

---

## 5) Bản đồ nhanh theo thư mục (rõ trách nhiệm)

```text
md/
├── CLI/
├── runbooks/
├── metrics/
├── export_graphdb-neo4j/
├── dataset/
├── debug/
└── temporal-graphrag/
```

### `md/CLI/` — vận hành bằng lệnh

- Mục tiêu: nơi chứa **command chuẩn** để chạy server/build/query.
- Bạn đọc folder này khi cần “chạy được ngay” và muốn ít tranh luận kiến trúc.
- Ví dụ file: `start_server.md`, `build_graph.md`, `query_graph.md`, `inference_config.md`.

### `md/runbooks/` — playbook theo tình huống

- Mục tiêu: nơi chứa **kịch bản thao tác thực chiến** (resume, incident, intervention modes, run report).
- Bạn đọc folder này khi cần xử lý case cụ thể, fail cụ thể, hoặc tái hiện một thí nghiệm cụ thể.
- Ví dụ file: `resume_setup.md`, `turboquant_intervention_modes_cli.md`, `experiment_matrix_turboquant_vs_baseline.md`, `build_graph_384_hf_nomic_run_report_v2.md`.

### `md/metrics/` — đo chất lượng/hiệu năng

- Mục tiêu: định nghĩa metric + cách chạy pipeline đánh giá + cách đọc output.
- Đây là folder chính cho phần báo cáo `quality/efficiency/reliability`.
- Ví dụ file: `tgrag_metrics_turboquant_evaluation.md`, `tgrag_metrics_execution_runbook.md`.

### `md/export_graphdb-neo4j/` — export/import graph DB

- Mục tiêu: quy trình đưa kết quả TG-RAG vào Neo4j và xác minh dữ liệu sau import.
- Tách riêng khỏi `runbooks/` để dễ quản lý nhóm tài liệu Graph DB.
- Ví dụ file:
   - `export_graphdb_Neo4j.md` (quy trình end-to-end)
   - `neo4j_export_results_7b_v2.md` (kết quả export thực tế đã verify)

### `md/dataset/` — mô tả dữ liệu và biến thể

- Mục tiêu: nơi ghi quy ước dataset, split, sampling, filtering, versioning.

### `md/debug/` — nhật ký điều tra lỗi

- Mục tiêu: ghi lại symptom → root cause → fix path cho các lỗi lớn.
- Dùng khi cần triage nhanh, không dùng thay cho tài liệu vận hành chuẩn.

### `md/temporal-graphrag/` — kiến trúc và lý thuyết TG-RAG

- Mục tiêu: lưu conceptual docs (temporal graph design, assumptions, data model).
- Dùng để giải thích “vì sao làm vậy”, không chỉ “chạy lệnh nào”.

### Quy ước đặt tài liệu (để không rối)

- **Lệnh chuẩn** đặt ở `CLI/`
- **Kịch bản case-specific** đặt ở `runbooks/`
- **Metric & đánh giá** đặt ở `metrics/`
- **Graph DB exchange** đặt ở `export_graphdb-neo4j/`
- **Dữ liệu/Debug/Lý thuyết** lần lượt ở `dataset/`, `debug/`, `temporal-graphrag/`

Chi tiết chuẩn hóa tên file và version xem thêm:

- `md/NAMING_VERSIONING_CONVENTION.md`

---

## 6) Khuyến nghị thực tế khi làm báo cáo

- Chốt 1 ma trận chạy trước (E1/E4 tối thiểu).
- Đóng băng embedding config giữa các run.
- Tách rõ kết quả `quality`, `efficiency`, `reliability`.
- Luôn lưu log + JSON kết quả theo naming convention.

---

## 7) Đường đọc nhanh theo từng nhu cầu

- Muốn chạy ngay: `CLI/` → `runbooks/turboquant_intervention_modes_cli.md`
- Muốn benchmark nghiêm túc: `metrics/` → `runbooks/experiment_matrix_turboquant_vs_baseline.md`
- Muốn kiểm tra Neo4j: `export_graphdb-neo4j/export_graphdb_Neo4j.md` → `export_graphdb-neo4j/neo4j_export_results_7b_v2.md`
- Muốn xử lý build dài và resume: `runbooks/resume_setup.md` → `runbooks/build_graph_384_hf_nomic_run_report_v2.md`
