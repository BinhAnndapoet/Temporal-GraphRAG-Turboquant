# Experiment Matrix: TurboQuant vs Baseline (TG-RAG)

Mục tiêu: chuẩn hóa ma trận thí nghiệm để so sánh công bằng giữa:

- Baseline (non-TurboQuant)
- TurboQuant (local llama-server)

Tài liệu này là file điều phối nhanh: **chạy gì trước, đặt tên ra sao, log lưu đâu, báo cáo metric thế nào**.

---

## 1. Nguyên tắc so sánh công bằng

Giữ cố định:

- Dataset / split câu hỏi
- Embedding config
- Query mode (`local/global/naive`) cho từng benchmark
- Prompt / token budget

Chỉ thay biến độc lập chính:

- LLM runtime: baseline vs turboquant

---

## 2. Ma trận thí nghiệm đề xuất

| ID | Mục tiêu | Build | Query | Judge | Kết quả chính |
|---|---|---|---|---|---|
| E1 | Baseline tham chiếu | Baseline | Baseline | External | Chất lượng + hiệu năng baseline |
| E2 | TurboQuant query-only | Baseline graph | TurboQuant | External | Tăng tốc inference, giữ quality |
| E3 | TurboQuant build-only | TurboQuant | Baseline | External | Giảm thời gian indexing/update |
| E4 | TurboQuant end-to-end | TurboQuant | TurboQuant | External | Claim optimize TG-RAG đầy đủ |
| E5 | Reliability check | (E4) | (E4) | Multi-judge | Disagreement + CI |

Khuyến nghị tối thiểu để báo cáo seminar:

- Bắt buộc có `E1` + `E4`
- Nếu thời gian đủ: thêm `E2` để chứng minh lợi ích query-only

---

## 3. Naming convention

Dùng format thống nhất:

```text
BUILD_<profile>_<docs>_<date>
PRED_<exp_id>_<mode>_<judge>_<date>.jsonl
METRIC_<exp_id>_<scope>_<date>.json
```

Ví dụ:

```text
BUILD_tq_7b_p2_c65k_hf_nomic_384docs_20260527
PRED_E4_local_none_20260527.jsonl
METRIC_E4_specific_nonllm_20260527.json
```

---

## 4. Thư mục output khuyến nghị

```text
outputs/build_graph/<BUILD_ID>/
results/preds/<PRED_ID>.jsonl
results/judged/<JUDGE_ID>.jsonl
results/metrics/<METRIC_ID>.json
results/reports/<REPORT_ID>.md
logs/build_graph/<BUILD_ID>.log
logs/query/<RUN_ID>.log
logs/llama_server/<SERVER_ID>.log
```

---

## 5. Checklist theo từng experiment

## 5.1 Trước khi chạy

- [ ] Server local hoạt động (`/v1` ok)
- [ ] Alias model khớp CLI
- [ ] Embedding config đã khóa cố định
- [ ] `working_dir` đúng build output
- [ ] Biến API judge đã set nếu dùng external judge

## 5.2 Sau khi chạy prediction

- [ ] Số câu chạy thành công khớp kỳ vọng
- [ ] Không có lỗi timeout hàng loạt
- [ ] Có file output JSONL hợp lệ

## 5.3 Sau khi chấm điểm

- [ ] Có non-LLM metrics (F1, ROUGE-L)
- [ ] Có specific judge metrics (Correct/Refusal/Incorrect)
- [ ] Có abstract pairwise win-rate (nếu benchmark abstract)
- [ ] Có p95/p99 latency
- [ ] Có bootstrap CI
- [ ] Có judge disagreement rate (nếu multi-judge)

---

## 6. Báo cáo tối thiểu để kết luận

Một kết luận “TurboQuant optimize TG-RAG” nên có đủ:

1. **Quality retention**: Correct/F1/ROUGE-L/Temporal Coverage không giảm mạnh.
2. **Efficiency gain**: latency mean + p95/p99 tốt hơn baseline.
3. **Reliability**: CI hợp lý, disagreement được báo cáo minh bạch.

---

## 7. Tài liệu liên quan (đọc kèm)

- `md/runbooks/turboquant_intervention_modes_cli.md`
- `md/metrics/tgrag_metrics_execution_runbook.md`
- `md/metrics/tgrag_metrics_turboquant_evaluation.md`
- `md/runbooks/resume_setup.md`
