# TG-RAG Evaluation Metrics và Metric khi tích hợp TurboQuant

> Mục tiêu tài liệu: tổng hợp lại các nhóm metric dùng để đánh giá **TG-RAG** theo paper gốc, sau đó bổ sung các metric cần dùng khi **apply TurboQuant** để tối ưu các LLM-heavy stages.  
> Tài liệu này dùng cho seminar / báo cáo kỹ thuật, nên trình bày theo hướng: **metric đo gì → đo ra sao → công thức → ví dụ → ý nghĩa khi đọc kết quả**.

---

## 0. Cách đọc tổng quan

TG-RAG là hệ thống RAG có yếu tố thời gian, nên đánh giá không chỉ dừng ở việc câu trả lời đúng hay sai. Paper gốc đánh giá theo nhiều góc nhìn:

1. **Specific QA**: câu hỏi fact-based, đáp án tương đối rõ.
2. **Abstract QA**: câu hỏi tổng hợp, phân tích xu hướng, cần đánh giá bằng LLM-as-a-Judge.
3. **Incremental Evaluation**: corpus được cập nhật theo thời gian, cần đo stability và adaptability.
4. **Cost / Ablation**: đo chi phí indexing/update và kiểm tra thành phần nào đóng góp vào performance.

Khi thêm **TurboQuant**, ta bổ sung thêm nhóm metric mở rộng:

5. **Graph Build & Retrieval Diagnostics**: metric để đo build graph nhanh/chuẩn tới mức nào và evidence retrieval có đúng temporal scope không.
6. **Efficiency + Quality Retention với TurboQuant**: đo latency, throughput, VRAM, update time và chất lượng sau quantization.

Nói ngắn gọn theo đúng tinh thần seminar:

- **Paper TG-RAG gốc**: đo build graph chủ yếu **gián tiếp** qua indexing/update cost, ablation temporal indexing và downstream QA.
- **Khi tích hợp TurboQuant**: cần đo build graph **trực tiếp hơn** (efficiency + construction quality + coverage/structure) để thấy rõ trade-off tốc độ/chất lượng.

> Lưu ý phân loại: nhóm 1–4 bám sát paper TG-RAG gốc. Nhóm 5 và 6 là nhóm metric mở rộng để phục vụ việc triển khai lại, debug hệ thống và so sánh khi tích hợp TurboQuant.

---

## 1. Bảng tổng hợp 6 nhóm metric

| Nhóm | Nguồn | Metric chính | Đo điều gì? | Dùng khi nào? |
|---|---|---|---|---|
| **1. Specific QA** | Paper gốc | Correct, Refusal, Incorrect, ROUGE-L, F1 | Câu trả lời fact-based có đúng, sai, từ chối, hoặc khớp reference không | Specific multi-hop QA |
| **2. Abstract QA** | Paper gốc | Comprehensiveness, Diversity, Temporal Coverage, Overall Winner | Câu trả lời tổng hợp có đầy đủ, đa dạng, đúng timeline không | Abstract / global temporal QA |
| **3. Incremental Evaluation** | Paper gốc | Base queries on base corpus, base queries on updated corpus, new queries on updated corpus, Index/Update Token Cost | Hệ thống có ổn định sau update và thích nghi với dữ liệu mới không | Evolving corpus / update scenario |
| **4. Ablation Study** | Paper gốc | Full TG-RAG, w/o PPR, w/o Temporal Retrieval, w/o Temporal Indexing | Thành phần nào trong TG-RAG đóng góp nhiều vào performance | Phân tích cơ chế, không chỉ báo cáo kết quả |
| **5. Graph Build & Retrieval Diagnostics** | Bổ sung triển khai | Build time, extraction throughput, quadruple validity, timestamp accuracy, grounding rate, coverage, Evidence Recall/Precision/TEA | Graph build có nhanh/ổn định không và evidence retrieve có đúng temporal scope không | Debug indexing + retriever + temporal filtering |
| **6. TurboQuant Efficiency** | Bổ sung khi tích hợp TurboQuant | Latency, Throughput, VRAM usage, Indexing/update time, Quality Retention, Quality Drop | TurboQuant có tối ưu inference mà vẫn giữ chất lượng temporal QA không | So sánh model gốc vs model quantized |

---

# Nhóm 1 — Specific QA Metrics

## 1.1. Specific QA là gì?

**Specific QA** là nhóm câu hỏi có đáp án tương đối rõ ràng, thường là dạng fact-based hoặc multi-hop fact-based.

Ví dụ:

```text
What was Western Digital Corporation's revenue in each quarter from 2023 Q1 to Q3?
```

Expected answer:

```text
2023-Q1 → $3.7B
2023-Q2 → $3.1B
2023-Q3 → $2.8B
```

Với dạng này, hệ thống cần trả lời đúng từng factual element. Nếu trả đúng nội dung nhưng sai mốc thời gian, trong TG-RAG vẫn phải xem là sai.

---

## 1.2. Các metric chính

| Metric | Đo gì? | Đo ra sao? | Công thức / cách tính | Ví dụ | Cách đọc |
|---|---|---|---|---|---|
| **Correct ↑** | Tỷ lệ factual elements được trả lời đúng | LLM-as-a-Judge so sánh từng factual element trong prediction với ground truth và evidence | `Correct = số factual elements đúng / tổng factual elements cần đánh giá` | Ground truth có 3 quý; model trả đúng đủ `$3.7B`, `$3.1B`, `$2.8B` | Càng cao càng tốt |
| **Refusal** | Tỷ lệ model từ chối trả lời | Đếm factual elements model trả kiểu “I don’t know”, “No explicit evidence”, “không đủ thông tin” | `Refusal = số elements bị từ chối / tổng elements` | Corpus có answer nhưng model nói “không đủ thông tin” | Với unanswerable QA, refusal có thể tốt; với answerable QA, refusal cao thường xấu |
| **Incorrect ↓** | Tỷ lệ factual elements sai, unsupported hoặc hallucinated | LLM judge đếm facts sai, lẫn thời gian hoặc bịa | `Incorrect = số elements sai / tổng elements` | Query hỏi 2023 Q1–Q3 nhưng model lấy revenue của 2022 hoặc 2024 | Càng thấp càng tốt |
| **ROUGE-L ↑** | Mức overlap theo chuỗi con chung dài nhất giữa generated answer và reference | So sánh Longest Common Subsequence giữa prediction và reference | Dựa trên LCS; thường báo cáo dạng F-measure | Model diễn đạt gần giống reference summary | Hữu ích cho overlap ngôn ngữ, nhưng chưa đủ để đo temporal correctness |
| **F1 ↑** | Mức overlap token-level giữa prediction và ground truth | Tính precision và recall theo token/span | `F1 = 2PR / (P + R)` | Model trả đúng 2/3 giá trị quý → F1 trung bình | Phù hợp với answer ngắn, nhiều value/entity |

Paper TG-RAG dùng GPT-4o-mini làm judge để đánh giá factual accuracy cho specific QA. Các factual elements được phân loại thành Correct, Refusal hoặc Incorrect; ngoài ra paper dùng ROUGE-L và F1 như non-LLM lexical overlap metrics.

---

## 1.3. Công thức F1

```text
Precision = số token đúng trong prediction / số token trong prediction

Recall = số token đúng trong prediction / số token trong ground truth

F1 = 2 × Precision × Recall / (Precision + Recall)
```

### Giải thích biến

| Ký hiệu | Ý nghĩa | Diễn giải |
|---|---|---|
| `Precision` | Độ chính xác của phần model trả ra | Trong những gì model nói, bao nhiêu là đúng |
| `Recall` | Độ bao phủ so với ground truth | Trong những gì cần trả lời, model trả được bao nhiêu |
| `F1` | Trung bình điều hòa của precision và recall | Cao khi prediction vừa đúng vừa đủ |

### Ví dụ F1 đơn giản

Ground truth:

```text
$3.7B, $3.1B, $2.8B
```

Prediction:

```text
$3.7B, $3.1B
```

Diễn giải:

- Model trả ra 2 giá trị và cả 2 đều đúng → precision cao.
- Nhưng model thiếu `$2.8B` của Q3 → recall thấp hơn.
- F1 phản ánh câu trả lời **đúng một phần nhưng chưa đầy đủ**.

---

## 1.4. Ví dụ lỗi Incorrect trong TG-RAG

Query:

```text
What was Western Digital Corporation's revenue in each quarter from 2023 Q1 to Q3?
```

Prediction sai:

```text
Western Digital reported $3.5B in 2022, $3.1B in 2023 Q2, and $3.0B in 2024.
```

Lý do sai:

| Lỗi | Giải thích |
|---|---|
| Sai mốc thời gian | Có evidence 2022 và 2024, trong khi query yêu cầu 2023 Q1–Q3 |
| Thiếu Q1/Q3 đúng | Không trả đúng đủ 3 quarter được hỏi |
| Temporal hallucination | Đúng entity/revenue nhưng sai temporal scope |

---

# Nhóm 2 — Abstract QA Metrics

## 2.1. Abstract QA là gì?

**Abstract QA** là nhóm câu hỏi cần tổng hợp, giải thích xu hướng, so sánh hoặc viết summary theo thời gian. Dạng này không có một exact answer duy nhất, nên khó dùng Exact Match.

Ví dụ:

```text
How did energy companies navigate cost pressures across 2024?
```

Answer tốt cần:

- bao phủ nhiều khía cạnh quan trọng,
- không chỉ lặp một ý,
- trình bày timeline rõ,
- có evidence từ đúng giai đoạn.

Paper TG-RAG dùng **LLM-based multi-dimensional pairwise comparison** cho abstract QA. Judge so sánh hai answers theo 3 tiêu chí: **Comprehensiveness**, **Diversity**, **Temporal Coverage**, sau đó chọn **Overall Winner**.

---

## 2.2. Các metric chính

| Metric | Đo gì? | Đo ra sao? | Công thức / cách tính | Ví dụ | Cách đọc |
|---|---|---|---|---|---|
| **Comprehensiveness ↑** | Answer có bao phủ đầy đủ các khía cạnh quan trọng không | Pairwise LLM judge chọn answer đầy đủ hơn | `Win-rate = số lần method thắng / tổng số comparisons` | Query hỏi xu hướng 2024; answer nhắc cost reduction, pricing discipline, demand recovery | Càng cao càng tốt |
| **Diversity ↑** | Answer có đa dạng góc nhìn, theme, evidence không | Judge xem answer có nhiều perspectives hay chỉ lặp một ý | `Diversity win-rate = số lần thắng về Diversity / tổng comparisons` | Answer chỉ nói “cost cutting” → thấp; thêm pricing, demand, margin, capex → cao | Càng cao càng tốt |
| **Temporal Coverage ↑** | Answer có bao phủ đúng và đủ chiều thời gian không | Judge kiểm tra answer có nhắc đúng years, quarters, events, timeline không | `Temporal Coverage win-rate = số lần thắng về temporal dimension / tổng comparisons` | Query hỏi Q1–Q3 nhưng answer chỉ nói Q1–Q2 → thấp | Rất quan trọng với TG-RAG |
| **Overall Winner ↑** | Answer nào tốt hơn tổng thể | Judge chọn winner dựa trên 3 tiêu chí trên | `Overall win-rate = số lần method được chọn winner / tổng comparisons` | TG-RAG đầy đủ hơn, đúng timeline hơn → TG-RAG thắng | Dùng để báo cáo win-rate tổng thể |

---

## 2.3. Temporal Coverage cần hiểu thế nào?

Temporal Coverage đo mức answer bao phủ đúng **temporal scope** mà query yêu cầu.

Query:

```text
What was Western Digital Corporation's revenue in each quarter from 2023 Q1 to Q3?
```

Temporal scope:

```text
Tq = {2023-Q1, 2023-Q2, 2023-Q3}
```

Answer tốt:

```text
2023-Q1 → $3.7B
2023-Q2 → $3.1B
2023-Q3 → $2.8B
```

Các lỗi thường gặp:

| Lỗi | Ví dụ | Vì sao sai? |
|---|---|---|
| Thiếu mốc thời gian | Chỉ trả Q1 và Q2 | Không cover đủ `Tq` |
| Sai mốc thời gian | Lấy revenue của 2022 hoặc 2024 | Đúng topic nhưng sai time |
| Gộp timeline | “Revenue was around $3B in 2023” | Không trả theo từng quý |
| Timeline lộn xộn | Q3 → Q1 → Q2 | Chronological explanation khó theo dõi |

---

## 2.4. Công thức win-rate

```text
Win-rate(method A) = số lần A thắng / tổng số pairwise comparisons
```

Ví dụ:

```text
TG-RAG thắng 80 lần trên 100 comparisons
Win-rate = 80 / 100 = 0.80
```

Diễn giải:

- Nếu TG-RAG có win-rate cao hơn baseline ở Temporal Coverage, điều đó cho thấy temporal graph và temporal retrieval giúp answer bám timeline tốt hơn.
- Nếu win-rate cao ở Comprehensiveness nhưng thấp ở Diversity, answer có thể đầy đủ nhưng chưa đa dạng góc nhìn.

---

# Nhóm 3 — Incremental Evaluation và Update Cost

## 3.1. Vì sao cần nhóm metric này?

TG-RAG nhấn mạnh rằng nhiều RAG evaluation trước đó giả định corpus tĩnh. Nhưng thực tế corpus luôn thay đổi: có báo cáo mới, transcript mới, chính sách mới, dữ liệu mới.

Do đó, paper chia evaluation thành ba setting để đo:

1. performance trước update,
2. stability sau update,
3. adaptability với query mới.

---

## 3.2. Ba setting đánh giá trong paper

| Setting | Corpus | Query | Mục tiêu đo | Ý nghĩa |
|---|---|---|---|---|
| **Base queries on base corpus** | Corpus cũ, ví dụ `2020–2023` | Query cũ | Base performance | Hệ thống hoạt động thế nào trước khi update |
| **Base queries on updated corpus** | Corpus đã thêm dữ liệu mới, ví dụ thêm `2024` | Query cũ | Stability after update | Thêm dữ liệu mới có làm hỏng câu hỏi cũ không |
| **New queries on updated corpus** | Corpus đã update | Query mới liên quan dữ liệu mới | New query adaptability | Hệ thống có học và retrieve được facts mới không |

---

## 3.3. Metric chi tiết

| Metric | Đo gì? | Đo ra sao? | Công thức / cách tính | Ví dụ | Cách đọc |
|---|---|---|---|---|---|
| **Base performance** | Chất lượng trên corpus ban đầu | Chạy Specific QA và Abstract QA trên base corpus | Dùng Correct/F1/ROUGE-L hoặc abstract win-rate | Corpus 2020–2023, query hỏi revenue 2023 Q1–Q3 | Là baseline trước update |
| **Stability after update** | Performance trên query cũ có ổn định sau khi thêm corpus mới không | Chạy lại base queries trên updated corpus rồi so với before update | `Stability Drop = Score_before - Score_after` | Thêm transcript 2024 nhưng query 2023 vẫn trả đúng | Drop càng nhỏ càng tốt |
| **New query adaptability** | Hệ thống có trả lời tốt query mới dựa trên dữ liệu mới không | Chạy new queries trên updated corpus | Dùng Correct/F1/ROUGE-L hoặc win-rate trên new queries | Sau khi thêm 2024, hỏi 2024 Q1–Q4 và model trả đúng | Càng cao càng tốt |
| **Index / Update Token Cost ↓** | Chi phí indexing hoặc update bằng LLM | Đếm prompt tokens và completion tokens trong LLM-based indexing/update | `Total Token Cost = Prompt Tokens + Completion Tokens` | TG-RAG update ít token hơn GraphRAG vì chỉ update new time nodes và ancestors | Càng thấp càng tốt nếu quality giữ được |
| **Update Cost Ratio ↓** | Incremental update tiết kiệm bao nhiêu so với full rebuild | So sánh cost của incremental update với full rebuild | `Update Cost Ratio = Cost_incremental_update / Cost_full_rebuild` | Full rebuild 10M tokens, incremental 2M tokens → ratio = 0.2 | Ratio càng nhỏ càng hiệu quả |
| **Retrieval stability** | Evidence cho query cũ có bị nhiễu sau update không | So sánh top retrieved evidence trước/sau update | Có thể đo overlap top-k hoặc temporal evidence accuracy | Query 2023 vẫn retrieve transcript 2023, không bị transcript 2024 chen vào | Quan trọng khi corpus mới có facts gần nghĩa |

---

## 3.4. Công thức Stability Drop

```text
Stability Drop = Score_before_update - Score_after_update
```

Giải thích:

| Ký hiệu | Ý nghĩa |
|---|---|
| `Score_before_update` | Kết quả trên base queries trước khi thêm corpus mới |
| `Score_after_update` | Kết quả trên base queries sau khi thêm corpus mới |
| `Stability Drop` | Mức giảm performance sau update |

Ví dụ:

```text
Correct_before = 0.599
Correct_after = 0.587
Stability Drop = 0.599 - 0.587 = 0.012
```

Diễn giải:

- Drop chỉ `0.012` nghĩa là performance trên query cũ gần như ổn định sau khi thêm dữ liệu mới.
- Nếu drop lớn, corpus mới có thể làm nhiễu retrieval hoặc làm summaries bị lệch.

---

## 3.5. Công thức Update Cost Ratio

```text
Update Cost Ratio = Cost_incremental_update / Cost_full_rebuild
```

Giải thích:

| Ký hiệu | Ý nghĩa |
|---|---|
| `Cost_incremental_update` | Chi phí cập nhật incremental, ví dụ token/time/LLM calls |
| `Cost_full_rebuild` | Chi phí rebuild toàn bộ index/graph/reports |
| `Update Cost Ratio` | Tỷ lệ chi phí incremental so với full rebuild |

Ví dụ:

```text
Cost_full_rebuild = 10M tokens
Cost_incremental_update = 2M tokens
Update Cost Ratio = 2M / 10M = 0.2
```

Diễn giải:

```text
Incremental update chỉ tốn 20% chi phí so với rebuild toàn bộ.
```

---

# Nhóm 4 — Ablation Study Metrics

## 4.1. Ablation Study là gì?

**Ablation Study** không phải một metric đơn lẻ, mà là cách đánh giá bằng cách bỏ từng thành phần của mô hình để xem performance giảm ra sao.

Mục tiêu:

```text
Nếu bỏ một module mà metric giảm mạnh → module đó quan trọng.
```

Trong TG-RAG, paper ablate các thành phần chính:

- Temporal Retrieval,
- PPR Ranking,
- Temporal Indexing.

---

## 4.2. Bảng ablation

| Variant | Bỏ thành phần gì? | Metric quan sát | Cách đọc nếu performance giảm |
|---|---|---|---|
| **Full TG-RAG** | Không bỏ gì | Correct, Refusal, Incorrect, ROUGE-L, F1 | Kết quả chuẩn để so sánh |
| **w/o PPR Ranking** | Bỏ Personalized PageRank trong local retrieval | Correct/F1, retrieval path | Nếu giảm, PPR giúp graph propagation và entity ranking |
| **w/o Temporal Retrieval** | Bỏ lọc theo temporal scope `Tq` | Correct, Incorrect, Temporal Coverage | Nếu giảm mạnh, temporal filtering là thành phần lõi |
| **w/o Temporal Retrieval + PPR** | Bỏ cả temporal filtering và graph propagation | Correct/F1/ROUGE-L | Đo tác động khi mất cả graph relevance và temporal relevance |
| **w/o all Temporal Indexing** | Bỏ temporal graph, time hierarchy, time reports | Correct, F1, Temporal Coverage, Abstract QA | Nếu giảm mạnh, temporal indexing là nền biểu diễn cốt lõi |

---

## 4.3. Cách đọc ablation trong TG-RAG

Ví dụ paper báo cáo:

| Variant | Correct | Refusal | Incorrect | ROUGE-L | F1 |
|---|---:|---:|---:|---:|---:|
| Full TG-RAG | 0.599 | 0.191 | 0.210 | 0.493 | 0.490 |
| w/o PPR | 0.580 | 0.223 | 0.197 | 0.483 | 0.472 |
| w/o Temporal Retrieval | 0.382 | 0.423 | 0.195 | 0.376 | 0.356 |
| w/o Temporal Retrieval + PPR | 0.482 | 0.294 | 0.223 | 0.434 | 0.416 |
| w/o all Temporal Indexing | 0.381 | 0.458 | 0.161 | 0.359 | 0.345 |

Diễn giải:

- Bỏ **PPR** làm Correct giảm nhẹ: PPR có ích nhưng không phải yếu tố duy nhất.
- Bỏ **Temporal Retrieval** làm Correct giảm mạnh và Refusal tăng: hệ thống khó lấy đúng evidence trong temporal scope.
- Bỏ **all Temporal Indexing** làm performance thấp: temporal graph/time hierarchy/time reports là nền biểu diễn quan trọng.

---

## 4.4. Công thức đọc drop trong ablation

```text
Metric Drop = Metric_full_model - Metric_ablation_variant
```

Ví dụ:

```text
Correct_full = 0.599
Correct_without_temporal_retrieval = 0.382

Metric Drop = 0.599 - 0.382 = 0.217
```

Diễn giải:

```text
Bỏ temporal retrieval làm Correct giảm 0.217 điểm tuyệt đối.
```

---

# Nhóm 5 — Graph Build & Retrieval Diagnostics

## 5.1. Vì sao cần nhóm này?

Paper gốc không định nghĩa một metric đơn lẻ tên “graph build quality”. Thay vào đó, build/indexing được phản ánh qua cost, ablation và chất lượng QA downstream.

Khi triển khai thực tế (đặc biệt lúc tích hợp TurboQuant), nên tách nhóm diagnostic rõ hơn để trả lời 3 câu hỏi:

1. Build graph có nhanh và tiết kiệm hơn không?
2. Graph tạo ra có còn đúng/grounded không?
3. Retrieval có lấy đúng evidence theo temporal scope không?

Do đó cần đo riêng:

```text
Build có nhanh/tiết kiệm không?
Graph có đúng, grounded, đủ phủ không?
Evidence retrieval có đúng temporal scope và reasoning path không?
```

---

## 5.2. Layer A — Graph Build Efficiency

| Metric | Đo gì? | Công thức / cách tính | Ý nghĩa |
|---|---|---|---|
| **Indexing Time ↓** | Tổng thời gian build graph/index | `T_index = T_extract + T_graph + T_report + T_store` | Đánh giá chi phí build end-to-end |
| **Extraction Time per Chunk ↓** | Tốc độ extract fact theo chunk | `T_per_chunk = T_extract / N_chunks` | So sánh độ nhanh stage LLM extraction |
| **LLM Calls / Tokens ↓** | Chi phí gọi LLM khi build | Đếm `api_calls`, `prompt_tokens`, `completion_tokens` | Đo cost indexing/update |
| **Build Throughput ↑** | Mức xử lý chunk theo thời gian | `Throughput = N_chunks / T_extract` | Đo thông lượng build |
| **Peak VRAM ↓** | Bộ nhớ GPU đỉnh | Log từ GPU monitor | Đo lợi ích quantization |
| **Build Speedup ↑** | TurboQuant nhanh hơn baseline bao nhiêu | `Speedup = T_original / T_quantized` | Chỉ số optimization cốt lõi |

---

## 5.3. Layer B — Graph Construction Quality

| Metric | Đo gì? | Công thức / cách tính | Ý nghĩa |
|---|---|---|---|
| **Temporal Quadruple Validity ↑** | Tuple `(v1, v2, e, τ)` có hợp lệ không | `valid_quadruples / total_quadruples` | Đo chất lượng extraction lõi |
| **Timestamp Normalization Accuracy ↑** | Chuẩn hóa mốc thời gian đúng không | Rule/gold/manual check | Đo temporal correctness |
| **Evidence Grounding Rate ↑** | Fact có link về source chunk/doc không | `% facts có source_id/chunk_id` | Giảm risk hallucinated graph |
| **Duplicate Entity Rate ↓** | Mức trùng node entity chưa canonicalize | `duplicate_entities / total_entities` | Đo chất lượng merge entity |
| **Temporal Edge Coverage ↑** | Quan hệ có timestamp hợp lệ hay không | `edges_with_valid_time / total_edges` | Đo độ phủ temporal relation |

---

## 5.4. Layer C — Retrieval Diagnostics

| Metric | Đo gì? | Đo ra sao? | Công thức / cách tính | Ví dụ | Ý nghĩa |
|---|---|---|---|---|---|
| **Evidence Recall ↑** | Hệ thống có retrieve đủ gold evidence cần thiết không | Tỷ lệ gold evidence xuất hiện trong top-k retrieved evidence | `Recall@k = |Gold ∩ Retrieved@k| / |Gold|` | Query cần Q1/Q2/Q3 revenue, retrieve đủ 3 chunks → recall cao | Đo độ đầy đủ của evidence |
| **Evidence Precision ↑** | Retrieved evidence có ít nhiễu không | Tỷ lệ retrieved evidence thật sự liên quan | `Precision@k = |Relevant ∩ Retrieved@k| / |Retrieved@k|` | Retrieve 10 chunks, 7 chunks đúng temporal scope → precision = 0.7 | Đo độ sạch của context |
| **Temporal Evidence Accuracy ↑** | Evidence có đúng mốc thời gian không | Kiểm tra timestamp của retrieved evidence có thuộc `Tq` không | `TEA = số evidence có τ ∈ Tq / tổng evidence retrieved` | Query hỏi 2023 nhưng evidence từ 2024 → sai | Đặc biệt quan trọng cho TG-RAG |
| **Path Coverage ↑** | Multi-hop query có đủ reasoning path không | Kiểm tra các facts/edges trên reasoning path có trong context không | `Path Coverage = số required edges retrieved / tổng required edges` | Company A → Startup B → Product C cần đủ 2 edges | Đo khả năng hỗ trợ reasoning chain |
| **Context Efficiency ↑** | Context đưa vào LLM có gọn và hữu ích không | Tỷ lệ useful facts trên tổng token context | `Context Efficiency = số useful facts / tổng context tokens` | Ít tokens nhưng đủ evidence → efficiency cao | Hữu ích khi tối ưu context window |

---

## 5.5. Layer D — Graph Coverage / Structure

| Metric | Đo gì? | Công thức / cách tính | Ý nghĩa |
|---|---|---|---|
| **Document Coverage ↑** | Bao nhiêu doc đóng góp facts | `docs_with_facts / total_docs` | Đo độ phủ extraction theo tài liệu |
| **Chunk Coverage ↑** | Bao nhiêu chunk tạo entities/relations | `chunks_with_facts / total_chunks` | Đo độ phủ extraction theo chunk |
| **#Nodes / #Edges / #Time-nodes** | Quy mô graph | Đếm trong graph DB/export tables | Quan sát tình trạng graph quá nhỏ/quá nhiễu |
| **Isolated Node Ratio ↓** | Tỷ lệ node rời rạc | `isolated_nodes / total_nodes` | Phát hiện graph connectivity yếu |
| **Average Degree** | Mức kết nối trung bình | tùy directed/undirected definition | Đánh giá connectivity tổng thể |

---

## 5.6. Ví dụ Temporal Evidence Accuracy

Query:

```text
What was revenue from 2023 Q1 to Q3?
```

Temporal scope:

```text
Tq = {2023-Q1, 2023-Q2, 2023-Q3}
```

Retrieved evidence:

| Evidence | Timestamp | Đúng temporal scope? |
|---|---|---|
| Revenue Q1 2023 | 2023-Q1 | Có |
| Revenue Q2 2023 | 2023-Q2 | Có |
| Revenue Q3 2023 | 2023-Q3 | Có |
| Revenue Q4 2024 | 2024-Q4 | Không |

Công thức:

```text
TEA = 3 / 4 = 0.75
```

Diễn giải:

```text
75% retrieved evidence đúng temporal scope.
```

---

# Nhóm 6 — TurboQuant + TG-RAG Efficiency Metrics

## 6.1. Vì sao cần nhóm này?

TG-RAG có nhiều **LLM-heavy stages**:

- temporal quadruple extraction,
- time report generation,
- global retrieval atomic point extraction,
- final answer generation,
- LLM-as-a-Judge evaluation nếu chạy local.

TurboQuant có thể tối ưu tầng **LLM inference** bằng cách giảm latency, giảm VRAM và tăng throughput. Nhưng khi quantize model, cần kiểm tra xem chất lượng temporal QA có bị giảm không.

Do đó nhóm metric này phải đo cả:

```text
Efficiency gain
+
Quality retention
```

---

## 6.2. Bảng metric TurboQuant + TG-RAG

| Nhóm | Metric | Đo gì? | Đo ra sao? | Công thức / ví dụ |
|---|---|---|---|---|
| **Quality** | Correct / F1 / ROUGE-L | Chất lượng answer sau quantization | Chạy cùng benchmark TG-RAG với model gốc và model quantized | So sánh `Correct_fp16` vs `Correct_quantized` |
| **Temporal Quality** | Temporal Coverage | Quantization có làm mất khả năng xử lý temporal scope không | Chạy query nhiều quý/năm, kiểm tra answer có đủ mốc không | Query Q1–Q3 phải trả đủ Q1, Q2, Q3 |
| **Latency ↓** | End-to-end latency | Thời gian từ query đến final answer | Đo wall-clock time/query | `Latency = t_end - t_start` |
| **Throughput ↑** | Tokens/sec | Tốc độ sinh token | Output tokens chia generation time | `Tokens/sec = output_tokens / generation_time_seconds` |
| **VRAM usage ↓** | Peak GPU memory | Model quantized có giảm VRAM không | Dùng `nvidia-smi`, profiler, GPU logger | So sánh peak VRAM FP16 vs TurboQuant |
| **Indexing/update time ↓** | LLM-heavy indexing stages có nhanh hơn không | Đo thời gian extraction/report generation | `Speedup = Time_original / Time_quantized` |
| **Quality Retention ↑** | Mức giữ chất lượng sau quantization | Metric quantized chia cho metric original | `Quality Retention = Quality_quantized / Quality_original` |
| **Quality Drop ↓** | Mức giảm chất lượng tuyệt đối | Metric original trừ metric quantized | `Quality Drop = Quality_original - Quality_quantized` |

---

## 6.3. Công thức Latency

```text
Latency = t_end - t_start
```

| Ký hiệu | Ý nghĩa |
|---|---|
| `t_start` | Thời điểm bắt đầu xử lý query |
| `t_end` | Thời điểm sinh xong answer |
| `Latency` | Tổng thời gian xử lý một query |

Ví dụ:

```text
t_start = 0s
t_end = 6.2s
Latency = 6.2s
```

Nếu TurboQuant giảm latency từ `6.2s` xuống `3.8s`, nghĩa là inference nhanh hơn.

---

## 6.4. Công thức Throughput

```text
Tokens/sec = Number of generated tokens / Generation time
```

Ví dụ:

```text
Generated tokens = 380
Generation time = 10s
Tokens/sec = 380 / 10 = 38 tokens/sec
```

Diễn giải:

- Tokens/sec càng cao, model sinh càng nhanh.
- Cần đo trên cùng prompt, cùng output budget và cùng hardware để so sánh công bằng.

---

## 6.5. Công thức Speedup

```text
Speedup = Time_original / Time_quantized
```

Ví dụ:

```text
Time_original = 100s
Time_quantized = 50s
Speedup = 100 / 50 = 2×
```

Diễn giải:

```text
TurboQuant chạy nhanh gấp 2 lần ở stage đó.
```

---

## 6.6. Công thức Quality Retention

```text
Quality Retention = Quality_quantized / Quality_original
```

Ví dụ với F1:

```text
F1_original = 0.80
F1_quantized = 0.76
Quality Retention = 0.76 / 0.80 = 0.95 = 95%
```

Diễn giải:

```text
Model quantized giữ được 95% chất lượng F1 so với model gốc.
```

---

## 6.7. Công thức Quality Drop

```text
Quality Drop = Quality_original - Quality_quantized
```

Ví dụ:

```text
Correct_original = 0.599
Correct_quantized = 0.570
Quality Drop = 0.599 - 0.570 = 0.029
```

Diễn giải:

```text
Correct giảm 2.9 điểm phần trăm sau quantization.
```

---

## 6.8. Bảng quyết định khi apply TurboQuant

| Câu hỏi đánh giá | Metric cần đo | Tốt khi nào? | Ví dụ |
|---|---|---|---|
| TurboQuant có làm answer sai hơn không? | Correct, Incorrect, F1, ROUGE-L | Correct/F1 giữ gần model gốc; Incorrect không tăng mạnh | Correct retention ≥ 95% |
| TurboQuant có làm mất temporal reasoning không? | Temporal Coverage, Temporal Evidence Accuracy | Answer vẫn đủ mốc thời gian, đúng timeline | Query Q1–Q3 vẫn trả đủ 3 quý |
| TurboQuant có giúp chạy nhanh hơn không? | Latency, Throughput, Speedup | Latency giảm, tokens/sec tăng | 6.2s → 3.8s; 24 → 38 tok/s |
| TurboQuant có giảm tài nguyên không? | VRAM usage | Peak VRAM giảm rõ | 14GB → 8GB |
| TurboQuant có giúp indexing/update nhanh hơn không? | Indexing time, update time | Extraction/report generation nhanh hơn | Time report generation giảm 40% |
| Trade-off có đáng không? | Quality Retention + Speedup | Retention cao, speedup lớn | Retention 95%, speedup 2× |

---

## 6.9. Bổ sung để production-grade hơn

Để báo cáo mang tính production (không chỉ demo), nên bổ sung 4 nhóm sau:

1. **Tail latency**: p95/p99 latency (không chỉ mean).
2. **Generation responsiveness**: TTFT và tokens/sec tính riêng phần generation.
3. **Uncertainty estimation**: confidence interval bằng bootstrap cho win-rate và F1.
4. **Judge reliability**: judge disagreement rate khi dùng LLM-as-a-Judge.

### 6.9.1. p95/p99 Latency

Mean latency có thể đẹp nhưng che giấu outlier. Với hệ thống production, cần biết truy vấn chậm nhất nằm ở đâu.

| Metric | Đo gì? | Công thức / cách tính | Cách đọc |
|---|---|---|---|
| **Latency p95 ↓** | 95% request nhanh hơn hoặc bằng ngưỡng này | Lấy percentile 95 của phân phối latency | Thể hiện trải nghiệm đa số user |
| **Latency p99 ↓** | 99% request nhanh hơn hoặc bằng ngưỡng này | Lấy percentile 99 của phân phối latency | Bắt tail latency / trường hợp xấu |

Ví dụ:

```text
mean = 3.8s, p95 = 7.2s, p99 = 12.9s
```

Diễn giải:

- Trung bình nhanh, nhưng vẫn có một nhóm query chậm đáng kể.
- Khi so sánh model gốc vs TurboQuant, nên so cả mean + p95 + p99.

### 6.9.2. TTFT và Tokens/sec tách riêng generation

Trong pipeline RAG, độ trễ đầu ra đầu tiên và tốc độ sinh token phản ánh 2 cảm nhận khác nhau của người dùng.

| Metric | Đo gì? | Công thức / cách tính | Ý nghĩa |
|---|---|---|---|
| **TTFT ↓** | Time-to-first-token | `TTFT = t_first_token - t_request_start` | Độ phản hồi ban đầu |
| **Generation Throughput ↑** | Tốc độ sinh token sau khi đã bắt đầu stream | `Tokens/sec_gen = output_tokens / (t_last_token - t_first_token)` | Tốc độ đọc được của phần answer |

Lưu ý:

- Không trộn TTFT vào mẫu số throughput generation.
- Nếu chỉ tính `output_tokens / (t_end - t_start)`, metric sẽ bị ảnh hưởng mạnh bởi retrieval/context build.

### 6.9.3. Confidence Interval (Bootstrap) cho win-rate và F1

Khi báo cáo kết quả, nên có khoảng tin cậy để tránh kết luận từ dao động ngẫu nhiên.

| Metric | Cách bootstrap | Báo cáo |
|---|---|---|
| **Win-rate** | Resample theo query (with replacement) B lần, tính win-rate mỗi lần | Mean + 95% CI |
| **F1** | Resample theo query, tính macro/micro F1 mỗi lần | Mean + 95% CI |

Ví dụ báo cáo:

```text
Win-rate = 0.78 [95% CI: 0.73, 0.82]
F1 = 0.61 [95% CI: 0.58, 0.64]
```

Nếu hai hệ có CI chồng lấn nhiều, cần cẩn trọng khi nói “thắng rõ rệt”.

### 6.9.4. Judge Disagreement Rate

Khi dùng LLM-as-a-Judge (hoặc nhiều judge), cần đo mức bất đồng để đánh giá độ ổn định của quy trình chấm.

| Metric | Đo gì? | Công thức |
|---|---|---|
| **Judge Disagreement Rate ↓** | Tỷ lệ mẫu mà các judge không cùng kết luận | `Disagreement = số mẫu bất đồng / tổng mẫu` |

Ví dụ:

```text
2 judges, 200 câu hỏi, bất đồng 34 câu
Disagreement rate = 34 / 200 = 17%
```

Diễn giải:

- Nếu bất đồng cao, nên thêm adjudication pass hoặc rubric chặt hơn.
- Nên log các case bất đồng để phân tích lỗi theo loại query (temporal vs non-temporal).

---

# 7. Metric nào nên ưu tiên đưa vào slide?

Nếu thời lượng seminar ngắn, không nên đưa hết tất cả. Nên ưu tiên:

| Mục tiêu trình bày | Metric nên đưa |
|---|---|
| Giải thích paper TG-RAG đánh giá answer fact-based ra sao | Correct, Refusal, Incorrect, ROUGE-L, F1 |
| Giải thích abstract/global QA | Comprehensiveness, Diversity, Temporal Coverage, Overall Winner |
| Giải thích evolving corpus | Base performance, Stability after update, New query adaptability, Update Cost |
| Giải thích thành phần TG-RAG có tác dụng không | Ablation: w/o PPR, w/o Temporal Retrieval, w/o Temporal Indexing |
| Giải thích TurboQuant optimize gì | Latency, Throughput, VRAM, Indexing/update time, Quality Retention |
| Khi cần production-readiness | p95/p99 latency, TTFT, bootstrap CI, judge disagreement rate |

---

# 8. Làm rõ: TurboQuant can thiệp từng phần hay toàn bộ pipeline?

Kết luận ngắn:

- **Có thể can thiệp từng phần** (build-only hoặc query-only), không bắt buộc all-or-nothing.
- Nếu mục tiêu nghiên cứu là **"TurboQuant optimize TG-RAG end-to-end"**, nên chạy local LLM ở cả build + query để kết luận đầy đủ.

## 8.1. Can thiệp theo stage

| Chế độ chạy | TurboQuant can thiệp | Dùng khi nào |
|---|---|---|
| **Build-only local LLM** | Entity extraction, summarization, temporal/community report generation | Tối ưu thời gian indexing/update |
| **Query-only local LLM** | Final answer generation (local/global/naive query) | Tối ưu latency phục vụ inference |
| **Build + Query local LLM** | Toàn bộ LLM-heavy stages | Đánh giá end-to-end TurboQuant optimization |
| **Hybrid (judge external)** | Pipeline chính local, judge dùng model khác (Gemini/GPT) | Giảm bias khi đánh giá chất lượng |

## 8.2. Vì sao dễ cảm giác “cấu hình phức tạp”? 

Vì hệ thống tách nhiều lớp cấu hình:

- LLM backend/runtime cho generation (`best_model_func`, `cheap_model_func`),
- embedding backend/runtime (`embedding_provider`, `embedding_model`, `embedding_device`),
- mode chạy (build/query/eval),
- judge model (nếu có).

Nên tách rõ 3 biến độc lập trong thí nghiệm:

1. **LLM chính** (TurboQuant vs baseline),
2. **Embedding** (giữ cố định),
3. **Judge** (giữ cố định hoặc dùng đa-judge có báo cáo disagreement).

## 8.3. Khuyến nghị setup thực nghiệm tối giản

```text
Nếu mục tiêu: TurboQuant optimize TG-RAG
→ Chạy local LLM cho build + query
→ Giữ embedding cố định
→ Judge dùng external model để chấm độc lập
→ Báo cáo cả quality + efficiency + production-grade metrics
```

## 8.4. Tài liệu thao tác CLI và xuất metric chi tiết

Để chạy thực nghiệm theo mode can thiệp và xuất metric nhất quán, xem thêm:

- `md/runbooks/turboquant_intervention_modes_cli.md`
	- Hướng dẫn can thiệp theo 4 mode: Build-only, Query-only, Build+Query, Hybrid.
	- Có lệnh CLI cụ thể cho `build_graph.py`, `query_graph.py`, `scripts/eval/run_batch_queries.py`.

- `md/metrics/tgrag_metrics_execution_runbook.md`
	- Quy trình sinh prediction, judge, non-LLM metrics.
	- Cách tính p95/p99 latency, TTFT, generation tokens/sec.
	- Cách tính bootstrap CI và judge disagreement rate.

---

# 9. Script nói tổng quan cho phần metric

Bạn có thể trình bày như sau:

> Khi đánh giá TG-RAG, paper không chỉ đo answer đúng hay sai. Với Specific QA, paper dùng Correct, Refusal và Incorrect để đánh giá factual accuracy bằng LLM-as-a-Judge, kết hợp ROUGE-L và F1 để đo lexical overlap. Điểm quan trọng là Correct trong TG-RAG không chỉ đúng về nội dung, mà còn phải đúng temporal scope.
>
> Với Abstract QA, do câu trả lời là dạng tổng hợp xu hướng hoặc phân tích dài, paper dùng pairwise LLM judge theo ba tiêu chí: Comprehensiveness, Diversity và Temporal Coverage, sau đó chọn Overall Winner. Temporal Coverage là metric đặc biệt quan trọng vì nó đo answer có bao phủ đúng timeline, years, quarters hoặc events được hỏi không.
>
> Ngoài chất lượng answer, paper còn thiết kế incremental evaluation. Corpus được chia thành base corpus và new corpus. Hệ thống được test trên base queries trước update, base queries sau update và new queries sau update. Cách đánh giá này giúp đo cả stability và adaptability khi knowledge evolves.
>
> Khi tích hợp TurboQuant, ta cần thêm metric efficiency như latency, throughput, VRAM usage và indexing/update time. Tuy nhiên, tối ưu tốc độ không đủ; phải đo Quality Retention để đảm bảo model quantized vẫn giữ được chất lượng temporal QA, đặc biệt là Correct và Temporal Coverage.

---

# 10. Tài liệu tham khảo

- TG-RAG paper: **RAG Meets Temporal Graphs: Time-Sensitive Modeling and Retrieval for Evolving Knowledge**, arXiv:2510.13590.
- Các nhóm metric paper gốc: Specific QA metrics, Abstract QA pairwise judge, Incremental Evaluation, Index/Update Token Cost, Ablation Study.
- Các nhóm metric mở rộng trong tài liệu này: Retrieval Quality diagnostics và TurboQuant Efficiency / Quality Retention.
