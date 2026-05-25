# Debug local LLM, TurboQuant và build graph

Ngày rà soát: 2026-05-22.

File này là bản viết lại có dấu, đã bỏ phần không dấu lặp lại. Cấu trúc mới đi theo luồng: tiêu chí so sánh, kết quả hiện tại, giải thích lỗi theo TH, bằng chứng source/log/output, ghi chú từ tài liệu web, và lệnh chạy đúng để áp dụng TurboQuant vào local LLM.

## 1. Kết luận ngắn

Nếu mục tiêu là chạy đúng TurboQuant local LLM để build graph, nên chạy từ repo:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
```

và start server từ:

```text
/home/guest/Projects/Research/llama-cpp-turboquant
```

Cấu hình local 7B nên thử lại trước:

```text
Model:        qwen2.5 7B Q8 GGUF
llama-server: -c 65536 --parallel 2 --n-predict 2048 -ctk q8_0 -ctv turbo3 -fa on
build_graph:  --local_llm_backend turboquant --llm_max_async 2 --llm_timeout 900
embedding:    Ollama nomic-embed-text tại http://localhost:11434
```

Không nên lấy TH11A làm bằng chứng TurboQuant nhanh, vì TH11A thực tế dùng Gemini. TH11A chỉ start llama-server và chạy healthcheck, nên GPU/VRAM bị chiếm nhưng build graph không gọi local Qwen.

TH5 là kết quả full 384 docs sạch nhất hiện có: Turboquant repo + Gemini API + Ollama embedding, chạy xong 384 docs. Nhưng TH5 không phải local LLM.

TH1/TH2 là local 7B qua llama-server, nhưng cấu hình -c 65536 --parallel 4 làm mỗi slot chỉ còn khoảng 16k context. Vì vậy community report bị lỗi context ở 10/50 docs. Nếu chạy full 384 bằng local 7B, cần giảm --parallel xuống 2 hoặc 1.

TH11A 384 fail do Ollama embedding nhận input quá dài, không phải do KV/cache của llama-server. Cần thêm truncate/cap content trước khi gọi embedding.

## 2. Repo, commit và phạm vi so sánh

| Repo | Vai trò | Trạng thái nên hiểu |
|---|---|---|
| /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant | Repo nên dùng để chạy lại TurboQuant local LLM | HEAD hiện tại 61ac8e1ebb34c43e71ff568a0f2114b4ac586138; có CLI runtime override rõ ràng |
| /home/guest/Projects/Research/Temporal-GraphRAG | Repo Original trong TH2/TH4/TH6 | Không phải upstream sạch tuyệt đối vì worktree có nhiều source đã sửa |
| /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2 | Worktree để tái hiện TH11A/TH11B | Commit c1f1ea2dd87db4addc1469197d12593275b37c76; có healthcheck gây nhầm backend |
| /home/guest/Projects/Research/llama-cpp-turboquant | Fork llama.cpp dùng để start llama-server TurboQuant | Nơi chạy ./build/bin/llama-server với -ctk, -ctv |

Lưu ý khi viết báo cáo: TH2/TH4/TH6 nên ghi là Original worktree đã chỉnh, không nên ghi là Original upstream sạch.

## 3. Các tiêu chí so sánh

| Tiêu chí | Ý nghĩa | Đọc ở đâu | Cách hiểu |
|---|---|---|---|
| Backend thực tế | Xác định build graph thật sự gọi Gemini, Ollama hay local llama-server | kv_store_llm_response_cache.json, build log dòng runtime, server log POST /v1/chat/completions | Tiêu chí quan trọng nhất vì nhìn GPU/VRAM hoặc healthcheck có thể nhầm |
| Độ hoàn tất | Run có persist đủ graph/vector/docs hay chỉ dừng ở cache | kv_store_full_docs.json, kv_store_text_chunks.json, vdb_entities.json, vdb_relations.json, GraphML | Nếu chỉ có cache thì run chưa hoàn tất, không dùng để so sánh chất lượng graph |
| Thời gian | Tổng thời gian và thời gian từng stage | Build log timer, elapsed | Biết bottleneck là LLM extraction, community, embedding hay persist |
| Quy mô input | Số docs và số chunks | Build log, kv_store_text_chunks.json | Ở các TH này chunk gần như giống nhau: 1 doc 5 chunks, 10 docs 39 chunks, 50 docs 199 chunks, 100 docs 391 chunks, 384 docs 1462 chunks |
| Quy mô graph | Số entities, relations, communities, graph nodes/edges | vdb_entities.json, vdb_relations.json, kv_store_community_reports.json, graph_chunk_entity_relation.graphml | Dùng để so chất lượng/độ giàu graph, nhưng phải loại run có report lỗi |
| Lỗi context LLM | Prompt vượt context của local LLM hoặc slot server | Server log và kv_store_community_reports.json | Thường do -c, --parallel, prompt community quá dài |
| Lỗi embedding | Text đưa vào embedding vượt context embedding model | Build log lỗi Ollama embedding API error, source embedding.py | Thường do entity/relation description quá dài sau merge |
| Sử dụng TurboQuant đúng | Có thật sự đi qua llama-server với KV TurboQuant không | CLI server có -ctk/-ctv; build CLI có --local_llm_backend turboquant --base_url http://localhost:8080/v1 | TH3/TH4 Ollama native và TH5/TH6 Gemini không tính là TurboQuant local LLM |
| Tính mở rộng 384 docs | Có chạy full ECT-QA 384 docs ổn không | Output 384 docs và log 384 docs | Chỉ TH5 thành công đầy đủ trong dữ liệu hiện có |
| Nguồn lỗi từ source/CLI/config | Lỗi do code, do config, hay do lệnh start server | Source line, config, CLI, logs | Giúp biết cần sửa code hay chỉ sửa lệnh chạy |

## 4. Bảng kịch bản và trạng thái hiện tại

| TH | Repo | Backend theo kịch bản | Backend thực tế | Model | Docs có dữ liệu | Trạng thái |
|---:|---|---|---|---|---|---|
| TH1 | Turboquant | llama-server TurboQuant | local llama-server OpenAI-compatible | Qwen2.5 7B Q8 GGUF | 1, 10, 50, 100 | 1/10/50 xong; 100 incomplete |
| TH2 | Original worktree | llama-server TurboQuant | local llama-server OpenAI-compatible | Qwen2.5 7B Q8 GGUF | 1, 10, 50 | 1/10/50 xong; không có 100 |
| TH3 | Turboquant | Ollama | Ollama native | qwen2.5:7b-instruct | 1, 10, 50 | xong đến 50; không phải TurboQuant |
| TH4 | Original worktree | Ollama | Ollama native | qwen2.5:7b-instruct | 1, 10, 50 | xong đến 50; không phải TurboQuant |
| TH5 | Turboquant | Gemini API | Gemini API | gemini-2.5-flash-lite | 1, 10, 50, 100, 384 | 384 xong đầy đủ |
| TH6 | Original worktree | Gemini API | Gemini API | gemini-2.5-flash-lite | 1, 10, 50, 100, 384 | 100 xong; 384 incomplete |
| TH7 | Turboquant | llama-server TurboQuant 14B | chưa có log đúng tên | Qwen3 14B GGUF | chưa thấy | chưa so sánh được |
| TH8 | Original worktree | llama-server TurboQuant 14B | chưa có log đúng tên | Qwen3 14B GGUF | chưa thấy | chưa so sánh được |
| TH9 | Turboquant | Ollama 14B | chưa có log đúng tên | qwen3:14b | chưa thấy | chưa so sánh được |
| TH10 | Original worktree | Ollama 14B | chưa có log đúng tên | qwen3:14b | chưa thấy | chưa so sánh được |
| TH11A | worktree c1f1ea2 | config gốc | Gemini API, không phải local LLM | gemini-2.5-flash-lite | 1, 5, 10, 50, 100, 384 | 100 xong; 384 fail embedding |
| TH11B | worktree c1f1ea2 | ép OpenAI/local | local llama-server | Qwen3 14B Q5 alias qwen3-14b-instruct | 1, 5 | 1 xong; 5 incomplete |

## 5. Kết quả hiện tại theo tiêu chí

### 5.1 Bảng định lượng chính

| TH | Docs | Hoàn tất | Thời gian | Chunks | LLM cache | Entities | Relations | Communities | Graph nodes | Graph edges | Ghi chú |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| TH1 | 1 | Có | 142.73s | 5 | 11 | 75 | 66 | 2 | 84 | 131 | local 7B |
| TH1 | 10 | Có, nhưng có lỗi report | 806.03s | 39 | 98 | 446 | 583 | 16 | 493 | 1034 | 4 community reports lỗi context |
| TH1 | 50 | Có, nhưng có lỗi report | 3283.03s | 199 | 451 | 2394 | 2795 | 75 | 2588 | 4992 | 28 community reports lỗi context |
| TH1 | 100 | Không hoàn tất | n/a | 391 loaded | 24 | n/a | n/a | n/a | n/a | n/a | log dừng sớm, output chỉ có cache |
| TH2 | 1 | Có | 84.54s | 5 | 12 | 83 | 81 | 2 | 94 | 155 | local 7B |
| TH2 | 10 | Có, nhưng có lỗi report | 769.63s | 39 | 95 | 566 | 684 | 22 | 598 | 1199 | 8 community reports lỗi context |
| TH2 | 50 | Có, nhưng có lỗi report | 3303.62s | 199 | 442 | 2589 | 3010 | 69 | 2788 | 5419 | 30 community reports lỗi context |
| TH3 | 1 | Có | 129.81s | 5 | 14 | 77 | 72 | 4 | 85 | 145 | Ollama native |
| TH3 | 10 | Có | 985.14s | 39 | 97 | 290 | 373 | 18 | 365 | 680 | Ollama native |
| TH3 | 50 | Có | 3768.17s | 199 | 451 | 1537 | 2103 | 48 | 1923 | 3885 | Ollama native |
| TH4 | 1 | Có | 81.06s | 5 | 12 | 53 | 45 | 4 | 67 | 92 | Ollama native |
| TH4 | 10 | Có | 1064.18s | 39 | 94 | 364 | 424 | 20 | 458 | 801 | Ollama native |
| TH4 | 50 | Có | 6035.75s | 199 | 448 | 1499 | 2216 | 42 | 1934 | 4039 | chậm nhất nhóm 7B |
| TH5 | 1 | Có | 107.00s | 5 | 15 | 128 | 64 | 12 | 133 | 128 | Gemini API |
| TH5 | 10 | Có | 363.12s | 39 | 71 | 555 | 550 | 47 | 588 | 904 | Gemini API |
| TH5 | 50 | Có | 1561.96s | 199 | 296 | 2266 | 2830 | 110 | 2454 | 4614 | Gemini API |
| TH5 | 100 | Có | 3198.16s | 391 | 567 | 4645 | 5278 | 173 | 5150 | 8723 | Gemini API |
| TH5 | 384 | Có | 12779.23s | 1462 | 1999 | 14577 | 19013 | 507 | 16214 | 31069 | full dataset thành công |
| TH6 | 1 | Có | 124.70s | 5 | 15 | 128 | 64 | 12 | 133 | 128 | Gemini API |
| TH6 | 10 | Có | 431.44s | 39 | 75 | 571 | 559 | 47 | 605 | 918 | Gemini API |
| TH6 | 50 | Có | 1817.49s | 199 | 296 | 2312 | 2841 | 110 | 2499 | 4644 | Gemini API |
| TH6 | 100 | Có | 3837.87s | 391 | 570 | 4507 | 5295 | 175 | 5019 | 8744 | Gemini API |
| TH6 | 384 | Không hoàn tất | n/a | 1462 loaded, khoảng 931 progressed | 931 | n/a | n/a | n/a | n/a | n/a | output chỉ có cache |
| TH11A | 1 | Có | 86.33s | 5 | 15 | 128 | 64 | 12 | 133 | 128 | thực tế Gemini |
| TH11A | 5 | Có | 154.56s | 19 | 38 | 353 | 296 | 26 | 379 | 518 | thực tế Gemini |
| TH11A | 10 | Có | 195.97s | 39 | 75 | 571 | 559 | 47 | 605 | 918 | thực tế Gemini |
| TH11A | 50 | Có | 636.82s | 199 | 296 | 2266 | 2830 | 110 | 2454 | 4614 | thực tế Gemini |
| TH11A | 100 | Có | 1126.49s | 391 | 568 | 4576 | 5282 | 171 | 5090 | 8765 | thực tế Gemini |
| TH11A | 384 | Fail | n/a | 1462 | 1627 | 0 persisted | 0 persisted | 0 persisted | 15988 GraphML | 30844 GraphML | fail ở Ollama embedding |
| TH11B | 1 | Có | 442.59s | 5 | 12 | 79 | 28 | 7 | 84 | 58 | local 14B Q5 thật |
| TH11B | 5 | Không hoàn tất | n/a | 19 loaded, khoảng 4 progressed | 9 | 0 persisted | 0 persisted | 0 persisted | 0 | 0 | quá chậm hoặc bị dừng sớm |

### 5.2 So sánh nhanh/chậm ở mốc 50 docs

| Nhóm | 50 docs | Nhận xét |
|---|---:|---|
| TH5 TQ + Gemini | 1561.96s | Nhanh và sạch nhất trong nhóm có 50 docs |
| TH11A c1 + Gemini | 636.82s | Rất nhanh vì concurrency cao hơn, nhưng 384 fail embedding; không phải local LLM |
| TH1 TQ + local 7B TurboQuant | 3283.03s | Local thật, nhưng community reports có lỗi context |
| TH2 Original + local 7B TurboQuant | 3303.62s | Tương tự TH1, có lỗi context |
| TH3 TQ + Ollama 7B | 3768.17s | Ollama native, không TurboQuant |
| TH4 Original + Ollama 7B | 6035.75s | Chậm nhất nhóm 7B |
| TH11B local 14B Q5 | chưa hoàn tất 5 docs | 1 doc đã 442.59s, không phù hợp chạy ngay 384 |

Kết luận về tốc độ:

- Nhanh nhất không đồng nghĩa đúng TurboQuant. TH11A nhanh nhưng là Gemini.
- Local TurboQuant 7B nhanh hơn Ollama native trong TH3/TH4, nhưng bị lỗi context do cấu hình server.
- 14B Q5 local chậm hơn 7B rõ rệt.
- I/O không phải bottleneck chính. Timer logs cho thấy persist chỉ vài giây, còn LLM extraction/community chiếm hàng nghìn giây.

## 6. Giải thích lỗi theo từng TH

### 6.1 TH1/TH2: build xong nhưng community reports bị lỗi context

Lệnh server TH1/TH2 dùng:

```text
-c 65536 --parallel 4 --n-predict 4096
```

Vấn đề nằm ở --parallel 4. Log server thực tế cho thấy mỗi slot chỉ còn khoảng 16384 tokens. Vì vậy prompt community report dài hơn 16k sẽ bị lỗi context.

Nguồn lỗi:

- CLI server: -c 65536 --parallel 4.
- Không phải do chunk size/overlap, vì số chunks giống nhau giữa nhiều TH.
- Không phải do logging/I/O, vì lỗi nằm trong server log và nội dung community report.

File cần đọc:

```text
Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_7b_p4c64k_20260522_105607.log
Temporal-GraphRAG/logs/llama_server/cmp_orig_turbo_7b_p4c64k_20260522_121901.log
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_050docs/kv_store_community_reports.json
Temporal-GraphRAG/outputs/build_graph/cmp_orig_turbo_7b_p4c64knp4096_050docs/kv_store_community_reports.json
```

Cách xử lý:

- Giảm server slots: dùng --parallel 2 hoặc --parallel 1.
- Đồng bộ build concurrency: --llm_max_async phải bằng hoặc nhỏ hơn --parallel.
- Giảm output budget: thử --n-predict 2048 thay vì 4096 để giảm thời gian decode.
- Nếu vẫn lỗi, giảm input community report bằng config/prompt, hoặc tắt community summary khi build local rồi tạo community reports bằng backend context lớn hơn.

### 6.2 TH1 100 docs: incomplete

TH1 100 docs có log/output nhưng không phải kết quả hoàn chỉnh:

```text
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_100docs.log
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_100docs
```

Dấu hiệu:

- Log có loaded 100 docs, new chunks 391.
- Output chỉ có cache khoảng 24 entries.
- Không có đủ full docs/vector/graph final.
- Không thấy traceback rõ trong phần log hiện có.

Kết luận: đây là run bị dừng sớm hoặc bị ngắt, không đủ bằng chứng để kết luận là lỗi source. Không nên dùng TH1 100 để so sánh chất lượng graph.

### 6.3 TH3/TH4: không phải TurboQuant

TH3/TH4 dùng Ollama native:

```text
--local_llm_backend ollama
--base_url http://localhost:11434
```

Vì vậy:

- Không đi qua llama-server của llama-cpp-turboquant.
- Không dùng KV cache -ctk/-ctv turbo3.
- Không có server log POST /v1/chat/completions từ llama-server.

File cần đọc:

```text
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_ollama_7b_api_050docs.log
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_ollama_7b_api_050docs/kv_store_llm_response_cache.json
Temporal-GraphRAG/outputs/build_graph/cmp_orig_ollama_7b_api_050docs/kv_store_llm_response_cache.json
```

Kết luận: TH3/TH4 hữu ích để so với Ollama native, nhưng không chứng minh TurboQuant.

### 6.4 TH5/TH6: Gemini API, không phải local LLM

TH5/TH6 dùng Gemini:

```text
--provider gemini
--model gemini-2.5-flash-lite
```

TH5 384 docs là kết quả hoàn chỉnh tốt nhất:

```text
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_gemini_api_384docs.log
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_gemini_api_384docs
```

TH6 384 không hoàn tất:

```text
Temporal-GraphRAG/logs/build_graph/cmp_orig_gemini_api_384docs.log
Temporal-GraphRAG/outputs/build_graph/cmp_orig_gemini_api_384docs
```

Dấu hiệu TH6 384 incomplete:

- Cache có khoảng 931 entries.
- Output không có đủ kv_store_full_docs.json, kv_store_text_chunks.json, vector stores và GraphML final đầy đủ.
- Log dừng giữa quá trình, không đủ bằng chứng kết luận nguyên nhân chính.

Kết luận: TH5 có thể dùng làm mốc tốc độ/chất lượng cloud API; TH6 384 không dùng làm mốc full run.

### 6.5 TH11A: vì sao có VRAM nhưng vẫn là Gemini?

TH11A start llama-server Qwen3 14B Q5, nên GPU/VRAM bị chiếm. Nhưng build graph vẫn dùng Gemini.

Bằng chứng source:

- [build_graph.py TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/build_graph.py:42) có hàm healthcheck xac_nhan_turboquant.
- [build_graph.py TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/build_graph.py:67) gọi healthcheck ngay khi chạy file.
- [config.yaml TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/configs/config.yaml:14) đặt building.provider là gemini.
- [config.yaml TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/configs/config.yaml:15) đặt building.model là gemini-2.5-flash-lite.
- [build_graph.py TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/build_graph.py:381) gọi create_temporal_graphrag_from_config với config_type là building.
- [build.py TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/src/build.py:157) load config rồi lấy provider/model từ block building.
- [config_loader.py TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/src/config/config_loader.py:48) chỉ lấy config theo config_type.

Bằng chứng output:

```text
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_050docs_20260522_204618/kv_store_llm_response_cache.json
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_384docs_20260522_204618/kv_store_llm_response_cache.json
```

Cache ghi model gemini-2.5-flash-lite. Vì vậy TH11A không phải local LLM.

### 6.6 TH11A 384: lỗi Ollama embedding context

Log lỗi:

```text
Ollama embedding API error 500: input length exceeds the context length
```

Source hiện tại lấy content rồi đưa nguyên vào embedding:

- [vector_nanovectordb.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/vector_nanovectordb.py:107) lấy contents từ v content.
- [vector_nanovectordb.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/vector_nanovectordb.py:120) gọi embedding_func theo batch.
- [embedding.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/embedding.py:118) định nghĩa ollama_embedding.
- [embedding.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/embedding.py:140) lặp từng text.
- [embedding.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/embedding.py:146) gọi endpoint /api/embeddings.
- [embedding.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/embedding.py:150) raise lỗi nếu Ollama trả status khác 200.

Nguyên nhân thực tế trong output TH11A 384:

- Có entity description quá dài, ví dụ node 2023 khoảng 29523 ký tự.
- Ollama nomic-embed-text trong model library đang ghi context window 2K.
- Source không truncate content trước khi gọi embedding.

File cần đọc:

```text
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/build_graph/th11a_c1_original_384docs_20260522_204618.log
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_384docs_20260522_204618/graph_chunk_entity_relation.graphml
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_384docs_20260522_204618/kv_store_llm_response_cache.json
```

Cách xử lý:

- Truncate/cap content trước khi gọi embedding.
- Log top-N content dài nhất khi embedding fail.
- Có thể chuyển từ endpoint legacy /api/embeddings sang /api/embed và dùng truncate, nhưng cần cân nhắc vì truncate âm thầm có thể làm mất thông tin.
- Tốt hơn: cap description sau bước merge entity/relation, ví dụ giới hạn entity/relation description còn 2048 hoặc 4096 tokens trước embedding.

### 6.7 TH11B: đúng local 14B nhưng quá chậm

TH11B ép config building.provider sang openai và model sang qwen3-14b-instruct. Đây mới là run local 14B thật.

File cần đọc:

```text
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/configs_runtime/th11b_c1_openai14b_20260522_211255.yaml
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11b_c1_openai14b_001docs_20260522_211255/kv_store_llm_response_cache.json
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/llama_server/srv_th11_c1_14bq5_top_level_20260522_204437.log
```

Kết quả:

- 1 doc mất 442.59s.
- 5 docs chưa hoàn tất.
- Server Qwen3 14B Q5 decode trung bình khoảng 29 tok/s.

Kết luận: TH11B chứng minh local 14B chạy đúng, nhưng không phù hợp để chạy ngay 384 docs nếu mục tiêu là nhanh.

### 6.8 TH11 server 14B Q8: lỗi OOM KV cache

Server log Q8:

```text
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/llama_server/srv_th11_c1_14b_top_level_20260522_204437.log
```

Lỗi chính:

```text
cudaMalloc failed: out of memory
failed to allocate buffer for kv cache
failed to create context
```

Nguyên nhân:

- Qwen3 14B Q8 nặng khoảng 14.61 GiB.
- Cần thêm KV cache khoảng 1.86 GiB ở c32768.
- GPU còn khoảng 15 GiB free không đủ cho cả model weights và KV.

Cách xử lý:

- Dùng Qwen3-14B-Q5_0.gguf thay vì Q8.
- Giữ -c 32768, --parallel 1 trước.
- Nếu vẫn OOM, giảm -c hoặc giảm GPU layers, nhưng giảm context sẽ tăng nguy cơ lỗi community prompt.

## 7. Ghi chú từ tài liệu web

### 7.1 llama-server và context/parallel

Tài liệu llama.cpp server nói llama-server có OpenAI-compatible chat completions, parallel decoding và continuous batching. Các tham số quan trọng gồm:

- -c hoặc --ctx-size: kích thước prompt context.
- -n hoặc --n-predict: số token sinh ra.
- -fa hoặc --flash-attn: bật flash attention.
- -ctk hoặc --cache-type-k: kiểu KV cache cho K.
- -ctv hoặc --cache-type-v: kiểu KV cache cho V.
- -ngl hoặc --n-gpu-layers: số layer offload lên GPU.

Điều quan trọng với benchmark này: log server mới là nguồn xác nhận context thực tế theo slot. Với TH1/TH2, dù CLI ghi -c 65536, log cho thấy slot context chỉ khoảng 16384 khi chạy parallel 4. Vì vậy khi ước lượng context phải đọc server log, không chỉ nhìn CLI.

Nguồn: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md

### 7.2 TurboQuant: đây là KV cache compression, không phải đổi model GGUF

Tài liệu/fork TurboQuant mô tả TurboQuant là kiểu nén KV cache thêm vào llama.cpp, dùng các cache type như turbo3/turbo4. Cách dùng điển hình là truyền cache type cho K/V khi start llama-server.

Điểm cần hiểu:

- Model GGUF vẫn là model Q8/Q5/Q4 bình thường.
- TurboQuant áp dụng lên KV cache lúc inference qua -ctk và -ctv.
- K precision ảnh hưởng attention routing nhiều hơn V, nên cấu hình an toàn thường giữ K cao hơn, ví dụ -ctk q8_0 -ctv turbo3 hoặc turbo4.
- Cấu hình symmetric -ctk turbo3 -ctv turbo3 tiết kiệm hơn nhưng cần tự validate chất lượng.
- Với CUDA, nên benchmark lại vì tài liệu cộng đồng ghi một số đường mixed q8_0 x turbo cần xác minh theo backend/hardware.

Nguồn:

- https://github.com/TheTom/turboquant_plus
- https://github.com/TheTom/turboquant_plus/blob/main/docs/papers/asymmetric-kv-compression.md
- https://github.com/ggml-org/llama.cpp/discussions/20969

Thiết lập thực dụng cho repo hiện tại:

```text
7B Q8:  -ctk q8_0 -ctv turbo3
14B Q5: -ctk q8_0 -ctv turbo3
```

Sau khi có baseline ổn, mới thử:

```text
-ctk q8_0 -ctv turbo4   # chất lượng an toàn hơn turbo3 nhưng tiết kiệm ít hơn
-ctk turbo3 -ctv turbo3 # tiết kiệm nhiều hơn nhưng phải tự kiểm chất lượng
```

### 7.3 Ollama embedding và lỗi context

Tài liệu Ollama API mới khuyến nghị endpoint /api/embed. Endpoint này có tham số truncate, mặc định true, dùng để cắt input vượt context window. Nếu truncate false thì trả lỗi.

Repo hiện tại đang gọi endpoint legacy /api/embeddings bằng payload model + prompt. Khi input quá dài, Ollama trả lỗi context như TH11A 384.

Ngoài ra trang model Ollama của nomic-embed-text ghi context window là 2K trong Ollama library. Vì vậy entity description dài hàng chục nghìn ký tự chắc chắn có rủi ro vượt context.

Nguồn:

- https://docs.ollama.com/api/embed
- https://ollama.com/library/nomic-embed-text

Cách xử lý trong code:

- Truncate nội dung trước khi gọi embedding.
- Đổi sang /api/embed và truyền truncate true nếu chấp nhận cắt âm thầm.
- Tốt nhất là vừa giới hạn description ở graph layer, vừa log các content quá dài.

### 7.4 GraphRAG indexing vốn tốn LLM và dễ sinh prompt dài

Tài liệu Microsoft GraphRAG nói pipeline indexing gồm entity extraction, relationship extraction, community detection, community summaries/reports, và embeddings. Standard GraphRAG dùng LLM cho entity extraction, relationship extraction, summarization và community reports. Tài liệu cũng có config max_input_length cho community reports và batch_max_tokens cho embeddings.

Điều này khớp với log ở đây:

- Thời gian chủ yếu nằm ở LLM extraction và community reports.
- Community report prompt dễ dài vì gom nhiều entity/relationship descriptions.
- Embedding fail có thể xảy ra nếu entity_description hoặc community_full_content vượt context embedding.

Nguồn:

- https://microsoft.github.io/graphrag/index/overview/
- https://microsoft.github.io/graphrag/index/methods/
- https://microsoft.github.io/graphrag/config/yaml/

## 8. Cấu hình và lệnh chạy đúng để test lại TurboQuant local LLM

### 8.1 Cấu hình khuyến nghị chính: 7B Q8, p2/c64k/np2048

Mục tiêu: tránh lỗi TH1/TH2 do per-slot context 16k, nhưng vẫn giữ concurrency 2 để không quá chậm.

Start server:

```bash
tmux new -s srv_tq_turbo_7b_p2c64k_np2048
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

RUN_ID=$(date +%Y%m%d_%H%M%S)
mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np2048 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 65536 \
  --parallel 2 \
  --n-predict 2048 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_7b_p2c64k_np2048_${RUN_ID}.log
```

Build graph:

```bash
tmux new -s bld_tq_turbo_7b_p2c64k_np2048
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

mkdir -p logs/build_graph outputs/build_graph

for D in 1 10 50 100 384; do
  L=$(printf '%03ddocs' "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_turbo_7b_p2c64knp2048_${L} \
    --model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np2048 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider ollama \
    --embedding_base_url http://localhost:11434 \
    --num_docs "$D" \
    --llm_max_async 2 \
    --llm_timeout 900 \
    2>&1 | tee logs/build_graph/cmp_tq_turbo_7b_p2c64knp2048_${L}.log
done
```

Trong build log phải thấy:

```text
runtime local_llm_backend=turboquant
provider=openai
llm_base_url=http://localhost:8080/v1
embedding_provider=ollama
embedding_base_url=http://localhost:11434
```

Nếu 50 docs vẫn có community context errors, chuyển sang cấu hình an toàn hơn.

### 8.2 Cấu hình an toàn nhất cho context: 7B Q8, p1/c64k/np2048

Start server chỉ khác:

```text
--parallel 1
```

Build graph chỉ khác:

```text
--llm_max_async 1
```

Cấu hình này chậm hơn nhưng giảm rủi ro lỗi community report vì mỗi request có nhiều context hơn.

### 8.3 Cấu hình 14B local: chỉ dùng Q5, không dùng Q8 trên GPU hiện tại

Start server 14B Q5:

```bash
tmux new -s srv_tq_turbo_14bq5_p1c32k_np2048
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

RUN_ID=$(date +%Y%m%d_%H%M%S)
mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/Qwen3-14B-Q5_0.gguf \
  --alias qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p1-np2048 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 1 \
  --n-predict 2048 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_14bq5_p1c32k_np2048_${RUN_ID}.log
```

Build graph 14B Q5:

```bash
tmux new -s bld_tq_turbo_14bq5_p1c32k_np2048
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

mkdir -p logs/build_graph outputs/build_graph

for D in 1 5 10 50; do
  L=$(printf '%03ddocs' "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_p1c32knp2048_${L} \
    --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p1-np2048 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider ollama \
    --embedding_base_url http://localhost:11434 \
    --num_docs "$D" \
    --llm_max_async 1 \
    --llm_timeout 1200 \
    2>&1 | tee logs/build_graph/cmp_tq_turbo_14bq5_p1c32knp2048_${L}.log
done
```

Không nên chạy ngay 384 docs với 14B Q5. Cần qua 1/5/10/50 trước vì TH11B 1 doc đã mất 442.59s.

## 9. Ước lượng thời gian khi chạy 384 docs

Các ước lượng này chỉ để lập kế hoạch, không phải kết quả chắc chắn.

| Cấu hình | Cơ sở ước lượng | Ước lượng 384 docs | Rủi ro |
|---|---|---|---|
| TH5 Gemini | đã có kết quả thật 384 docs | 12779.23s, khoảng 3h33m | không phải local LLM |
| 7B TurboQuant p4/c64k cũ | TH1 50 docs 3283s nhưng có lỗi context | có thể nhiều giờ, nhưng không khuyến nghị | community report lỗi do 16k slot |
| 7B TurboQuant p2/c64k mới | giảm parallel nên mỗi slot nhiều context hơn | có thể chậm hơn p4, nhưng sạch hơn | cần test 50/100 trước |
| 7B TurboQuant p1/c64k | an toàn context nhất | chậm hơn p2 | phù hợp nếu p2 vẫn lỗi context |
| 14B Q5 p1/c32k | TH11B 1 doc 442.59s | có thể rất lâu, không nên chạy 384 ngay | tốc độ thấp, 5 docs còn chưa xong |

Cách ước lượng thực dụng sau khi chạy lại:

```text
seconds_per_chunk = elapsed_seconds / số_chunks_đã_xử_lý
ước lượng 384 = seconds_per_chunk * 1462 + thời gian community + thời gian embedding/persist
```

Nhưng cần nhớ: community reports không tuyến tính hoàn toàn, vì càng nhiều docs thì community prompt càng dài, nguy cơ context/embedding lỗi tăng.

## 10. Checklist kiểm tra sau mỗi run

### 10.1 Kiểm backend thật sự

```bash
rg -n 'model|gemini-2.5-flash-lite|qwen3-14b-instruct|qwen2.5:7b-instruct|qwen25' \
  outputs/build_graph/<OUTPUT_FOLDER>/kv_store_llm_response_cache.json
```

Nếu cache ghi Gemini thì không phải local LLM. Nếu cache ghi alias của llama-server và server log có POST /v1/chat/completions thì mới là local llama-server.

### 10.2 Kiểm lỗi community context

```bash
rg -n 'exceeds available context size|context length|error|Error' \
  outputs/build_graph/<OUTPUT_FOLDER>/kv_store_community_reports.json
```

### 10.3 Kiểm lỗi build graph

```bash
rg -n 'Error during graph building|Ollama embedding API error|exceeds available context size|Traceback' \
  logs/build_graph/<BUILD_LOG>.log
```

### 10.4 Kiểm server thật sự nhận request

```bash
rg -n 'POST /v1/chat/completions|exceeds available context size|n_ctx|n_ctx_seq|slot|cudaMalloc failed|decode|prompt eval' \
  logs/llama_server/<SERVER_LOG>.log
```

### 10.5 Kiểm output đã hoàn tất chưa

Một output folder hoàn tất tối thiểu nên có:

```text
kv_store_full_docs.json
kv_store_text_chunks.json
kv_store_llm_response_cache.json
vdb_entities.json
vdb_relations.json
kv_store_community_reports.json
graph_chunk_entity_relation.graphml
temporal_hierarchy.graphml
```

Nếu chỉ có kv_store_llm_response_cache.json thì run chưa hoàn tất.

## 11. Nên sửa code gì trước khi chạy full 384 local

### 11.1 Thêm guard truncate embedding

Vấn đề TH11A 384 nằm ở embedding content quá dài. Nên sửa ở đường dẫn trước khi gọi embedding:

- [vector_nanovectordb.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/vector_nanovectordb.py:107)
- [embedding.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/embedding.py:118)

Khuyến nghị:

```text
Nếu len hoặc token_count content vượt giới hạn embedding, truncate và log warning.
Log namespace, id, độ dài cũ, độ dài mới.
```

### 11.2 Giới hạn description sau merge entity/relation

Nếu một entity như 2023 gom quá nhiều mô tả, description sẽ phình rất lớn. Nên cap description sau merge, ví dụ 2048 hoặc 4096 tokens, trước khi ghi vào vector store.

### 11.3 Ghi log nguồn backend ở đầu run

Repo Turboquant hiện tại đã có runtime print. Khi chạy phải giữ dòng này trong log để tránh nhầm như TH11A.

## 12. Nguồn tham khảo web đã dùng

- llama.cpp server README: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- TurboQuant plus repo: https://github.com/TheTom/turboquant_plus
- TurboQuant asymmetric KV compression notes: https://github.com/TheTom/turboquant_plus/blob/main/docs/papers/asymmetric-kv-compression.md
- llama.cpp TurboQuant discussion: https://github.com/ggml-org/llama.cpp/discussions/20969
- Ollama embed API: https://docs.ollama.com/api/embed
- Ollama nomic-embed-text model page: https://ollama.com/library/nomic-embed-text
- Microsoft GraphRAG indexing overview: https://microsoft.github.io/graphrag/index/overview/
- Microsoft GraphRAG methods: https://microsoft.github.io/graphrag/index/methods/
- Microsoft GraphRAG detailed config: https://microsoft.github.io/graphrag/config/yaml/
