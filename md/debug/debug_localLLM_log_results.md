# Debug local LLM, TurboQuant, llama-server và kết quả build graph

Ngày rà soát: 2026-05-22.

Tài liệu này là bản chi tiết đã khôi phục lại sau khi bản rút gọn trước đó làm mất nhiều nội dung. Mục tiêu là giữ đủ các phần cần dùng để kiểm chứng lại benchmark:

- Tiêu chí so sánh và cách hiểu từng tiêu chí.
- Bảng kịch bản TH1-TH10 và TH11A/TH11B.
- Mapping đúng log server, log build, output folder cho từng TH.
- Kết quả định lượng theo docs 1, 5, 10, 50, 100, 384 nếu có.
- Giải thích lỗi theo TH, chỉ rõ lỗi do CLI, source, config, server context, embedding context hay run bị dừng.
- Bằng chứng từ source code và file output.
- Full lệnh start server và build graph cho TH1-TH10, TH11A/TH11B.
- Cấu hình khuyến nghị để chạy đúng TurboQuant local LLM cho 384 docs.
- Ghi chú từ tài liệu web về llama-server, TurboQuant, Ollama embedding và GraphRAG indexing.

Bản rút gọn trước khi khôi phục được sao lưu tại:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/md/debug/debug_localLLM_log_results_summary_backup.md
```

## Tổng quan trước mục lục: local LLM + TurboQuant đang vướng gì?

Mục tiêu chính của toàn bộ tài liệu này là kiểm chứng xem **Temporal-GraphRAG-Turboquant** có chạy được **local LLM qua llama-server TurboQuant** cho bài toán **TG-RAG / ECT-QA 384 docs** hay không, và nếu chưa chạy full ổn định thì lỗi nằm ở đâu.

Kết luận tổng quan hiện tại:

```text
Repo nên chạy chính: /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
Server nên chạy từ: /home/guest/Projects/Research/llama-cpp-turboquant
Local LLM ổn nhất hiện tại: Qwen3 14B Q5 qua llama-server TurboQuant
Embedding hiện tại gây rủi ro: Ollama nomic-embed-text hardcode trong source
Full 384 local hiện chưa nên chạy lại nếu chưa sửa embedding layer
```

### A. Các vấn đề chính khi chạy local LLM + TurboQuant

| Vấn đề | TH / Folder chạy | Model / runtime liên quan | Triệu chứng | Nguyên nhân thật | Hướng fix để chạy đúng local + TurboQuant |
|---|---|---|---|---|---|
| Nhầm backend local/Gemini | TH11A, folder `Temporal-GraphRAG-Turboquant-th11-c1f1ea2` | Server Qwen3 14B Q5 có chạy, nhưng build cache là `gemini-2.5-flash-lite` | Có start `llama-server`, GPU/VRAM bị chiếm, nhưng cache lại là Gemini | `build_graph.py` TH11 healthcheck server trước, nhưng `config.yaml` vẫn `building.provider=gemini` | Không lấy TH11A làm đường chạy local; xác định backend bằng `kv_store_llm_response_cache.json` và server log |
| Context community report bị thiếu ở 7B | TH1 folder `Temporal-GraphRAG-Turboquant`, TH2 folder `Temporal-GraphRAG` | Qwen2.5 7B Q8, `-c 65536 --parallel 4 --n-predict 4096`, KV `q8_0/turbo3` | Build xong nhưng một số community reports là `Error Report for Unknown` | Context tổng 64k bị chia cho 4 slot, mỗi slot còn khoảng 16k; prompt community report vượt slot context | Với đường 7B trong folder Turboquant, chạy lại theo TH1 nhưng đổi `--parallel 2` hoặc `1`, `--llm_max_async` khớp, ưu tiên `--n-predict 2048/3072` |
| Embedding input quá dài ở 14B | TH7 folder `Temporal-GraphRAG-Turboquant`; TH11A 384 ở folder TH11 | TH7 dùng Qwen3 14B Q5 local TurboQuant; embedding vẫn Ollama `nomic-embed-text` | TH7 100 và TH11A 384 lỗi `Ollama embedding API error 500: input length exceeds context length` | Entity/relation description sau merge quá dài, source gửi nguyên sang `nomic-embed-text`; source chưa có `--embedding_model/dim/max_chars` | Với đường 14B, fix bắt buộc là patch embedding CLI/source, cap/log content, dùng BGE-M3/HF embedding trước khi chạy 100/384 |
| 14B Q8 OOM VRAM | TH8/TH11 server Q8, folder Original/TH11 | Qwen3 14B Q8 + KV 32k | `cudaMalloc failed`, `failed to allocate kv cache` | 16GB VRAM không đủ cho Qwen3 14B Q8 + KV cache 32k | Chuẩn hóa 14B về Q5: `Qwen3-14B-Q5_0.gguf`, `-c 32768 --parallel 2`; nếu vẫn sát VRAM thì `--parallel 1` |
| Output incomplete nhưng dễ bị đọc nhầm | TH1 100 folder TQ, TH7 384 folder TQ, TH11B 5 folder TH11 | 7B/14B local tùy TH | Chỉ có cache hoặc GraphML tạm, thiếu vector/full_docs/chunks | Run bị dừng trước persist đầy đủ | Chỉ coi run hoàn tất khi đủ `full_docs`, `text_chunks`, `vdb_*`, `community_reports`, GraphML |
| Local 14B rất chậm | TH7 folder `Temporal-GraphRAG-Turboquant`, TH11B folder TH11 | Qwen3 14B Q5 local qua `llama-server` | 1 doc hoặc 50 docs mất rất lâu | 14B local decode chậm hơn Gemini/API; community report nhiều request | Chạy mốc 1/5/10/50 trước, thêm runtime logging stage-level, chưa chạy 384 khi embedding chưa fix |
| Config mặc định không phải local | `Temporal-GraphRAG-Turboquant/tgrag/configs/config.yaml` | Default `building.provider=gemini`, `building.model=gemini-2.5-flash-lite` | Không truyền CLI thì build dùng Gemini | Config mặc định phục vụ Gemini baseline, không tự chuyển sang local | Khi chạy local trong folder TQ phải dùng CLI override `--local_llm_backend turboquant --model ... --base_url http://localhost:8080/v1` |


### A.1 Tổng kết lỗi theo từng giai đoạn build graph local

Phần này chỉ xét **local LLM + local embedding + TurboQuant** trong giai đoạn **build graph**. Không dùng TH5/TH6 Gemini làm bằng chứng chính ở đây. TH11A cũng không dùng làm mốc local vì cache đã chứng minh TH11A dùng Gemini; TH11A chỉ là bằng chứng phụ cho lỗi embedding scale lớn.

Pipeline build graph thực tế cần đọc theo thứ tự này:

```text
start llama-server
-> build_graph.py load config/CLI runtime
-> load docs và chunking
-> extract_entities bằng local LLM
-> merge entity/relation vào graph
-> upsert vector: gọi local embedding
-> generate community reports bằng local LLM
-> persist JSON/vector/GraphML cuối
```

Nếu không tách theo stage như trên thì rất dễ kết luận sai. Ví dụ TH7 100 không fail vì LLM/KV: local LLM đã xử lý đủ 391/391 chunks rồi mới fail ở embedding. Ngược lại TH1/TH2 không fail ở embedding: vector upsert đã qua, lỗi nằm ở community report prompt vượt slot context.

| Stage | Stage đó chạy cái gì | TH/log kiểm chứng | Lỗi/thực trạng nhìn thấy | Vì sao xảy ra | Cách xử lý trước 384 docs |
|---|---|---|---|---|---|
| 0. Start `llama-server` | Load GGUF vào GPU, cấp KV cache, tạo slot theo `--parallel`; stage này xảy ra trước khi Python build graph chạy | Q8 fail: `Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_14b_p2c32k_20260522_233312.log`; Q5 chạy: `cmp_tq_turbo_14bq5_p2c32k_20260523_004207.log` | Qwen3 14B Q8 fail với `cudaMalloc failed` và `failed to allocate buffer for kv cache`; Q5 có `POST /v1/chat/completions 200` và `truncated = 0` | TurboQuant giảm KV, nhưng không làm nhỏ model weights. 14B Q8 + KV 32k vẫn quá sát 16GB VRAM | Với RTX 5070 Ti 16GB, 14B nên dùng Q5, không dùng Q8. Server khuyến nghị: `-c 32768 --parallel 2 -ctk q8_0 -ctv turbo3`; nếu còn sát VRAM hoặc context report lỗi thì thử `--parallel 1` |
| 1. Runtime/config | `build_graph.py` đọc CLI/config rồi quyết định provider/model/base_url thật sự dùng cho LLM và embedding | TH7 100 log dòng runtime: `provider=openai`, model `qwen3-14b-q5-...`, `wire_protocol=openai-compatible-local`, `embedding_provider=ollama` | Nếu không kiểm runtime/cache, dễ nhầm có server local là build dùng local | Backend thật nằm ở CLI/config/cache, không nằm ở việc GPU có bị chiếm hay không | Mỗi run phải kiểm ba chỗ: dòng `[runtime]` trong build log, model trong `kv_store_llm_response_cache.json`, và server log có `POST /v1/chat/completions` |
| 2. Load docs và chunking | Đọc `ect-qa/corpus/base.jsonl.gz`, giới hạn `--num_docs`, tạo text chunks theo chunk size/overlap | TH7 100: `new chunks: 391`; TH7 384: `new chunks: 1462`; TH1 50: `new chunks: 199` | Stage này chưa phải bottleneck chính; log thường chỉ vài phần mười giây | Số chunk tăng gần tuyến tính theo docs, nhưng lỗi sau đó tăng không tuyến tính vì entity/relation bị merge theo tên chung | Không cần sửa chunking trước tiên. Giữ 1200/100 để so sánh, nhưng phải log số chunks và không so thời gian nếu số chunks khác nhau |
| 3. Chunk LLM extraction | Với mỗi chunk, local LLM trích entity/relation/temporal info; đây là phần gọi nhiều request nhất tới `llama-server` | TH7 100: `extract_entities started: chunks=391`, `Processed 391(100%) chunks`, `chunk LLM extraction + parsing: 15735.13s`; TH1 50: `chunk LLM extraction + parsing: 2987.35s` | 14B Q5 local chạy rất lâu nhưng đã chạy đúng; TH7 384 chỉ dừng khoảng `310/1462` chunks nên là run incomplete, chưa phải lỗi embedding cuối | Local 14B decode chậm và số request lớn. Đây là chi phí thật của local LLM, không phải I/O/timer logging | Chạy mốc 1/5/10/50/100 trước. Với 384, cần resume/cache ổn và log stage-level; không dùng TH7 384 hiện tại làm benchmark hoàn tất |
| 4. Merge entity/relation vào graph | Sau extraction, code gom entity/relation trùng tên, merge description/source_id, ghi GraphML trung gian | TH7 100: `aggregate extracted records: entities=3886, relations=2423`, `split/filter ... graph_entities=3817`, `entity merge/upsert batches complete: entities=3817: 378.95s` | Stage này không crash, nhưng tạo ra entity description rất dài | TG-RAG/ECT-QA có nhiều entity chung như `CHINA`, năm/quý, chỉ số tài chính. Khi nhiều chunks trùng entity, description bị nối dài | Cần cap/summarize description sau merge hoặc tách theo temporal slice trước khi đem đi embedding |
| 5. Vector upsert embedding | Tạo payload vector từ entity/relation rồi gọi embedding local. Với source hiện tại, content embedding là `entity_name + description`, sau đó gửi sang Ollama `/api/embeddings` | TH7 100: `vector upsert started: namespace=entities items=3817`, sau đó lỗi `Ollama embedding API error 500: {"error":"the input length exceeds the context length"}` | Đây là blocker sạch nhất của local 14B hiện tại: LLM extraction đã xong, graph merge đã xong, fail đúng lúc embed entity vectors | Description sau merge quá dài. `nomic-embed-text` qua Ollama có giới hạn context; source hiện chưa chặn/truncate/log item quá dài trước khi gọi embedding | Patch bắt buộc trước 384: thêm `--embedding_model`, `--embedding_dim`, `--embedding_max_chars`; log top-N content dài nhất; truncate theo token/char trước embedding. Ưu tiên BGE-M3/HF embedding nếu muốn ổn định hơn `nomic` |
| 6. Community report | Sau khi graph/vector đã có, code detect communities rồi dùng LLM tạo summary/report cho từng community | TH1 50 build log có nhiều `Failed to generate community report after 3 attempts`; TH1 server log có `n_ctx_seq = 16384`, 4 slot `n_ctx = 16384`, và request `32160`, `37344`, `76727` tokens vượt `16384`; TH7 50 cũng có report failed với Q5 p2/c32k | Build vẫn có thể báo completed, nhưng một số community report là error report. Đây là pass kỹ thuật một phần, không phải graph sạch | `-c` là context tổng; `--parallel` chia thành slot. `-c 65536 --parallel 4` thành 16k/slot; `-c 32768 --parallel 2` cũng thành 16k/slot. Community prompt có thể lớn hơn 16k do graph/community description dài | Với 7B: thử p2 hoặc p1 thay p4, giảm `--n-predict` 2048/3072. Với 14B: nếu report còn vượt context, dùng `--parallel 1` hoặc giảm/cap prompt community |
| 7. Persist output cuối | Ghi `kv_store_full_docs`, `kv_store_text_chunks`, `vdb_*`, `community_reports`, GraphML cuối | TH1 100 chỉ có cache; TH7 100 lỗi trước persist final nên `full_docs/text_chunks/community` đếm 0; TH7 384 chỉ có cache; TH11B 5 có cache nhưng output final rỗng | Có file không đồng nghĩa pass. Cache có thể tồn tại dù build chết giữa chừng | Persist cuối chỉ xảy ra sau khi các stage trước qua hết. Nếu fail ở embedding/community/premature stop, output bị thiếu hoặc rỗng | Chỉ coi run pass khi đủ JSON/vector/GraphML và count hợp lý. Không dùng output chỉ có cache làm benchmark |
| 8. Đo benchmark | Đo thời gian stage build graph và server throughput khi không có process khác tranh GPU/CPU/RAM | TH7 có ghi chú còn process 001docs; TH9/TH10 phải stop `llama-server` nếu dùng Ollama 14B | Thời gian sai nếu cùng lúc chạy nhiều build, hoặc Ollama LLM/embedding và `llama-server` cùng giữ GPU | Local LLM, local embedding và server đều tranh tài nguyên. Timer logging không đủ lớn để giải thích chênh lệch hàng nghìn giây | Chạy từng TH tuần tự; log build/server riêng; dùng `nvidia-smi`, cache count và stage timers để đọc kết quả |

Các lỗi đã gặp cần hiểu đúng:

| Lỗi | Không nên kết luận sai là | Kết luận đúng từ log |
|---|---|---|
| TH7 100 lỗi embedding | Không phải Qwen3 14B Q5 hay TurboQuant fail extraction | LLM local đã xử lý đủ `391/391` chunks; fail ở `entity_vdb.upsert -> ollama_embedding -> /api/embeddings` |
| TH1/TH2 community report failed | Không phải embedding fail, cũng không phải build hoàn toàn chết | Build đã qua vector upsert và persist, nhưng một số community prompt vượt 16k slot context |
| TH7 384 incomplete | Không phải bằng chứng 384 fail embedding cuối | Run dừng khi mới extraction một phần, chỉ chứng minh 384 local rất lâu/chưa hoàn tất trong lần đó |
| 14B Q8 OOM | Không phải lỗi source build graph | Server chưa load xong KV/model, lỗi xảy ra trước Python build graph |
| Có cache nhưng output thiếu | Không phải pass | Cache chỉ chứng minh đã gọi LLM một phần; phải kiểm full docs/chunks/vector/community/GraphML cuối |

Trace lỗi embedding của TH7 100:

```text
build_graph.py
-> create_temporal_graphrag_from_config(...)
-> temporal_graphrag.build_graph(...)
-> extract_entities(...)
-> entity_vdb.upsert(data_for_vdb)
-> vector_nanovectordb.py: embeddings_list = await asyncio.gather(...)
-> build.py: embedding_wrapper(...)
-> embedding.py: ollama_embedding(...)
-> Ollama /api/embeddings
-> 500: the input length exceeds the context length
```

Vì vậy, blocker local build graph hiện nằm ở ba lớp chính:

```text
1. Server/context slot cho community report.
2. Embedding input length sau merge entity/relation.
3. Output incomplete do run bị dừng trước persist final.
```

TurboQuant cần được đánh giá ở lớp LLM inference qua `llama-server`; nó không tự sửa lỗi embedding input length, không tự giảm community prompt, và không thay thế kiểm tra output cuối.

Điểm quan trọng nhất: **TurboQuant không phải nguyên nhân trực tiếp của lỗi full 384 hiện tại**. TurboQuant chỉ tác động lên inference/KV cache trong `llama-server`. Các lỗi đang chặn full 384 nằm ở:

```text
1. context slot của local LLM khi tạo community report
2. embedding input length sau khi entity/relation description bị merge quá dài
3. source hiện chưa cho chọn embedding_model/dim bằng CLI ở build_graph.py
```

### B. Hướng fix để chạy full 384 docs trong folder Turboquant

Trước khi chạy lại full 384 local, cần sửa theo thứ tự:

| Ưu tiên | Việc cần làm | Lý do |
|---:|---|---|
| 1 | Giữ folder chạy chính là `Temporal-GraphRAG-Turboquant` | Đây là repo có CLI override rõ cho local backend và là folder mục tiêu để apply TurboQuant |
| 2 | Dùng Qwen3 14B Q5, không dùng Q8 | Q8 đã fail VRAM/KV trên 16GB |
| 3 | Server dùng `-c 32768 --parallel 2 --n-predict 4096 -ctk q8_0 -ctv turbo3` | Cân bằng giữa context, concurrency và VRAM |
| 4 | Build dùng `--llm_max_async 2 --llm_timeout 900` | Khớp với server slot, tránh queue nghẽn |
| 5 | Patch embedding CLI/source: `--embedding_model`, `--embedding_dim`, `--embedding_max_chars` | Nếu không patch, source vẫn dùng `nomic-embed-text` dù đã pull model khác |
| 6 | Đổi embedding sang `bge-m3` hoặc HuggingFace BGE-M3 | Hợp ECT-QA/TG-RAG hơn `nomic`, context dài hơn, dimension rõ hơn |
| 7 | Cap/log entity/relation content trước embedding | Chặn lỗi `input length exceeds context length` ở 100/384 |
| 8 | Chạy tuần tự 50 -> 100 -> 384 | 50 pass không chứng minh 384 pass vì description phình theo scale |
| 9 | Sau build, kiểm đủ output | Không dùng run chỉ có cache hoặc GraphML tạm làm mốc |

Cấu hình chạy hiện tại nên hướng tới:

```text
Repo:        /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
LLM server:  Qwen3-14B-Q5_0.gguf qua llama-server TurboQuant
KV:          -ctk q8_0 -ctv turbo3
Context:     -c 32768
Parallel:    --parallel 2
Build async: --llm_max_async 2
Embedding:   bge-m3, embedding_dim=1024, sau khi patch source
Guard:       embedding_max_chars khoảng 16000 trước, log top content dài nhất
Chunk:       giữ 1200/100 trước
Dataset:     ect-qa/corpus/base.jsonl.gz, full 384 docs
```

Nếu chưa patch embedding layer, cấu hình hiện tại chỉ nên dùng để benchmark local LLM ở 1/5/10/50 docs, chưa nên coi là pipeline full 384 ổn định.

### B.1 Nên đi theo TH nào để fix full 384 cho 7B và 14B?

Mục tiêu không phải chọn TH nhanh nhất, mà chọn **đường chạy đúng local + TurboQuant trong folder `Temporal-GraphRAG-Turboquant`** rồi fix từng lỗi cho 384 docs.

| Đường fix | TH gốc nên bám theo | Folder build | Server/model | Cấu hình server nên dùng lại | Build config nên dùng | Lỗi phải fix trước 384 | Khi nào coi là đạt |
|---|---|---|---|---|---|---|---|
| Local 7B + TurboQuant | TH1 | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant` | Qwen2.5 7B Q8 GGUF qua `llama-server` | Đổi từ p4 sang p2/p1: `-c 65536 --parallel 2 --n-predict 2048/3072 -ctk q8_0 -ctv turbo3 -fa on -ngl 99` | `--local_llm_backend turboquant --llm_max_async 2 --llm_timeout 900 --embedding_provider ollama` | Community report context; sau đó vẫn cần guard embedding nếu chạy 100/384 | 50/100/384 có đủ output và không còn `Error Report for Unknown` do context |
| Local 14B + TurboQuant | TH7 | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant` | Qwen3 14B Q5 GGUF qua `llama-server` | Giữ Q5: `-c 32768 --parallel 2 --n-predict 4096 -ctk q8_0 -ctv turbo3 -fa on -ngl 99`; nếu lỗi context thì thử `--parallel 1` | `--local_llm_backend turboquant --model qwen3-14b-q5-... --llm_max_async 2 --llm_timeout 900` | Embedding input length là blocker chính; cần `--embedding_model bge-m3 --embedding_dim 1024 --embedding_max_chars ...` sau khi patch | 100/384 pass đủ vector stores, không còn `Ollama embedding API error` |
| Baseline Gemini để đối chiếu | TH5 | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant` | Gemini API, không TurboQuant | Không cần server local | `--provider gemini --model gemini-2.5-flash-lite` | Không dùng để chứng minh local LLM; chỉ làm mốc graph/API | Dùng để so output/chất lượng/tốc độ với local |
| Không nên bám để fix chính | TH11A/TH11B | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2` | TH11A là Gemini thật; TH11B local 14B nhưng commit cũ/chậm | Chỉ dùng kiểm chứng commit cũ | Không dùng làm pipeline chính | Dễ nhầm healthcheck/backend | Chỉ dùng làm bằng chứng phân tích, không dùng làm đường chạy 384 mới |

Tóm lại:

```text
Muốn fix 7B full 384: đi theo TH1, nhưng đổi server p4 -> p2/p1 và giảm n-predict.
Muốn fix 14B full 384: đi theo TH7 Q5, nhưng phải patch embedding trước.
Muốn kiểm pipeline graph/API sạch: dùng TH5 làm baseline, không phải local LLM.
```

### C. Vì sao phải so sánh nhiều TH?

Các TH không chỉ để xem cái nào nhanh hơn. Mục tiêu là tách lỗi theo từng lớp:

| Nhóm TH | Mục tiêu | Source/folder | Ý nghĩa |
|---|---|---|---|
| TH1 vs TH2 | So Turboquant repo và Original worktree khi cùng dùng local 7B TurboQuant | `Temporal-GraphRAG-Turboquant` vs `Temporal-GraphRAG` | Kiểm tra khác biệt repo/source khi backend giống nhau |
| TH3 vs TH4 | So Ollama 7B native | TQ vs Original | Baseline local không TurboQuant |
| TH5 vs TH6 | So Gemini API | TQ vs Original | Baseline cloud/API, xác nhận graph pipeline có thể chạy full 384 nếu LLM mạnh/ổn định |
| TH7 vs TH8 | So local 14B Q5 TurboQuant | TQ vs Original | Kiểm tra cấu hình local mạnh hơn 7B và giới hạn VRAM 16GB |
| TH9 vs TH10 | So Ollama 14B native | TQ vs Original | Baseline 14B không TurboQuant, phải stop llama-server để tránh tranh GPU |
| TH11A | Tái hiện commit `c1f1ea2` nguyên bản | `Temporal-GraphRAG-Turboquant-th11-c1f1ea2` | Chứng minh healthcheck/server không đồng nghĩa build dùng local LLM |
| TH11B | Ép commit cũ dùng local OpenAI-compatible server | TH11 worktree | Chứng minh local Qwen3 14B Q5 thật nhưng rất chậm |

Cách đọc đúng các source/folder:

```text
Temporal-GraphRAG-Turboquant:
  folder mục tiêu để tiếp tục chạy TurboQuant local LLM.

Temporal-GraphRAG:
  folder gọi là Original trong TH2/TH4/TH6/TH8/TH10, nhưng local worktree này đã có custom, không phải upstream sạch tuyệt đối.

Temporal-GraphRAG-Turboquant-th11-c1f1ea2:
  folder chỉ dùng để tái hiện commit cũ TH11A/TH11B, không nên dùng làm pipeline chính.

llama-cpp-turboquant:
  nơi start llama-server có TurboQuant KV bằng -ctk/-ctv.
```

### D. Cách kiểm một run có thật sự thành công hay không

Một run chỉ được coi là hoàn tất khi có đủ:

```text
kv_store_full_docs.json
kv_store_text_chunks.json
kv_store_llm_response_cache.json
kv_store_community_reports.json
vdb_entities.json
vdb_relations.json
vdb_entities_new.json
graph_chunk_entity_relation.graphml
graph_temporal_hierarchy.graphml
```

Không đủ để kết luận thành công nếu chỉ thấy:

```text
kv_store_llm_response_cache.json
hoặc GraphML tạm
hoặc log có một phần Processed chunks
```

Backend thật phải kiểm bằng:

```text
1. model trong kv_store_llm_response_cache.json
2. build log dòng [runtime]
3. server log có POST /v1/chat/completions nếu là llama-server
```

## Mục lục

Dùng mục lục này theo đúng thứ tự đọc hiện tại: bài toán -> repo/TH -> kết quả -> lỗi -> hướng fix -> source/lệnh/log appendix.

- `Tổng quan trước mục lục`: mục tiêu, lỗi chính, hướng fix nhanh, tổng kết lỗi local build graph theo từng stage.
- `1. Kết luận chính`: folder nên chạy, backend thật, lỗi chính.
- `2. Bối cảnh TG-RAG / ECT-QA`: ECT-QA là gì, vì sao TG-RAG khác normal RAG, dataset/chunking ảnh hưởng ra sao.
- `3. Repo, commit và phạm vi so sánh`: Turboquant, Original worktree, TH11 c1f1ea2, llama-cpp-turboquant.
- `4. Quy tắc tên kết quả`: quy tắc `cmp_<repo>_<backend>_<model>_<runtime>_<docs>`.
- `5. Bảng kịch bản TH1-TH10 và TH11`: mapping nhanh từng TH theo folder/model/backend.
- `6. Các tiêu chí so sánh`: backend, hoàn tất, thời gian, graph, lỗi context/embedding.
- `7. Kết quả định lượng chi tiết`: bảng kết quả docs/chunks/cache/entities/relations/communities.
- `8. So sánh theo tiêu chí`: backend, tốc độ, độ sạch output, bottleneck.
- `9. Audit log/output và trạng thái run hợp lệ`: rà lại report failed, output incomplete, run nào dùng được.
- `10. Phân tích lỗi chi tiết theo TH`: lỗi context, embedding, TH11A/TH11B, OOM.
- `11. Hướng fix full 384 trước khi chạy lại local`: guard embedding, cap description, logging.
- `12. Config hiện tại, GPU 16GB và hướng chạy ổn định`: config hiện tại, RTX 5070 Ti 16GB, setup local/HuggingFace, checklist full 384.
- `13. Cấu hình và lệnh chạy đúng để test lại TurboQuant local LLM`: 7B/14B local khuyến nghị.
- `14. Source code chi tiết theo TH và folder`: source snippets theo Turboquant/Original/TH11.
- `15. Mapping log và output đúng theo TH`: đường dẫn log/output từng TH.
- `16. Full lệnh kịch bản gốc TH1-TH10 và TH11`: toàn bộ lệnh server/build.
- `17. Checklist kiểm tra sau mỗi run`: kiểm backend, community context, build graph, server, output.
- `18. Ước lượng thời gian khi chạy 384 docs`: ước lượng theo log hiện có.
- `19. Bổ sung chọn embedding cho Temporal GraphRAG / ECT-QA`: `nomic`, BGE-M3, Qwen3 embedding, chunking, fine-tune.
- `20. Ghi chú từ tài liệu web`: llama-server, TurboQuant, Ollama embedding, GraphRAG indexing.
- `21. Nguồn tham khảo web`: nguồn đã dùng để đối chiếu.

## 1. Kết luận chính

Nếu mục tiêu là **chạy đúng TurboQuant local LLM để build graph**, nên chạy từ repo:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
```

và start server từ:

```text
/home/guest/Projects/Research/llama-cpp-turboquant
```

Cấu hình local 7B nên test lại trước:

```text
Model:        qwen2.5 7B Q8 GGUF
llama-server: -c 65536 --parallel 2 --n-predict 2048 -ctk q8_0 -ctv turbo3 -fa on
build_graph:  --local_llm_backend turboquant --llm_max_async 2 --llm_timeout 900
embedding:    Ollama nomic-embed-text qua http://localhost:11434
```

Ghi chú cập nhật: cấu hình 7B ở trên là mốc debug/local baseline. Với RTX 5070 Ti 16GB và mục tiêu full 384 docs, hướng ưu tiên hiện tại là mục 0.4: Qwen3 14B Q5 + TurboQuant KV, sau đó sửa embedding model/dim/cap để chạy BGE-M3 hoặc embedding tương đương.

Các kết luận quan trọng theo log/output hiện có:

- TH11A không phải local LLM. TH11A thực tế dùng `gemini-2.5-flash-lite`. Việc GPU/VRAM bị chiếm là do đã start `llama-server` và source `c1f1ea2` chạy healthcheck top-level.
- TH11B mới là local Qwen3 14B Q5 thật, vì cache ghi `qwen3-14b-instruct` và server log có chat completions. Nhưng TH11B rất chậm: 1 doc mất 442.59s, 5 docs chưa hoàn tất.
- TH1/TH2 là local 7B qua `llama-server`, nhưng cấu hình `-c 65536 --parallel 4` làm mỗi slot chỉ còn khoảng 16k context, khiến community reports bị lỗi context.
- TH5 và TH6 là hai mốc Gemini API đã chạy được 384 docs; TH5 sạch hơn, TH6 pass nhưng có 2 community report retry fail. Cả hai đều không phải local LLM/TurboQuant.
- TH11A 384 fail do Ollama embedding nhận input quá dài, không phải do KV/context của `llama-server`.
- Timer logs cho thấy bottleneck chính là LLM extraction/community, không phải I/O hay timer logging.

## 2. Bối cảnh TG-RAG / ECT-QA

### 0.8 ECT-QA, TG-RAG và cấu hình đủ đúng cho bài toán local LLM + TurboQuant

Bài toán đang làm không phải normal RAG. Paper **TG-RAG - RAG Meets Temporal Graphs: Time-Sensitive Modeling and Retrieval for Evolving Knowledge** mô tả TG-RAG là bi-level temporal graph gồm temporal knowledge graph có timestamped relations và hierarchical time graph. Điểm chính là cùng một fact/entity ở thời điểm khác nhau cần được biểu diễn khác nhau, sau đó query sẽ retrieve subgraph theo phạm vi semantic + temporal.

Nguồn web đã đối chiếu:

```text
https://arxiv.org/abs/2510.13590
https://github.com/hanjiale/Temporal-GraphRAG
https://deepwiki.com/hanjiale/Temporal-GraphRAG/8-ect-qa-benchmark-dataset
https://huggingface.co/datasets/austinmyc/ECT-QA
```

Thống kê ECT-QA local trong hai repo hiện giống nhau:

| Split | Docs | Thời gian | Công ty | Token/doc min/avg/max | Chars/doc min/avg/max | Mục tiêu |
|---|---:|---|---:|---:|---:|---|
| `base.jsonl.gz` | 384 | 2020-2023 | 24 | 1204 / 3309.6 / 5884 | 6379 / 18331.8 / 32531 | Build graph gốc |
| `new.jsonl.gz` | 96 | 2024 | 24 | 1208 / 3258.2 / 5180 | 6535 / 18161.5 / 28515 | Incremental update |

Question files local:

| File | Số câu | Vai trò |
|---|---:|---|
| `local_base.jsonl` | 656 | câu hỏi fact/temporal cụ thể trên 2020-2023 |
| `global_base.jsonl` | 72 | câu hỏi trend/summary trên 2020-2023 |
| `local_new.jsonl` | 349 | câu hỏi fact/temporal sau update 2024 |
| `global_new.jsonl` | 28 | câu hỏi trend/summary sau update 2024 |

Tổng local theo file là `1005 local/specific + 100 global/abstract`. Đây là số nên dùng khi nói về dataset trong repo đang chạy.

Vì `chunk_size=1200`, `chunk_overlap=100`, base 384 docs sinh ra 1462 chunks trong các run TH5/TH6/TH11A. Nghĩa là trung bình khoảng 3.8 chunks/doc. Chunking này đang vừa đủ cho extraction: không quá nhỏ để nổ số request, không quá lớn để prompt extraction vượt context. Lỗi full local hiện tại không nằm ở chunking ban đầu mà nằm ở hai tầng sau:

```text
1. Community report prompt có thể vượt context slot local LLM khi graph lớn.
2. Entity/relation description sau merge phình dài rồi đưa vào Ollama embedding, gây input length error.
```

Ảnh hưởng tới setup:

| Thành phần | Config hiện tại | Đánh giá cho ECT-QA/TG-RAG | Khuyến nghị |
|---|---|---|---|
| `chunk_size=1200` | đang dùng trong `config.yaml` | Hợp lý với transcript 1.2k-5.9k tokens | Giữ 1200 trước; chỉ giảm 1000 nếu local prompt quá dài |
| `chunk_overlap=100` | đang dùng | Đủ nối ngữ cảnh giữa các đoạn earnings call | Giữ 100 hoặc test 150; không tăng mạnh |
| `temporal_entity_extraction_new` | extract timestamp entity, important entities, temporal triplets | Đúng bản chất TG-RAG, nhưng output local LLM dễ dài/noisy | Cần LLM đủ tốt; Qwen3 14B Q5 tốt hơn 7B cho chất lượng, nhưng chậm hơn |
| Entity types | financial concept, business segment, event, company, person, product, location, organization | Khá phù hợp finance nhưng còn chung | Có thể bổ sung/tinh prompt về `financial metric`, `guidance`, `risk`, `geography`, `customer/channel` nếu muốn tăng chất lượng |
| Community report | prompt temporal report khá dài | Là bottleneck LLM và nơi TH1/TH2 lỗi context | Giữ cho final TG-RAG; nếu debug tốc độ extraction có thể tạm tắt, nhưng không dùng làm kết quả cuối |
| `disable_entity_summarization=true` trong config eval | bỏ summarize entity/relation | Giảm thêm LLM call nhưng có thể làm description dài hơn | Chỉ dùng khi đã có cap/log embedding input; nếu chưa cap thì có thể làm lỗi embedding nặng hơn |
| `querying.seed_node_method=relations` | query seed bằng relation | Hợp TG-RAG vì relation có timestamp | Embedding relation phải tốt; đổi embedding phải rebuild cả build/query |
| `querying.top_k=50` | retrieve rộng | Tốt cho recall multi-hop, nhưng dễ kéo noise nếu embedding kém | Giữ 50 cho benchmark; nếu graph noisy thì test 20/30 để debug |
| `enable_subgraph=true` | traverse graph | Cần cho multi-hop temporal retrieval | Giữ true |
| `enable_entity_retrieval=false` | không seed trực tiếp bằng entity embedding | Làm relation embedding quan trọng hơn | Có thể test bật entity retrieval sau khi embedding ổn |

Với mục tiêu **chạy local LLM và áp dụng TurboQuant để xem có tối ưu cho Temporal-GraphRAG không**, benchmark nên tách ba lớp:

| Lớp | Cần đo | Vì sao |
|---|---|---|
| LLM extraction/community | thời gian, timeout, context error, số report lỗi | Đây là nơi TurboQuant có tác động trực tiếp qua `llama-server` |
| Embedding/vector store | input length error, max content length, embedding model/dim | Đây là lỗi chính ở TH7 100 và TH11A 384, không do TurboQuant |
| Retrieval/eval | seed hit, temporal edge hit, answer quality | Đây mới là chất lượng TG-RAG cuối cùng trên ECT-QA |

Cấu hình nên dùng theo giai đoạn:

| Giai đoạn | Mục tiêu | Cấu hình nên chạy |
|---|---|---|
| Debug local LLM | xác nhận server/CLI/cache đúng | Qwen3 14B Q5, `-c 32768 --parallel 2`, docs 1/5/10/50 |
| Build full base ổn định | chạy được 384 docs không fail | Patch `embedding_model/dim`, dùng BGE-M3 hoặc HF embedding, cap/log embedding input |
| Benchmark TurboQuant | so p1/p2, 7B/14B, n-predict 2048/4096 | Giữ cùng chunk/embedding để chỉ thay LLM runtime |
| Incremental TG-RAG | test 2024 new docs | Sau khi base 384 ổn, mới chạy `new.jsonl.gz` với incremental/preserve communities |
| Query/eval | đo chất lượng ECT-QA | Query phải dùng đúng cùng embedding model/dim với graph đã build |

Cấu hình tối thiểu trước khi chạy full 384 local nên là:

```text
Repo:       /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
LLM:        Qwen3-14B-Q5_0.gguf qua llama-server TurboQuant
Server:     -c 32768 --parallel 2 --n-predict 4096 -ctk q8_0 -ctv turbo3 -fa on -ngl 99
Build:      --local_llm_backend turboquant --llm_max_async 2 --llm_timeout 900
Chunk:      1200/100
Embedding:  bge-m3 hoặc HF BGE-M3 sau khi source có --embedding_model/--embedding_dim
Guard:      cap/log entity/relation content trước embedding
Output:     không dùng lại vector store cũ khi đổi embedding model/dim
```

Nếu chưa sửa embedding layer, chỉ nên coi 1/5/10/50 docs là benchmark local LLM. Chạy 100/384 với `nomic` mặc định có khả năng lặp lại lỗi input length.

## 3. Repo, commit và phạm vi so sánh

| Repo | Vai trò | Trạng thái nên hiểu |
|---|---|---|
| `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant` | Repo nên dùng để chạy lại TurboQuant local LLM | HEAD hiện tại `61ac8e1ebb34c43e71ff568a0f2114b4ac586138`; có CLI runtime override rõ ràng |
| `/home/guest/Projects/Research/Temporal-GraphRAG` | Repo Original trong TH2/TH4/TH6 | Không phải upstream sạch tuyệt đối vì worktree có nhiều source đã sửa |
| `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2` | Worktree để tái hiện TH11A/TH11B | Commit `c1f1ea2dd87db4addc1469197d12593275b37c76`; có healthcheck gây nhầm backend |
| `/home/guest/Projects/Research/llama-cpp-turboquant` | Fork llama.cpp dùng để start `llama-server` TurboQuant | Nơi chạy `./build/bin/llama-server` với `-ctk`, `-ctv` |

Ghi chú quan trọng:

- Khi so sánh Original và Turboquant, không nên nói Original là bản sạch tuyệt đối. Repo Original hiện có nhiều file source đã sửa như `build_graph.py`, `tgrag/src/core/build.py`, `tgrag/src/core/building.py`, `tgrag/src/llm/client.py`, `tgrag/src/llm/completion.py`, `tgrag/src/storage/vector_nanovectordb.py`, `tgrag/src/temporal_graphrag.py`.
- Worktree TH11 chỉ dùng để kiểm chứng commit `c1f1ea2`, không nên dùng làm cấu hình chạy chính cho benchmark mới.

## 4. Quy tắc tên kết quả

Quy tắc đặt tên đã dùng:

```text
cmp_<repo>_<backend>_<model>_<runtime>_<docs>

repo:    tq | orig
backend: turbo | ollama | gemini
model:   7b | 14b
runtime: p4c64knp4096 | p2c32knp4096 | api
docs:    001docs | 005docs | 010docs | 050docs | 100docs | 384docs
```

Ý nghĩa:

- `tq`: repo `Temporal-GraphRAG-Turboquant`.
- `orig`: repo `Temporal-GraphRAG`, nhưng trong log hiện tại đây là worktree đã chỉnh, không phải upstream sạch.
- `turbo`: local `llama-server` OpenAI-compatible API, có thể dùng TurboQuant KV nếu server start với `-ctk/-ctv`.
- `ollama`: Ollama native API, không phải TurboQuant.
- `gemini`: Gemini API, không phải local LLM.
- `p4c64knp4096`: server parallel 4, context 64k, n-predict 4096.
- `p2c32knp4096`: server parallel 2, context 32k, n-predict 4096.

## 5. Bảng kịch bản TH1-TH10 và TH11

Bảng này dùng để đọc nhanh: mỗi TH đang chạy ở folder nào, dùng backend/model nào, và mục tiêu kiểm chứng là gì. Các TH không chỉ để đo nhanh/chậm; chúng tách lỗi theo repo, backend, local server, Ollama native, Gemini baseline và commit cũ.

| TH | Folder build/output | Mục tiêu/đang kiểm gì | Tmux server | Tmux build | Repo | Backend | Model | Runtime | Trạng thái log/output |
|---:|---|---|---|---|---|---|---|---|---|
| TH1 | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant` | Đường chính để kiểm local 7B + TurboQuant trong repo mục tiêu; dùng để xem TurboQuant 7B có build graph được không và lỗi context community xuất hiện ra sao | `srv_tq_turbo_7b_p4c64k` | `bld_tq_turbo_7b_p4c64k` | Turboquant | `llama-server` TurboQuant OpenAI-compatible | GGUF Qwen2.5 7B Q8 | p4/c64k/np4096 | Có 1/10/50 success; 100 incomplete; 10/50 có community report lỗi context |
| TH2 | `/home/guest/Projects/Research/Temporal-GraphRAG` | So với TH1 khi giữ cùng local 7B TurboQuant nhưng đổi sang Original worktree; dùng để tách lỗi do repo hay do server/context | `srv_orig_turbo_7b_p4c64k` | `bld_orig_turbo_7b_p4c64k` | Original worktree | `llama-server` TurboQuant OpenAI-compatible | GGUF Qwen2.5 7B Q8 | p4/c64k/np4096 | Có 1/10/50 success; không có 100; lỗi community context giống TH1 |
| TH3 | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant` | Baseline local 7B nhưng không dùng TurboQuant; kiểm repo Turboquant khi gọi Ollama native | none | `bld_tq_ollama_7b` | Turboquant | Ollama native | `qwen2.5:7b-instruct` | api | Có 1/10/50 success; không có 100 |
| TH4 | `/home/guest/Projects/Research/Temporal-GraphRAG` | Baseline Original + Ollama 7B; so với TH3 để tách khác biệt repo khi backend Ollama giống nhau | none | `bld_orig_ollama_7b` | Original worktree | Ollama native | `qwen2.5:7b-instruct` | api | Có 1/10/50 success; không có 100 |
| TH5 | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant` | Baseline cloud/API sạch cho repo Turboquant; dùng để chứng minh graph pipeline có thể chạy full 384 nếu LLM extraction không bị giới hạn local | none | `bld_tq_gemini` | Turboquant | Gemini API | `gemini-2.5-flash-lite` | api | Có 1/10/50/100/384 success |
| TH6 | `/home/guest/Projects/Research/Temporal-GraphRAG` | Baseline cloud/API cho Original worktree; so với TH5 để thấy khác biệt repo/source khi cùng Gemini | none | `bld_orig_gemini` | Original worktree | Gemini API | `gemini-2.5-flash-lite` | api | Có 1/10/50/100/384 success; 384 có 2 community report retry fail nhưng build vẫn hoàn tất |
| TH7 | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant` | Đường chính để kiểm local 14B Q5 + TurboQuant trong repo mục tiêu; đây là hướng ưu tiên để apply TurboQuant local LLM trên 16GB VRAM | `srv_tq_turbo_14bq5_p2c32k` | `bld_tq_turbo_14bq5_p2c32k_005_100docs` | Turboquant | `llama-server` TurboQuant OpenAI-compatible | GGUF Qwen3 14B Q5 | p2/c32k/np4096 | 1/5/10/50 success; 100 fail ở Ollama embedding input length; 384 dừng sớm khoảng 310/1462 chunks |
| TH8 | `/home/guest/Projects/Research/Temporal-GraphRAG` | So với TH7 khi giữ local 14B TurboQuant nhưng đổi Original worktree; Q5 dùng để tránh Q8 OOM | `srv_orig_turbo_14bq5_p2c32k` | `bld_orig_turbo_14bq5_p2c32k` | Original worktree | `llama-server` TurboQuant OpenAI-compatible | GGUF Qwen3 14B Q5 | p2/c32k/np4096 | Cập nhật sang Q5 vì Q8 OOM VRAM; chạy 1/10/50 |
| TH9 | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant` | Baseline Ollama native 14B trong repo Turboquant; không dùng TurboQuant, dùng để so với TH7 | none | `bld_tq_ollama_14b` | Turboquant | Ollama native | `qwen3:14b` | api | Dùng Ollama, stop `llama-server` trước; chạy 1/10/50, `llm_max_async=1` |
| TH10 | `/home/guest/Projects/Research/Temporal-GraphRAG` | Baseline Ollama native 14B trong Original worktree; so với TH9 khi backend/model giống nhau | none | `bld_orig_ollama_14b` | Original worktree | Ollama native | `qwen3:14b` | api | Dùng Ollama, không chạy song song TH9; chạy 1/10/50, `llm_max_async=1` |
| TH11A | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2` | Tái hiện commit cũ `c1f1ea2` nguyên bản; mục tiêu là kiểm healthcheck/server có làm build dùng local thật không | `srv_th11_c1_14b_top_level` | `bld_th11a_c1_original_all` | worktree `c1f1ea2` | Config gốc, thực tế Gemini | Cache là `gemini-2.5-flash-lite` | api + server healthcheck | Có 1/5/10/50/100 success; 384 fail embedding; không dùng làm mốc local LLM |
| TH11B | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2` | Ép commit cũ dùng OpenAI-compatible local server; mục tiêu là chứng minh local Qwen3 14B Q5 thật nhưng rất chậm/incomplete | `srv_th11_c1_14b_top_level` | `bld_th11b_c1_openai14b_all` | worktree `c1f1ea2` | Ép OpenAI/local | Qwen3 14B Q5 alias `qwen3-14b-instruct` | c32k local | 1 success; 5 incomplete |

Đường nên bám để fix full local hiện tại:

```text
7B local + TurboQuant:  bám TH1 trong folder Temporal-GraphRAG-Turboquant, nhưng đổi p4 -> p2/p1.
14B local + TurboQuant: bám TH7 trong folder Temporal-GraphRAG-Turboquant, dùng Q5 và sửa embedding trước khi chạy 100/384.
TH11A/TH11B: chỉ dùng làm bằng chứng commit cũ, không dùng làm pipeline chính.
```

## 6. Các tiêu chí so sánh

| Tiêu chí | Ý nghĩa | Đọc ở đâu | Cách hiểu |
|---|---|---|---|
| Backend thực tế | Xác định build graph thật sự gọi Gemini, Ollama hay local `llama-server` | `kv_store_llm_response_cache.json`, build log dòng `[runtime]`, server log `POST /v1/chat/completions` | Quan trọng nhất, vì nhìn GPU/VRAM hoặc healthcheck có thể nhầm |
| Độ hoàn tất | Run có persist đủ docs/chunks/vector/GraphML hay chỉ dừng ở cache | Output folder | Nếu chỉ có cache thì run chưa hoàn tất, không dùng để so sánh chất lượng graph |
| Thời gian | Tổng thời gian và thời gian từng stage | Build log `[timer]`, elapsed summary | Dùng để biết bottleneck là LLM extraction, community, embedding hay persist |
| Quy mô input | Số docs và chunks | Build log, `kv_store_text_chunks.json` | Cùng số docs/chunks mới so tốc độ hợp lý |
| Quy mô graph | Entities, relations, communities, graph nodes/edges | `vdb_entities.json`, `vdb_relations.json`, `kv_store_community_reports.json`, GraphML | Dùng để so chất lượng/độ giàu graph, nhưng phải loại run có report lỗi |
| Lỗi context LLM | Prompt vượt context của local LLM hoặc context mỗi slot server | Server log, `kv_store_community_reports.json` | Thường do `-c`, `--parallel`, prompt community quá dài |
| Lỗi embedding | Text đưa vào embedding vượt context embedding model | Build log lỗi `Ollama embedding API error`, source `embedding.py` | Thường do entity/relation description quá dài sau merge |
| Sử dụng TurboQuant đúng | Có thật sự đi qua `llama-server` với KV TurboQuant không | CLI server có `-ctk/-ctv`; build CLI có `--local_llm_backend turboquant --base_url http://localhost:8080/v1` | TH3/TH4 Ollama native và TH5/TH6 Gemini không tính là TurboQuant local LLM |
| Tính mở rộng 384 docs | Có chạy full ECT-QA 384 docs ổn không | Output 384 docs và log 384 docs | TH5 và TH6 thành công đầy đủ; TH7 100 fail ở embedding input length, TH11A 384 fail ở embedding |
| Nguồn lỗi từ source/CLI/config | Lỗi do code, config hay lệnh start server | Source line, config, CLI, logs | Giúp biết cần sửa code hay chỉ sửa lệnh chạy |

Giải thích thêm:

- `LLM cache` cho biết số response LLM đã lưu và model được gọi. Đây là bằng chứng trực tiếp nhất để phân biệt Gemini/Ollama/local server.
- `Community reports` cần kiểm nội dung, không chỉ đếm số lượng. TH1/TH2 có report bị lỗi context nên dù run xong vẫn không sạch.
- `GraphML` có thể được tạo trước khi vector store persist hoàn chỉnh. TH11A 384 có GraphML nhưng vector stores không persist vì fail ở embedding.
- `--n-predict` không phải nguyên nhân chính của lỗi context TH1/TH2. Lỗi chính là prompt/input vượt context slot. Tuy nhiên `--n-predict` cao làm chậm decode và tăng ngân sách output.

## 7. Kết quả định lượng chi tiết

| TH | Docs | Status | Elapsed | Chunks | LLM cache | Entities | Relations | Communities | Graph nodes | Graph edges | Ghi chú |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| TH1 | 1 | success | 142.73s | 5 | 11 | 75 | 66 | 2 | 84 | 131 | local 7B llama-server |
| TH1 | 10 | success nhưng có report lỗi | 806.03s | 39 | 98 | 446 | 583 | 16 | 493 | 1034 | 2 community reports lỗi context trong output cuối |
| TH1 | 50 | success nhưng có report lỗi | 3283.03s | 199 | 451 | 2394 | 2795 | 75 | 2588 | 4992 | 14 community reports failed trong output cuối |
| TH1 | 100 | incomplete | n/a | 391 loaded | 24 | n/a | n/a | n/a | n/a | n/a | output chỉ có cache, log kết thúc sớm |
| TH2 | 1 | success | 84.54s | 5 | 12 | 83 | 81 | 2 | 94 | 155 | local 7B llama-server |
| TH2 | 10 | success nhưng có report lỗi | 769.63s | 39 | 95 | 566 | 684 | 22 | 598 | 1199 | 4 community reports failed trong output cuối |
| TH2 | 50 | success nhưng có report lỗi | 3303.62s | 199 | 442 | 2589 | 3010 | 69 | 2788 | 5419 | 15 community reports failed trong output cuối |
| TH2 | 100 | missing | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | không thấy log/output |
| TH3 | 1 | success | 129.81s | 5 | 14 | 77 | 72 | 4 | 85 | 145 | Ollama 7B native |
| TH3 | 10 | success | 985.14s | 39 | 97 | 290 | 373 | 18 | 365 | 680 | Ollama 7B native |
| TH3 | 50 | success | 3768.17s | 199 | 451 | 1537 | 2103 | 48 | 1923 | 3885 | Ollama 7B native |
| TH3 | 100 | missing | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | không thấy log/output |
| TH4 | 1 | success | 81.06s | 5 | 12 | 53 | 45 | 4 | 67 | 92 | Ollama 7B native |
| TH4 | 10 | success | 1064.18s | 39 | 94 | 364 | 424 | 20 | 458 | 801 | Ollama 7B native |
| TH4 | 50 | success | 6035.75s | 199 | 448 | 1499 | 2216 | 42 | 1934 | 4039 | chậm nhất nhóm 7B |
| TH4 | 100 | missing | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | không thấy log/output |
| TH5 | 1 | success | 107.00s | 5 | 15 | 128 | 64 | 12 | 133 | 128 | Gemini API |
| TH5 | 10 | success | 363.12s | 39 | 71 | 555 | 550 | 47 | 588 | 904 | Gemini API |
| TH5 | 50 | success | 1561.96s | 199 | 296 | 2266 | 2830 | 110 | 2454 | 4614 | Gemini API |
| TH5 | 100 | success | 3198.16s | 391 | 567 | 4645 | 5278 | 173 | 5150 | 8723 | Gemini API |
| TH5 | 384 | success | 12779.23s | 1462 | 1999 | 14577 | 19013 | 507 | 16214 | 31069 | full dataset success |
| TH6 | 1 | success | 124.70s | 5 | 15 | 128 | 64 | 12 | 133 | 128 | Gemini API |
| TH6 | 10 | success | 431.44s | 39 | 75 | 571 | 559 | 47 | 605 | 918 | Gemini API |
| TH6 | 50 | success | 1817.49s | 199 | 296 | 2312 | 2841 | 110 | 2499 | 4644 | Gemini API |
| TH6 | 100 | success | 3837.87s | 391 | 570 | 4507 | 5295 | 175 | 5019 | 8744 | Gemini API |
| TH6 | 384 | success nhưng có report lỗi | 11673.70s | 1462 | 1997 | 14426 | 18940 | 508 | 16048 | 30872 | Gemini API; 2 community reports failed nhưng output đầy đủ |
| TH7 | 1 | success | 292.40s | 5 | 14 | 86 | 47 | 7 | 88 | 96 | local 14B Q5 TurboQuant |
| TH7 | 5 | success | 640.70s | 19 | 47 | 257 | 141 | 20 | 269 | 276 | local 14B Q5 TurboQuant |
| TH7 | 10 | success nhưng có report lỗi | 2124.86s | 39 | 105 | 465 | 323 | 35 | 481 | 585 | 1 community report failed |
| TH7 | 50 | success nhưng có report lỗi | 8296.05s | 199 | 459 | 1978 | 1026 | 76 | 2039 | 1913 | 13 community reports failed |
| TH7 | 100 | failed | n/a | 391 | 864 | 0 persisted | 0 persisted | 0 | 3984 tạm | 4483 tạm | fail ở `entity_vdb.upsert` do Ollama embedding input length; full_docs/text_chunks rỗng |
| TH7 | 384 | incomplete/dừng sớm | n/a | 1462 loaded, dừng ở 310 | 622 | 0 persisted | 0 persisted | 0 | n/a | n/a | log dừng khoảng 310/1462 chunks; output chỉ có cache |
| TH11A | 1 | success | 86.33s | 5 | 15 | 128 | 64 | 12 | 133 | 128 | thực tế Gemini |
| TH11A | 5 | success | 154.56s | 19 | 38 | 353 | 296 | 26 | 379 | 518 | thực tế Gemini |
| TH11A | 10 | success | 195.97s | 39 | 75 | 571 | 559 | 47 | 605 | 918 | thực tế Gemini |
| TH11A | 50 | success | 636.82s | 199 | 296 | 2266 | 2830 | 110 | 2454 | 4614 | thực tế Gemini |
| TH11A | 100 | success | 1126.49s | 391 | 568 | 4576 | 5282 | 171 | 5090 | 8765 | thực tế Gemini |
| TH11A | 384 | failed | n/a | 1462 | 1627 | 0 persisted | 0 persisted | 0 persisted | 15988 GraphML | 30844 GraphML | fail ở Ollama embedding |
| TH11B | 1 | success | 442.59s | 5 | 12 | 79 | 28 | 7 | 84 | 58 | local 14B Q5 thật |
| TH11B | 5 | incomplete | n/a | 19 loaded, khoảng 4 progressed | 9 | 0 persisted | 0 persisted | 0 persisted | 0 | 0 | quá chậm hoặc bị dừng sớm |

## 8. So sánh theo tiêu chí

### 8.1 Backend thực tế

| Nhóm | Backend thực tế | Bằng chứng |
|---|---|---|
| TH1/TH2 | local `llama-server` OpenAI-compatible | Server log có `POST /v1/chat/completions`; cache model là alias local |
| TH7 | local `llama-server` OpenAI-compatible Qwen3 14B Q5 | Build log `local_llm_backend=turboquant provider=openai`; server log Q5 có `POST /v1/chat/completions 200`, `truncated = 0`, KV K `q8_0` V `turbo3` |
| TH3/TH4 | Ollama native | Build chạy `--local_llm_backend ollama`, cache model `qwen2.5:7b-instruct` |
| TH5/TH6 | Gemini API | Cache model `gemini-2.5-flash-lite` |
| TH11A | Gemini API | Config `building.provider=gemini`; cache model Gemini; server chỉ healthcheck/load model |
| TH11B | local `llama-server` Qwen3 14B Q5 | Runtime config đổi `provider=openai`, cache model `qwen3-14b-instruct` |

### 8.2 Tốc độ ở mốc 50 docs

| Nhóm | 50 docs | Nhận xét |
|---|---:|---|
| TH11A c1 + Gemini | 636.82s | Rất nhanh nhưng không phải local LLM, 384 fail embedding |
| TH5 TQ + Gemini | 1561.96s | Kết quả API sạch nhất, chạy full 384 thành công |
| TH6 Original + Gemini | 1817.49s | Gemini API; 384 hiện đã chạy full thành công nhưng không phải local LLM |
| TH1 TQ + local 7B TurboQuant | 3283.03s | Local thật, nhưng community reports có lỗi context |
| TH2 Original + local 7B TurboQuant | 3303.62s | Local thật, tương tự TH1 |
| TH3 TQ + Ollama 7B | 3768.17s | Ollama native, không TurboQuant |
| TH4 Original + Ollama 7B | 6035.75s | Chậm nhất nhóm 7B |
| TH7 TQ + local 14B Q5 TurboQuant | 8296.05s | Local thật qua llama-server Q5; 50 pass nhưng 100 fail ở embedding input length |
| TH11B local 14B Q5 | chưa xong 5 docs | 1 doc đã 442.59s |

### 8.3 Độ sạch của output

| Nhóm | Độ sạch | Lý do |
|---|---|---|
| TH5 384 | Sạch nhất trong nhóm API/Turboquant | Có đủ docs/chunks/vector/GraphML/community, không thấy lỗi context chính |
| TH6 384 | Có thể dùng làm mốc Gemini Original mới | Output đầy đủ: 384 docs, 1462 chunks, 14426 entity vectors, 18940 relation vectors, GraphML 16048/30872; có 2 community report retry fail |
| TH1/TH2 50 | Không sạch hoàn toàn | Có community reports chứa lỗi context |
| TH7 50 | Local TurboQuant Q5 pass nhưng chưa sạch tuyệt đối | Output đầy đủ đến 50 docs, nhưng có 13 community report failed |
| TH7 100 | Không dùng làm mốc | Fail ở `entity_vdb.upsert` do Ollama embedding input quá dài; vector stores rỗng |
| TH7 384 | Không dùng làm mốc | Log dừng khoảng 310/1462 chunks, output chỉ có cache |
| TH11A 384 | Không dùng làm mốc | Fail ở embedding, vector stores không persist |
| TH11B 5 | Không dùng làm mốc | Incomplete |

### 8.4 I/O, timer log hay LLM là bottleneck?

Timer logs cho thấy bottleneck là LLM và embedding, không phải ghi file:

- TH1 50 docs: total 3283.03s, LLM extraction khoảng 2987.35s, entity stage 3164.35s, community 115.92s, persist 2.59s.
- TH5 384 docs: total 12779.23s, LLM extraction khoảng 8255s, entity stage 10801s, community 1960s, persist 17s.
- TH6 384 docs: total 11673.70s, `extract_entities total` 9212.62s, `entity_vdb upsert` 323.08s, `entity_vdb_new upsert` 321.13s, `relation_vdb upsert` 495.68s, community 2440.66s, persist 18.48s.
- TH7 50 docs: total 8296.05s, extraction stage khoảng 7952.30s, vector upsert cộng lại khoảng 75.35s, community 341.94s, persist 1.62s.
- TH7 100 docs: chunk LLM extraction đi hết 391 chunks trong 15735.13s, sau đó fail ở batch embedding entity đầu tiên. Dòng `persist all storages` trong exception cleanup không làm run hợp lệ vì `kv_store_full_docs.json`, `kv_store_text_chunks.json`, vector stores đều rỗng.

Kết luận:

- I/O ghi JSON/GraphML không phải nguyên nhân chính; persist chỉ vài giây đến vài chục giây ở run pass.
- Timer logging/print không gây chậm hàng nghìn giây; phần chậm nằm ở gọi LLM local và community report.
- Với local Qwen3 14B Q5, bottleneck lớn nhất là chunk LLM extraction; lỗi scale hiện tại lại nằm ở embedding input quá dài sau khi merge entity/relation.

## 9. Audit log/output và trạng thái run hợp lệ

### 0.7 Rà soát lại log/output và điểm cần chỉnh trong file

Tôi đã rà lại các output folder và build log bằng các file sau:

```text
kv_store_full_docs.json
kv_store_text_chunks.json
kv_store_llm_response_cache.json
kv_store_community_reports.json
vdb_entities.json
vdb_relations.json
graph_chunk_entity_relation.graphml
logs/build_graph/*.log
logs/llama_server/*.log
```

Kết quả rà soát: phần lớn bảng định lượng đang đúng về docs/chunks/cache/entities/relations/GraphML. Điểm cần chỉnh là số `community report failed` ở vài dòng TH1/TH2 trước đó đang giống số lỗi/retry trong log hơn là số report lỗi cuối cùng đã persist trong `kv_store_community_reports.json`.

| TH | Docs | Đã ghi cũ | Đúng theo output persist | Cách đọc đúng |
|---:|---:|---:|---:|---|
| TH1 | 10 | 4 failed | 2 failed | 2 report cuối là `Error Report for Unknown` |
| TH1 | 50 | 28 failed | 14 failed | log có nhiều retry/error hơn, output cuối có 14 report lỗi |
| TH2 | 10 | 8 failed | 4 failed | output cuối có 4 report lỗi context |
| TH2 | 50 | 30 failed | 15 failed | output cuối có 15 report lỗi context |
| TH6 | 384 | 2 failed | 2 failed | đúng, output đủ nhưng có 2 community report fail |
| TH7 | 10 | 1 failed | 1 failed | đúng |
| TH7 | 50 | 13 failed | 13 failed | đúng |

Các trạng thái quan trọng sau audit:

| TH | Trạng thái đúng sau audit | Ý nghĩa |
|---:|---|---|
| TH5 384 | Hoàn tất sạch | Gemini API, không phải local LLM; dùng làm baseline cloud/API |
| TH6 384 | Hoàn tất, có 2 community report fail | Vẫn có đủ full docs/chunks/vector/GraphML; không dùng để kết luận TurboQuant |
| TH7 100 | Fail embedding input length | Có cache và GraphML tạm, nhưng `full_docs`, `text_chunks`, vector stores cuối cùng rỗng; không tính là run hoàn tất |
| TH7 384 | Incomplete | Chỉ có cache, thiếu full docs/chunks/vector/GraphML; không dùng làm mốc |
| TH11A 384 | Fail embedding input length | GraphML tạm có node/edge nhưng vector stores không persist; lỗi nằm ở Ollama embedding |
| TH11B 5 | Incomplete | Chỉ có cache rất ít, không có graph/vector hoàn chỉnh |

Kết luận sau audit: file nên phân biệt rõ `log retry/error count` và `final persisted failed report count`. Khi so chất lượng graph, dùng `kv_store_community_reports.json` cuối cùng; khi phân tích nguyên nhân chậm/lỗi, đọc thêm build log và server log.

## 10. Phân tích lỗi chi tiết theo TH

### 9.1 TH1/TH2: lỗi context ở community reports

Lệnh server TH1/TH2 dùng:

```text
-c 65536 --parallel 4 --n-predict 4096
```

Nhìn như context 64k, nhưng server log cho thấy mỗi slot chỉ khoảng 16k context. Khi prompt community report vượt 16k, server trả lỗi:

```text
request (...) exceeds available context size (16384)
```

Nguồn lỗi:

- Lỗi đến từ CLI start server và cách chia context theo `--parallel`.
- Không phải do chunk size/overlap, vì các TH đều có số chunks giống nhau ở cùng số docs.
- Không phải do I/O/logging.
- `--n-predict 4096` không phải gốc lỗi context, nhưng làm request lâu hơn.

File cần đọc:

```text
Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_7b_p4c64k_20260522_105607.log
Temporal-GraphRAG/logs/llama_server/cmp_orig_turbo_7b_p4c64k_20260522_121901.log
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_050docs/kv_store_community_reports.json
Temporal-GraphRAG/outputs/build_graph/cmp_orig_turbo_7b_p4c64knp4096_050docs/kv_store_community_reports.json
```

Số lỗi đã thấy:

- TH1 10 docs: 2 failed community reports trong output cuối.
- TH1 50 docs: 14 failed community reports trong output cuối.
- TH2 10 docs: 4 failed community reports trong output cuối.
- TH2 50 docs: 15 failed community reports trong output cuối.

Cách xử lý:

- Dùng `--parallel 2` với `-c 65536` để tăng context mỗi slot lên khoảng 32k.
- Nếu vẫn lỗi, dùng `--parallel 1`.
- Đồng bộ build `--llm_max_async` bằng hoặc nhỏ hơn server `--parallel`.
- Giảm `--n-predict` xuống 2048 hoặc 3072 để giảm thời gian decode.
- Nếu prompt community vẫn quá dài, tắt community summary khi build local hoặc giảm token budget của community report.

### 9.2 TH1 100 docs: incomplete

TH1 100 có log/output nhưng không hoàn chỉnh:

```text
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_100docs.log
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_100docs
```

Dấu hiệu:

- Log có loaded 100 docs và 391 chunks.
- Output chỉ có khoảng 24 cache entries.
- Không có đủ vector stores và GraphML final.
- Không thấy traceback rõ trong đoạn log hiện có.

Kết luận: run bị dừng sớm hoặc bị ngắt. Không dùng TH1 100 để so sánh chất lượng hoặc tốc độ full.

### 9.3 TH3/TH4: Ollama native, không phải TurboQuant

TH3/TH4 dùng:

```text
--local_llm_backend ollama
--base_url http://localhost:11434
```

Vì vậy:

- Không đi qua `llama-server` của `llama-cpp-turboquant`.
- Không dùng KV TurboQuant `-ctk/-ctv`.
- Không có server log `/v1/chat/completions` từ `llama-server`.

Kết luận: TH3/TH4 hữu ích để so với Ollama native, nhưng không chứng minh được TurboQuant.

### 9.4 TH5/TH6: Gemini API, không phải local LLM

TH5/TH6 dùng:

```text
--provider gemini
--model gemini-2.5-flash-lite
```

TH5 384 là kết quả full dataset thành công:

```text
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_gemini_api_384docs.log
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_gemini_api_384docs
```

TH6 384 hiện cũng đã có log/output xác nhận full dataset thành công:

```text
Temporal-GraphRAG/logs/build_graph/cmp_orig_gemini_api_384docs.log
Temporal-GraphRAG/outputs/build_graph/cmp_orig_gemini_api_384docs
```

Bằng chứng TH6 384 pass:

```text
✅ Graph building completed successfully!
✅ Total elapsed: 11673.70s
[build-stage] new chunks: 1462
[build-detail] extract_entities total: 9212.62s
[build-detail] entity_vdb upsert: entities=14426: 323.08s
[build-detail] entity_vdb_new upsert: entities=14426: 321.13s
[build-detail] relation_vdb upsert: relations=18940: 495.68s
[build-detail] generate temporal community reports: reports=508: 2440.66s
[build-stage] persist all storages: 18.48s
```

Output TH6 384 đã đủ file:

```text
graph_chunk_entity_relation.graphml
kv_store_full_docs.json
kv_store_text_chunks.json
kv_store_community_reports.json
kv_store_llm_response_cache.json
vdb_entities.json
vdb_entities_new.json
vdb_relations.json
```

Số lượng output TH6 384:

| File/output | Count |
|---|---:|
| `kv_store_full_docs.json` | 384 |
| `kv_store_text_chunks.json` | 1462 |
| `kv_store_community_reports.json` | 508 |
| `kv_store_llm_response_cache.json` | 1997 |
| `vdb_entities.json` data/embeddings | 14426 |
| `vdb_entities_new.json` data/embeddings | 14426 |
| `vdb_relations.json` data/embeddings | 18940 |
| `graph_chunk_entity_relation.graphml` | 16048 nodes / 30872 edges |

Điểm cần lưu ý: TH6 384 có 2 dòng `ERROR - Failed to generate community report after 3 attempts`, nhưng đây là lỗi ở một vài community report, không làm build fail. Run vẫn persist đầy đủ output và có summary success.

### 9.4.1 Bổ sung TH7 Q5 và lỗi embedding input length

TH7 là case đúng mục tiêu áp dụng TurboQuant vào local LLM trong repo Turboquant:

```text
[runtime] local_llm_backend=turboquant provider=openai model=qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 wire_protocol=openai-compatible-local
[runtime] llm_base_url=http://localhost:8080/v1
[runtime] embedding_provider=ollama embedding_base_url=http://localhost:11434
```

Server log TH7 Q5 xác nhận `llama-server` đang dùng TurboQuant KV:

```text
llama_context: n_ctx         = 32768
llama_context: n_ctx_seq     = 16384
llama_kv_cache: size = 1860.00 MiB (...), K (q8_0): 1360.00 MiB, V (turbo3): 500.00 MiB
srv    load_model: initializing slots, n_slots = 2
slot   load_model: id 0 | new slot, n_ctx = 16384
slot   load_model: id 1 | new slot, n_ctx = 16384
srv log_server_r: done request: POST /v1/chat/completions 127.0.0.1 200
slot release: ... truncated = 0
```

Kết quả TH7 hiện tại:

| Docs | Status | Elapsed | Chunks | Entity vectors | Relation vectors | Ghi chú |
|---:|---|---:|---:|---:|---:|---|
| 1 | pass | 292.40s | 5 | 86 | 47 | local 14B Q5 thật |
| 5 | pass | 640.70s | 19 | 257 | 141 | local 14B Q5 thật |
| 10 | pass có cảnh báo | 2124.86s | 39 | 465 | 323 | 1 community report failed |
| 50 | pass có cảnh báo | 8296.05s | 199 | 1978 | 1026 | 13 community report failed |
| 100 | fail | n/a | 391 | 0 persisted | 0 persisted | fail ở `entity_vdb.upsert` do Ollama embedding input length |
| 384 | incomplete/dừng sớm | n/a | log dừng ở 310/1462 | 0 persisted | 0 persisted | output chỉ có cache |

Tại thời điểm kiểm tra, không còn process `build_graph.py`/`llama-server` TH7 đang chạy. File `cmp_tq_turbo_14bq5_p2c32knp4096_384docs.log` dừng ở khoảng `Processed 310(21%) chunks`, mtime `2026-05-23 11:46`, output folder 384 chỉ có `kv_store_llm_response_cache.json`. Vì vậy xem TH7 384 là run dừng sớm, không phải run đang chờ hoàn tất.

Lỗi thật của TH7 100:

```text
❌ Error during graph building: Ollama embedding API error 500: {"error":"the input length exceeds the context length"}
Traceback:
build_graph.py
-> temporal_graphrag.py
-> tgrag/src/core/building.py:1257 await entity_vdb.upsert(data_for_vdb)
-> tgrag/src/storage/vector_nanovectordb.py:120 embeddings_list = await asyncio.gather(...)
-> tgrag/src/build.py:86 embedding_wrapper
-> tgrag/src/llm/embedding.py:152 raise Exception(...)
```

Đoạn source đang tạo content embedding entity trong repo Turboquant hiện tại:

```python
# /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/core/building.py
if entity_vdb is not None and entity_vdb_new is not None:
    data_for_vdb = {
        compute_mdhash_id(dp["entity_name"], prefix="ent-"): {
            "content": dp["entity_name"] + " " + dp.get("description", ""),
            "entity_name": dp["entity_name"],
            "description": dp.get("description", ""),
            "entity_type": dp.get("entity_type", ""),
        }
        for dp in all_entities_data
    }
    await entity_vdb.upsert(data_for_vdb)
```

Đoạn source vector store gửi nguyên `content` sang embedding:

```python
# /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/vector_nanovectordb.py
contents = [v["content"] for v in data.values()]
batches = [
    contents[i : i + self._max_batch_size]
    for i in range(0, len(contents), self._max_batch_size)
]
embeddings_list = await asyncio.gather(
    *[self.embedding_func(batch) for batch in batches]
)
```

Đoạn source Ollama embedding nhận text và raise lỗi nếu API trả 500:

```python
# /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/embedding.py
for text in texts:
    payload = {
        "model": model,
        "prompt": text,
    }
    async with session.post(
        f"{ollama_url}/api/embeddings",
        json=payload
    ) as response:
        if response.status != 200:
            error_text = await response.text()
            raise Exception(f"Ollama embedding API error {response.status}: {error_text}")
```

Điểm quan trọng: TH7 100 không fail do `llama-server` context/KV. LLM extraction đã xử lý xong `391(100%) chunks` trước khi lỗi. Lỗi xảy ra sau đó, ở bước vector embedding entity bằng Ollama `nomic-embed-text`.

So sánh độ dài description trong GraphML để hiểu vì sao fail không giống nhau giữa TH6/TH7/TH11A:

| Run | Max node description | Max edge description | Kết luận |
|---|---:|---:|---|
| TH5 384 Gemini TQ | 2934 chars | 2971 chars | Pass embedding |
| TH6 384 Gemini Original | 2934 chars | 2971 chars | Pass embedding |
| TH7 50 local 14B Q5 | 9308 chars | 1111 chars | Vẫn pass nhưng đã có entity rất dài |
| TH7 100 local 14B Q5 | 16408 chars | 2014 chars | Fail embedding ở entity vector upsert |
| TH11A 384 c1 Gemini | 29523 chars | 2971 chars | Fail embedding |

Diễn giải cho bài toán Temporal GraphRAG:

- Chunk extraction thành công chưa đủ để kết luận build graph thành công. Sau extraction còn merge entity/relation, tạo GraphML, rồi embed entity/relation vào vector store.
- Temporal GraphRAG dễ tạo entity thời gian và entity tổng quát bị lặp qua nhiều transcript, ví dụ `CHINA`, `FREE CASH FLOW`, `2023`, `2021-Q2`, `2022-Q4`.
- Khi merge description, một entity có thể tích lũy rất nhiều đoạn mô tả qua nhiều chunks/docs. Source hiện tại ghép thẳng `entity_name + description` rồi gửi sang Ollama embedding.
- TH6 384 pass vì output Gemini hiện tại giữ description tối đa khoảng 2934 chars, còn TH7 local Qwen3 14B Q5 tạo description dài hơn rất nhiều. Đến 100 docs đã thấy entity `CHINA` khoảng 16408 chars, làm Ollama embedding vượt context.
- TH7 50 pass nhưng đã có entity `JD.COM` khoảng 9308 chars, nên 50 docs chưa phải bằng chứng đủ an toàn cho 100/384.
- TH7 384 log dừng ở khoảng `Processed 310(21%) chunks`, output chỉ có cache. Không dùng TH7 384 hiện tại để kết luận tốc độ hay chất lượng vì run chưa đi tới bước persist.

### 9.5 TH11A: vì sao có VRAM nhưng vẫn là Gemini?

TH11A start server Qwen3 14B Q5 nên GPU/VRAM bị chiếm. Nhưng build graph vẫn gọi Gemini.

Bằng chứng source:

- [build_graph.py TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/build_graph.py:42) có hàm `xac_nhan_turboquant`.
- [build_graph.py TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/build_graph.py:67) gọi healthcheck ngay khi chạy file.
- [config.yaml TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/configs/config.yaml:14) đặt `building.provider: gemini`.
- [config.yaml TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/configs/config.yaml:15) đặt `building.model: gemini-2.5-flash-lite`.
- [build_graph.py TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/build_graph.py:381) gọi `create_temporal_graphrag_from_config` với `config_type="building"`.
- [build.py TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/src/build.py:157) load config rồi lấy provider/model từ block `building`.
- [config_loader.py TH11](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/src/config/config_loader.py:48) chỉ lấy config theo `config_type`.

Bằng chứng output:

```text
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_050docs_20260522_204618/kv_store_llm_response_cache.json
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_384docs_20260522_204618/kv_store_llm_response_cache.json
```

Cache ghi model `gemini-2.5-flash-lite`, không phải `qwen3-14b-instruct`.

Kết luận: TH11A chỉ chứng minh config cũ gây nhầm backend. Nó không chứng minh TurboQuant local nhanh.

### 9.6 TH11A 384: lỗi Ollama embedding context

TH11A chạy đúng source/config cũ của commit `c1f1ea2`, nhưng kết quả log chứng minh vấn đề không nằm ở `llama-server`.

#### Kết luận từ log TH11A

| Docs | Kết quả | Thời gian |
|---:|---|---:|
| 001 | pass | 86.33s |
| 005 | pass | 154.56s |
| 010 | pass | 195.97s |
| 050 | pass | 636.82s |
| 100 | pass | 1126.49s |
| 384 | fail | sau khi xử lý xong 1462 chunks |

Log 384 cho thấy extraction đã đi hết toàn bộ chunks trước khi fail ở embedding:

```text
Processed 1462(100%) chunks
41848 entities(duplicated)
20584 relations(duplicated)
```

Lỗi thật:

```text
Ollama embedding API error 500: {"error":"the input length exceeds the context length"}
```

Pipeline lỗi:

```text
extract_entities
-> entity_vdb.upsert(data_for_vdb)
-> vector_nanovectordb.py
-> ollama_embedding(...)
-> /api/embeddings
```

Cache xác nhận TH11A không dùng `llama-server` để extract LLM:

```text
TH11A cache model = gemini-2.5-flash-lite
```

Nghĩa là:

- `llama-server` được start vì top-level healthcheck trong `build_graph.py`.
- LLM extraction vẫn dùng Gemini vì `building.provider = gemini`.
- Embedding dùng Ollama `nomic-embed-text`.
- 384 fail vì text đưa vào Ollama embedding quá dài.

#### Source cũ tạo content embedding quá dài

Folder/source áp dụng cho TH11A:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2
```

File source tạo payload cho entity/relation vector DB:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/src/core/building.py
```

Đoạn source quan trọng:

```python
logger.info("Starting vector database upserts...")
if entity_vdb is not None and entity_vdb_new is not None:
    data_for_vdb = {
        compute_mdhash_id(dp["entity_name"], prefix="ent-"): {
            "content": dp["entity_name"] + " " + dp.get("description", ""),
            "entity_name": dp["entity_name"],
            "description": dp.get("description", ""),
            "entity_type": dp.get("entity_type", ""),
        }
        for dp in all_entities_data
    }
    data_for_vdb_new = {
        compute_mdhash_id(dp["entity_name"], prefix="ent-"): {
            "content": dp["entity_name"] + " " + dp.get("description", ""),
            "entity_name": dp["entity_name"],
            "description": dp.get("description", ""),
            "entity_type": dp.get("entity_type", ""),
        }
        for dp in all_entities_data
    }
    
    logger.info(f"Upserting {len(data_for_vdb)} entities to entity_vdb...")
    await entity_vdb.upsert(data_for_vdb)
    
    logger.info(f"Upserting {len(data_for_vdb_new)} new entities to entity_vdb_new...")
    await entity_vdb_new.upsert(data_for_vdb_new)
if relation_vdb is not None:
    valid_relations_data = [dp for dp in all_relations_data if dp is not None]
    data_for_vdb_relation = {
        compute_mdhash_id(dp["src_id"]+'_'+dp["tgt_id"]+'_'+timestamp, prefix="rel-"): {
            "content": des,
            "entity_name": dp["src_id"]+'_'+dp["tgt_id"]+'_'+timestamp,
        }
        for dp in valid_relations_data for timestamp, des in dp.get('description', {}).items()
    }
    await relation_vdb.upsert(data_for_vdb_relation)
```

Điểm gây lỗi nằm ở dòng logic này:

```python
"content": dp["entity_name"] + " " + dp.get("description", "")
```

Khi chạy 384 docs, một số entity/relation description bị merge/gom quá dài. Source gửi nguyên văn `content` sang Ollama embedding `nomic-embed-text`, nên Ollama báo vượt context.

#### Source vector store và embedding hiện tại đang gửi nguyên content

File vector store:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/src/storage/vector_nanovectordb.py
```

Đoạn upsert cần đối chiếu:

```python
list_data = [
    {
        "__id__": k,
        **{k1: v1 for k1, v1 in v.items() if k1 in self.meta_fields},
    }
    for k, v in data.items()
]

contents = [v["content"] for v in data.values()]
batches = [
    contents[i : i + self._max_batch_size]
    for i in range(0, len(contents), self._max_batch_size)
]

logger.info(f"Generating embeddings for {len(batches)} batches...")
embeddings_list = await asyncio.gather(
    *[self.embedding_func(batch) for batch in batches]
)
```

File embedding:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/src/llm/embedding.py
```

Đoạn gọi Ollama:

```python
async def ollama_embedding(
    texts: List[str],
    model: str = "nomic-embed-text",
    base_url: Optional[str] = None
) -> np.ndarray:
    """Generate embeddings using Ollama."""
    import aiohttp
    
    client_manager = get_client_manager()
    ollama_url = client_manager.get_ollama_base_url(base_url)
    
    embeddings = []
    async with aiohttp.ClientSession() as session:
        for text in texts:
            payload = {
                "model": model,
                "prompt": text,
            }
            
            async with session.post(
                f"{ollama_url}/api/embeddings",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama embedding API error {response.status}: {error_text}")
```

Chuỗi lỗi vì vậy là:

```text
content quá dài
-> contents = [v["content"] ...]
-> embedding_func(batch)
-> ollama_embedding(texts)
-> POST /api/embeddings
-> Ollama 500 input length exceeds context length
```

#### Vì sao 100 docs pass nhưng 384 docs fail?

- 100 docs chưa làm description tích lũy dài tới mức vượt context.
- 384 docs tạo nhiều entity/relation trùng hơn, merge description dài hơn.
- Entity dạng thời gian như `2023`, `2021-Q2`, `2022-Q4` dễ gom mô tả từ nhiều chunks, làm content embedding phình to.
- Output TH11A 384 từng thấy entity description rất dài, ví dụ node `2023` khoảng 29523 ký tự.

#### Log hiện còn thiếu

Source cũ thiếu log để biết chính xác item nào quá dài:

- Không log batch embedding nào fail.
- Không log max length của content.
- Không log `entity_name` gây lỗi.
- Không log riêng thời gian `entity_vdb`, `entity_vdb_new`, `relation_vdb` upsert.
- Không log top-N content dài nhất trước embedding.

Do đó kết luận hiện tại chắc ở mức:

```text
Lỗi nằm ở embedding input quá dài, không phải llama-server.
```

Chưa thể chỉ chính xác entity nào gây fail nếu chưa thêm log.

#### Diff code đề xuất để sửa/log đúng chỗ

Đây là diff minh họa nên đưa vào `vector_nanovectordb.py`. Mục tiêu là truncate trước khi embedding và log item bị truncate. Diff này là hướng sửa đề xuất, không phải nội dung đã áp dụng trong benchmark cũ.

```diff
diff --git a/tgrag/src/storage/vector_nanovectordb.py b/tgrag/src/storage/vector_nanovectordb.py
--- a/tgrag/src/storage/vector_nanovectordb.py
+++ b/tgrag/src/storage/vector_nanovectordb.py
@@
-        contents = [v["content"] for v in data.values()]
+        embedding_max_chars = int(self.global_config.get("embedding_max_chars", 8000))
+        contents = []
+        truncated_items = []
+
+        for item_id, item in data.items():
+            content = item.get("content", "")
+            if not isinstance(content, str):
+                content = str(content)
+
+            original_len = len(content)
+            if original_len > embedding_max_chars:
+                truncated_items.append({
+                    "id": item_id,
+                    "entity_name": item.get("entity_name"),
+                    "original_chars": original_len,
+                    "truncated_chars": embedding_max_chars,
+                    "namespace": self.namespace,
+                })
+                content = content[:embedding_max_chars]
+
+            contents.append(content)
+
+        if truncated_items:
+            logger.warning(
+                "Truncated %s oversized embedding inputs in namespace=%s; top examples=%s",
+                len(truncated_items),
+                self.namespace,
+                truncated_items[:10],
+            )
```

Nếu muốn log batch fail rõ hơn, bọc phần `asyncio.gather`:

```diff
@@
-        embeddings_list = await asyncio.gather(
-            *[self.embedding_func(batch) for batch in batches]
-        )
+        try:
+            embeddings_list = await asyncio.gather(
+                *[self.embedding_func(batch) for batch in batches]
+            )
+        except Exception:
+            lengths = sorted(
+                [(i, len(c)) for i, c in enumerate(contents)],
+                key=lambda x: x[1],
+                reverse=True,
+            )[:10]
+            logger.exception(
+                "Embedding failed in namespace=%s; total_items=%s batches=%s top_content_lengths=%s",
+                self.namespace,
+                len(contents),
+                len(batches),
+                lengths,
+            )
+            raise
```

Nếu muốn sửa ở `embedding.py`, có thể thêm guard ngay trước payload, nhưng nhược điểm là không biết `entity_name` hoặc `namespace`:

```diff
diff --git a/tgrag/src/llm/embedding.py b/tgrag/src/llm/embedding.py
--- a/tgrag/src/llm/embedding.py
+++ b/tgrag/src/llm/embedding.py
@@
-        for text in texts:
+        max_chars = int(os.getenv("TG_RAG_EMBEDDING_MAX_CHARS", "8000"))
+        for text in texts:
+            if len(text) > max_chars:
+                text = text[:max_chars]
             payload = {
                 "model": model,
                 "prompt": text,
             }
```

Khuyến nghị thực tế:

- Sửa ở `vector_nanovectordb.py` tốt hơn vì có `item_id`, `entity_name`, `namespace`.
- Sửa ở `embedding.py` chỉ là lớp bảo vệ cuối cùng.
- Nếu muốn sạch hơn nữa, cap description ngay sau bước merge entity/relation để graph không phình description quá mức.

#### Hướng xử lý đúng cho TH11A

Có 2 hướng:

1. Sửa source an toàn: trước khi gọi Ollama embedding, truncate content theo token/char limit và log item bị truncate.
2. Nếu chỉ muốn tái hiện TH11A không sửa code: chạy tới 100 docs là hợp lệ; full 384 docs có khả năng fail lại cùng lỗi.

Với TH11A original, đổi CLI không giải quyết triệt để vì `c1f1ea2` dùng config cũ và embedding Ollama `nomic-embed-text`, không có CLI rõ để đổi embedding model.

### 9.7 TH11B: đúng local 14B nhưng quá chậm

TH11B ép config:

```text
building.provider = openai
building.model    = qwen3-14b-instruct
OPENAI_BASE_URL   = http://localhost:8080/v1
```

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

### 9.8 TH11 server 14B Q8: lỗi OOM KV cache

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

- Qwen3 14B Q8 khoảng 14.61 GiB.
- Cần thêm KV cache khoảng 1.86 GiB ở c32768.
- GPU còn khoảng 15 GiB free không đủ cho model weights + KV.

Cách xử lý:

- Dùng Qwen3-14B-Q5_0.gguf thay vì Q8.
- Giữ `-c 32768`, `--parallel 1` trước.
- Nếu vẫn OOM, giảm `-c` hoặc GPU layers, nhưng giảm context sẽ tăng rủi ro lỗi community prompt.

### 9.9 Bảng lý do lỗi/nghi vấn các TH còn lại

| TH | Vấn đề | Nguyên nhân hợp lý từ log/source | Hướng xử lý |
|---:|---|---|---|
| TH1 | 10/50 docs có community report lỗi context | `-c 65536 --parallel 4` làm mỗi slot chỉ khoảng 16k context; community prompt vượt slot context | Dùng `--parallel 2` hoặc `1`, đồng bộ `--llm_max_async`, giảm `--n-predict` |
| TH1 | 100 docs incomplete | Log/output dừng sớm, chỉ có cache, không đủ GraphML/vector | Không dùng làm mốc; chạy lại sau khi sửa context |
| TH2 | 10/50 docs có community report lỗi context | Cùng server config như TH1, per-slot context quá thấp | Đổi sang Q5/Q8 phù hợp, dùng `--parallel 2` hoặc `1` |
| TH3 | Chậm hơn Gemini, không phải TurboQuant | Ollama native, không qua `llama-server`, không dùng `-ctk/-ctv` | Chỉ dùng làm baseline Ollama |
| TH4 | Chậm nhất nhóm 7B | Original worktree + Ollama native; không TurboQuant | Không so với TurboQuant trực tiếp |
| TH5 | Thành công 384 nhưng không phải local LLM | Gemini API làm LLM extraction; Ollama chỉ embedding | Dùng làm mốc cloud/API, không dùng làm mốc local |
| TH6 | 384 pass nhưng có 2 community report retry fail | Log/output mới đã persist đủ docs/chunks/vector/GraphML; lỗi community report không làm build fail | Dùng làm mốc Gemini Original, nhưng không dùng để kết luận local LLM/TurboQuant |
| TH7 | 100 fail ở embedding input length | Local Qwen3 14B Q5 tạo entity description dài; source gửi nguyên `entity_name + description` sang Ollama embedding; fail tại `entity_vdb.upsert` | Q5 server đúng, nhưng cần truncate/log embedding content trước khi chạy 100/384; hiện chỉ coi 1/5/10/50 là mốc đã pass |
| TH8 | Cần đổi Q8 sang Q5 | Q8 đã fail VRAM/KV ở TH11 server Q8 | Dùng Q5, `-c 32768 --parallel 2` |
| TH9 | Không chạy chung llama-server | Ollama 14B sẽ tranh GPU nếu llama-server đang giữ model | Stop llama-server trước, `llm_max_async=1` |
| TH10 | Không chạy song song TH9 | Cùng dùng Ollama `qwen3:14b`, dễ tranh GPU/RAM | Chạy tuần tự, `llm_max_async=1` |
| TH11A | 384 fail embedding | Entity/relation content quá dài gửi vào Ollama embedding | Truncate/log content trước embedding |
| TH11B | 1 doc pass nhưng rất chậm; 5 docs incomplete | Local Qwen3 14B Q5 thật, decode chậm hơn Gemini/7B | Chỉ test 1/5/10 trước, không chạy 384 ngay |

## 11. Hướng fix full 384 trước khi chạy lại local

### 16.1 Thêm guard truncate embedding

Vấn đề TH11A 384 và TH7 100 đều nằm ở embedding content quá dài. Nên sửa trước khi gọi embedding:

- [vector_nanovectordb.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/vector_nanovectordb.py:107)
- [embedding.py](/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/embedding.py:118)

Khuyến nghị:

```text
Nếu len hoặc token_count content vượt giới hạn embedding, truncate và log warning.
Log namespace, id, độ dài cũ, độ dài mới.
```

### 16.2 Giới hạn description sau merge entity/relation

Nếu một entity như `2023`, `CHINA`, `FREE CASH FLOW`, `2021-Q2` gom quá nhiều mô tả, description sẽ phình rất lớn. Nên cap description sau merge, ví dụ 2048 hoặc 4096 tokens, trước khi ghi vào vector store. TH7 100 đã thấy max node description khoảng 16408 ký tự; TH11A 384 từng thấy node `2023` khoảng 29523 ký tự.

### 16.3 Ghi log nguồn backend ở đầu run

Repo Turboquant hiện tại đã có runtime print. Khi chạy phải giữ dòng này trong log để tránh nhầm như TH11A.

### 16.4 Logging còn thiếu theo `md/debug/add_runtime_logging_plan.md`

File `md/debug/add_runtime_logging_plan.md` đang đúng hướng là cần runtime log chi tiết hơn, nhưng hiện vẫn thiếu các điểm quan trọng cho lỗi TH7/TH11A:

- Log top-N `content` dài nhất trước khi gọi embedding.
- Log namespace vector đang upsert: `entities`, `entities_new`, `relations`.
- Log batch index, item id, entity name, độ dài ký tự và nếu có thì token estimate khi embedding fail.
- Tách timer rõ `chunk LLM extraction`, `entity merge`, `entity_vdb.upsert`, `entity_vdb_new.upsert`, `relation_vdb.upsert`, `community reports`, `persist`.
- Ghi JSONL usage theo `TG_RAG_USAGE_LOG` nếu muốn ước lượng token/cost/request count; hiện plan mới nêu convention, source chưa có producer đầy đủ.

Kết luận vận hành hiện tại: folder nên tiếp tục dùng để apply TurboQuant local LLM là `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant`, với Qwen3 14B Q5 `-c 32768 --parallel 2 --n-predict 4096` và build `--llm_max_async 2` cho mốc nhỏ. Tuy nhiên trước khi chạy 100/384 ổn định cần sửa guard/truncate embedding; nếu chưa sửa thì chỉ nên dùng 1/5/10/50 để benchmark local.

## 12. Config hiện tại, GPU 16GB và hướng chạy ổn định

Phần này bổ sung sau khi đọc lại:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/configs/config.yaml
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/configs/config_eval_ollama_nomic_fast.yaml
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/configs/prompts.yaml
```

Kết luận ngắn: folder nên tiếp tục dùng để apply TurboQuant local LLM là:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
```

Không nên dùng worktree TH11 `c1f1ea2` làm folder chạy chính, vì TH11 dùng để tái hiện commit cũ và có healthcheck/top-level config dễ gây nhầm backend. Repo Turboquant hiện tại có CLI override rõ hơn cho local `llama-server`.

### 0.1 Config hiện tại đang quyết định gì?

| File/config | Giá trị hiện tại | Tác động thực tế | Nên hiểu khi chạy local |
|---|---|---|---|
| `config.yaml -> building.provider` | `gemini` | Nếu không truyền CLI override, build graph dùng Gemini API cho LLM extraction | Muốn local LLM phải truyền `--local_llm_backend turboquant --model ... --base_url ...` hoặc sửa `building.provider/model` |
| `config.yaml -> building.model` | `gemini-2.5-flash-lite` | Đây là lý do TH11A nhìn có server nhưng cache vẫn là Gemini | Không dùng top-level `llm:` để kết luận build đang dùng local |
| `config.yaml -> building.embedding_provider` | `ollama` | Build dùng Ollama embedding | Nhưng source hiện chưa cho chọn `embedding_model` từ CLI/config chính |
| `config.yaml -> chunk_size/chunk_overlap` | `1200/100` | Document đã được cắt sliding/fixed window trước extraction | Hợp lý cho ECT-QA; chưa phải nguyên nhân chính của lỗi 100/384 |
| `config.yaml -> enable_community_summary` | `true` | Có thêm bước tạo community report | Cần cho GraphRAG, nhưng local LLM sẽ chậm và dễ gặp prompt dài nếu graph lớn |
| `config_eval_ollama_nomic_fast.yaml -> disable_entity_summarization` | `true` | Bỏ qua bước LLM summarize description entity/relation | Hữu ích để tránh stall, nhưng có thể làm description dài hơn và tăng rủi ro embedding input quá dài |
| `querying.top_k` | `50` | Query lấy nhiều seed/relation hơn | Tốt cho recall, nhưng embedding quality sai sẽ kéo sai subgraph nhiều hơn |
| `querying.seed_node_method` | `relations` | Retrieval nghiêng về relation seed | Với ECT-QA temporal, relation embedding rất quan trọng |
| `querying.enable_subgraph` | `true` | Có traverse subgraph sau retrieval | Nếu seed node sai thì temporal neighborhood sai, answer dễ sai |
| `llm:` block cuối `config.yaml` | `provider=openai`, `model=qwen3-14b-instruct` | Không phải block build chính trong flow hiện tại | Build dùng block `building` vì `build_graph.py` gọi `config_type="building"` |

Bằng chứng source: `config_loader.py` chỉ lấy đúng block theo `config_type`, rồi mới merge CLI override:

```python
def get_config(self, config_type: Literal["building", "querying"], override_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get configuration based on task type as a dictionary."""
    # Get config by type
    config = self.config.get(config_type, {}).copy()

    # Override with provided arguments
    if override_args:
        config.update({k: v for k, v in override_args.items() if v is not None})
```

Vì vậy khi chạy build, thứ tự ưu tiên là:

```text
CLI override trong build_graph.py
-> block building trong config.yaml
-> default trong source
```

Không phải:

```text
block llm cuối file config.yaml
```

### 0.2 Source hiện tại vì sao vẫn dùng `nomic-embed-text`?

`build_graph.py` hiện chỉ có CLI cho provider/base URL embedding:

```python
parser.add_argument(
    '--embedding_provider',
    choices=['ollama', 'openai', 'azure', 'bedrock'],
    default=None,
    help='Override embedding provider from config'
)
parser.add_argument(
    '--embedding_base_url',
    type=str,
    default=None,
    help='Embedding base URL, e.g. http://localhost:11434 for Ollama embeddings'
)
```

Chưa có:

```text
--embedding_model
--embedding_dim
--embedding_max_chars
--embedding_max_tokens
```

Trong `tgrag/src/build.py`, nhánh Ollama đang hardcode dimension 768 và không truyền model:

```python
elif embedding_provider == "ollama":
    return await ollama_embedding(texts, base_url=base_url)
...
elif embedding_provider == "ollama":
    return EmbeddingFunc(
        embedding_dim=768,
        func=embedding_wrapper,
        max_token_size=8192
    )
```

Trong `tgrag/src/llm/embedding.py`, model mặc định là `nomic-embed-text` và source gọi endpoint legacy `/api/embeddings`:

```python
async def ollama_embedding(
    texts: List[str],
    model: str = "nomic-embed-text",
    base_url: Optional[str] = None
) -> np.ndarray:
    ...
    for text in texts:
        payload = {
            "model": model,
            "prompt": text,
        }
        
        async with session.post(
            f"{ollama_url}/api/embeddings",
            json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Ollama embedding API error {response.status}: {error_text}")
```

Hệ quả: dù chạy `ollama pull bge-m3` hoặc `ollama pull qwen3-embedding:4b`, build vẫn dùng `nomic-embed-text` nếu chưa sửa source truyền `embedding_model`.

### 0.3 `nomic-embed-text` có nâng context lên 8192 được không?

Không nên coi đây là cách sửa chính cho pipeline hiện tại.

Lý do:

| Điểm kiểm tra | Kết luận |
|---|---|
| Ollama docs chung | Có thể set context server bằng `OLLAMA_CONTEXT_LENGTH=8192 ollama serve` hoặc API options `num_ctx` cho một số endpoint |
| Ollama model page của `nomic-embed-text` | Các biến thể `nomic-embed-text` trong Ollama library đang ghi `2K context window` |
| Source hiện tại | Gọi `/api/embeddings` legacy, payload chỉ có `model` và `prompt`, không có `options.num_ctx`, không có `truncate` |
| Log TH7/TH11A | Đã có lỗi thật: `input length exceeds the context length` |
| Temporal GraphRAG | Entity/relation description sau merge có thể lên 16k-29k chars, nên 8192 token nếu có cũng không phải bảo đảm tuyệt đối |

Ollama API mới `/api/embed` có trường `truncate` mặc định `true`, có `dimensions`, `options`. Nhưng source hiện tại chưa dùng endpoint đó. Vì vậy với code hiện tại, câu trả lời vận hành là:

```text
Không nên dựa vào việc tăng context của nomic lên 8192.
Phải cap/truncate/log embedding input trước.
Muốn ổn định hơn cho full 384 docs thì nên chuyển sang bge-m3 hoặc Qwen3 embedding sau khi patch embedding_model/dim.
```

Nếu vẫn muốn thử `nomic` 8192, cần test riêng ngoài pipeline:

```bash
OLLAMA_CONTEXT_LENGTH=8192 ollama serve
ollama ps

curl http://localhost:11434/api/embed -d '{
  "model": "nomic-embed-text",
  "input": "đoạn text dài cần test",
  "truncate": false
}'
```

Nếu request dài vẫn lỗi thì model/package đang không nhận context đó. Nếu không lỗi thì vẫn cần patch source sang `/api/embed` và truyền options/truncate rõ ràng.

### 0.4 Setup nên chọn cho RTX 5070 Ti 16GB

Mục tiêu của bạn là apply TurboQuant vào local LLM, nên phần LLM extraction/community nên đi qua `llama-server`, còn embedding có thể chạy qua Ollama hoặc service riêng.

| Mục tiêu | Setup nên dùng | Lý do |
|---|---|---|
| Benchmark local LLM sạch tới 50 docs | Qwen3 14B Q5 + TurboQuant KV, embedding `nomic` hiện tại | Đã có TH7 1/5/10/50 pass; đủ đo tốc độ LLM local |
| Full 100/384 ổn định | Qwen3 14B Q5 + TurboQuant KV, embedding `bge-m3`, có cap/log embedding content | TH7 100 fail ở embedding input length, không phải server; cần đổi/cap embedding trước |
| Chất lượng embedding cao hơn | `qwen3-embedding:4b` hoặc HuggingFace Qwen3 Embedding 4B | Context dài và instruction-aware, nhưng dễ tranh VRAM |
| Baseline cloud/API | TH5/TH6 Gemini + Ollama embedding | Dùng để đối chiếu chất lượng/tốc độ, không tính là TurboQuant local |
| Ollama 14B native | TH9/TH10 `qwen3:14b`, `llm_max_async=1` | Baseline Ollama, không dùng TurboQuant; phải stop `llama-server` để tránh tranh GPU |

Khuyến nghị cụ thể cho 16GB:

```text
LLM model:     Qwen3-14B-Q5_0.gguf
KV:            -ctk q8_0 -ctv turbo3
Context:       -c 32768
Parallel:      --parallel 2 trước; nếu lỗi context community thì thử --parallel 1
n-predict:     --n-predict 4096; nếu muốn nhanh hơn có thể test 2048
Build async:   --llm_max_async 2 khớp --parallel 2
Timeout:       --llm_timeout 900
Chunk:         giữ 1200/100 trước; nếu prompt dài thì test 1000/100
Embedding:     bge-m3 sau khi patch, dim 1024; hoặc nomic chỉ để debug nhỏ và phải cap
```

Lệnh server nên dùng cho local TurboQuant 14B Q5:

```bash
tmux new -s srv_tq_turbo_14bq5_p2c32k
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/Qwen3-14B-Q5_0.gguf \
  --alias qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 2 \
  --n-predict 4096 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_14bq5_p2c32k_$(date +%Y%m%d_%H%M%S).log
```

Lệnh build hiện tại, khi **chưa patch embedding model/dim**, chỉ nên dùng để benchmark local tới 50 docs:

```bash
tmux new -s bld_tq_turbo_14bq5_p2c32k_001_050docs
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

mkdir -p logs/build_graph outputs/build_graph

for D in 1 5 10 50; do
  L=$(printf "%03ddocs" "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_${L} \
    --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider ollama \
    --embedding_base_url http://localhost:11434 \
    --num_docs "$D" \
    --llm_max_async 2 \
    --llm_timeout 900 \
    2>&1 | tee logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_${L}.log
done
```

Lệnh mục tiêu để chạy full 384 chỉ nên dùng **sau khi patch source** cho `--embedding_model`, `--embedding_dim` và cap/log embedding input:

```bash
ollama pull bge-m3

tmux new -s bld_tq_turbo_14bq5_bgem3_384docs
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

mkdir -p logs/build_graph outputs/build_graph

python -u build_graph.py \
  --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_bgem3_p2c32knp4096_384docs \
  --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --embedding_model bge-m3 \
  --embedding_dim 1024 \
  --embedding_max_chars 16000 \
  --num_docs 384 \
  --llm_max_async 2 \
  --llm_timeout 900 \
  2>&1 | tee logs/build_graph/cmp_tq_turbo_14bq5_bgem3_p2c32knp4096_384docs.log
```

Nếu chưa patch, không nên chạy lại full 384 với `nomic` mặc định vì rất dễ lặp lại lỗi TH7/TH11A.

### 0.5 Nếu đổi từ Ollama embedding sang HuggingFace thì có được không?

Có. Đổi embedding sang HuggingFace là hướng tốt cho bài toán này, nhưng nó là thay đổi ở **embedding layer**, không liên quan trực tiếp tới `llama-server`.

Phân tách đúng:

```text
llama-server TurboQuant:
  dùng cho LLM extraction, entity/relation extraction, community summary.

Ollama/HuggingFace embedding:
  dùng cho vector hóa chunks/entities/relations/community reports.
```

Do đó có thể chạy:

```text
LLM = Qwen3 14B Q5 qua llama-server TurboQuant
Embedding = BAAI/bge-m3 qua HuggingFace/FlagEmbedding/SentenceTransformers
```

Điểm cần set up nếu đổi sang HuggingFace:

| Hạng mục | Cần quyết định |
|---|---|
| Provider mới | Thêm `embedding_provider: huggingface` hoặc `local_hf` |
| Model | `BAAI/bge-m3`, `Qwen/Qwen3-Embedding-0.6B`, `Qwen/Qwen3-Embedding-4B`, hoặc `nomic-ai/nomic-embed-text-v1.5` |
| Dimension | `bge-m3=1024`, `qwen3-embedding:0.6b=1024`, `qwen3-embedding:4b=2560`, `nomic=768` |
| Device | CPU để tránh tranh VRAM với `llama-server`, hoặc GPU nếu stop server/đủ VRAM |
| Batch size | Giảm nếu OOM; bắt đầu `batch_size=4-12` với BGE-M3 |
| Max length | BGE-M3 dùng `max_length=8192`, nhưng vẫn nên cap/summarize input |
| Normalize | Nên normalize vector nếu dùng cosine similarity |
| Rebuild output | Đổi embedding model/dim thì phải build lại vector store; không trộn output cũ |

Với RTX 5070 Ti 16GB, phương án thực dụng nhất là:

```text
Phase 1 ổn định:
  llama-server Qwen3 14B Q5 dùng GPU
  embedding BGE-M3 qua Ollama hoặc HF CPU/GPU nhẹ
  cap/log embedding input

Phase 2 chất lượng:
  benchmark qwen3-embedding:4b sau khi đã có output BGE-M3
  không chạy song song nếu thấy VRAM sát ngưỡng

Phase 3 retrieval:
  nếu muốn tận dụng hết BGE-M3, bổ sung hybrid retrieval dense + sparse/BM25 + temporal filter
```

Nếu chỉ đổi sang HuggingFace nhưng vẫn nhét nguyên entity description 20k-30k chars vào embedding thì vẫn có rủi ro vector loãng hoặc chậm. Vì vậy fix bắt buộc của bài toán Temporal GraphRAG là:

```text
cap/log embedding input
giới hạn description sau merge
tách temporal slice vector nếu entity xuất hiện ở nhiều quý/năm
```

### 0.6 Checklist trước khi chạy full 384 docs

| Bước | Check | Lý do |
|---|---|---|
| 1 | `llama-server` Q5 đang expose đúng alias `qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096` | Tránh nhầm Q8/OOM hoặc alias không khớp |
| 2 | `--llm_max_async` bằng `--parallel` hoặc thấp hơn | Tránh queue nghẽn và context slot bị chia không đúng kỳ vọng |
| 3 | Không chạy Ollama 14B native cùng lúc | Tránh tranh GPU với `llama-server` |
| 4 | Embedding đã có `embedding_model/dim` rõ | Tránh tưởng dùng BGE-M3 nhưng source vẫn gọi `nomic` |
| 5 | Có cap/log embedding input | Tránh lỗi `input length exceeds the context length` ở 100/384 |
| 6 | Query dùng cùng embedding model/dim với build | Tránh vector query khác vector index |
| 7 | Chạy 50 -> 100 -> 384 tuần tự | 50 pass chưa chứng minh 384 pass vì entity description tăng theo scale |
| 8 | Sau run kiểm output đủ GraphML, vector store, chunks, community reports | Tránh dùng run chỉ có cache làm mốc |

## 13. Cấu hình và lệnh chạy đúng để test lại TurboQuant local LLM

### 12.1 Cấu hình khuyến nghị chính: 7B Q8, p2/c64k/np2048

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
  L=$(printf "%03ddocs" "$D")
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

Nếu 50 docs vẫn có community context errors, chuyển sang cấu hình an toàn hơn:

```text
server: --parallel 1
build:  --llm_max_async 1
```

### 12.2 Cấu hình 14B local: chỉ dùng Q5, không dùng Q8 trên GPU hiện tại

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
  L=$(printf "%03ddocs" "$D")
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

## 14. Source code chi tiết theo TH và folder

Mục này ghi trực tiếp source code hiện tại đang xử lý backend/config/embedding ra sao, để đối chiếu với từng nhóm TH. Các snippet chỉ giữ phần liên quan trực tiếp đến backend và lỗi, không paste toàn bộ file.

### 11.0 Đoạn source code bị ảnh hưởng cần đối chiếu trực tiếp

Phần này show trực tiếp code đang quyết định backend/config/embedding, để đối chiếu lỗi từng TH. Đây là các đoạn source đang chạy ở workspace, không chỉ là tên file.

#### A. TH11A/TH11B: vì sao healthcheck không đồng nghĩa với build bằng local LLM?

Áp dụng cho:

| TH | Folder | Ý nghĩa |
|---|---|---|
| TH11A | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2` | Chạy config gốc, thực tế dùng Gemini |
| TH11B | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2` | Chạy config runtime đã sửa sang OpenAI/local |

File source:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/build_graph.py
```

Đoạn code này là nguyên nhân TH11A nhìn như có TurboQuant nhưng không quyết định backend build graph. Nó chỉ kiểm tra `/props` của `llama-server` và in log:

```python
def xac_nhan_turboquant():
    # Lấy thông tin URL từ file .env
    base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:8080/v1")
    
    # Chuyển đổi sang endpoint kiểm tra thuộc tính của llama-server
    props_url = base_url.replace("/v1", "").rstrip("/") + "/props"
    
    try:
        # Gửi request kiểm tra tới server
        with urllib.request.urlopen(props_url, timeout=3) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                
                print("\n" + "═"*65)
                print("🚀 [TURBOQUANT+ VALIDATION] KẾT NỐI SERVER THÀNH CÔNG!")
                print(f" 🔹 API Endpoint  : {base_url}")
                print(f" 🔹 Nhân xử lý    : Llama-Server C++ (Tích hợp tối ưu TurboQuant+)")
                print(" 🔹 Trạng thái KV : Đang tự động nén trực tiếp trên VRAM GPU")
                print(" ═" + "═"*63 + "\n")
            else:
                print(f"⚠️ Cảnh báo: Kết nối tới server nhưng trả về mã lỗi: {response.status}")
    except Exception:
        print("\n❌ [LỖI KẾT NỐI] KHÔNG THỂ TÌM THẤY SERVER CỦA TURBOQUANT!")
        print(f"   Vui lòng chắc chắn rằng bạn đã chạy lệnh khởi động `./build/bin/llama-server` tại cổng {base_url} trước.\n")

# Gọi hàm kiểm tra ngay khi chạy file
xac_nhan_turboquant()
```

Điểm cần hiểu:

- TH11A gọi `xac_nhan_turboquant()` ngay khi chạy file, nên có log TurboQuant và GPU bị chiếm nếu server đang load model.
- Nhưng đoạn này không set `provider`, không set `model`, không truyền `base_url` vào graph build.
- Backend thật sự nằm ở config `building` và `create_temporal_graphrag_from_config(config_type="building")` phía dưới.

Đoạn build graph của TH11 vẫn đọc `config_type="building"`:

```python
# Create TemporalGraphRAG from config (simplified!)
print("="*60)
print("Loading Configuration and Initializing TemporalGraphRAG")
print("="*60)
print(f"Config file: {args.config}")
if override_config:
    print(f"Overrides: {override_config}")
print()

try:
    graph_rag = create_temporal_graphrag_from_config(
        config_path=args.config,
        config_type="building",
        override_config=override_config if override_config else None
    )
```

File config TH11A:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/configs/config.yaml
```

Đoạn config này mới là phần quyết định TH11A dùng Gemini:

```yaml
building:
  # Corpus and data paths
  corpus_path: "./ECT_data/"
  working_dir: "./output_ollama"  # If null, auto-generated from corpus, model, and datetime

  # Model configuration
  baseline: "temporalrag"  # Only temporalrag is currently supported
  provider: "gemini"  # LLM provider: openai, azure, bedrock, gemini, ollama
  model: "gemini-2.5-flash-lite"
  
  # Embedding configuration
  embedding_provider: "ollama"  # Embedding provider: openai, azure, bedrock, ollama (defaults to provider if not specified)

  # Chunking parameters
  chunk_size: 1200  # Max token size per chunk
  chunk_overlap: 100  # Overlap token size between consecutive chunks

  # Temporal processing
  enable_seasonal_matching: false  # Enable seasonal matching in temporal normalization

  # Community summary generation
  enable_community_summary: true  # Enable/disable community summary generation

llm:
  provider: "openai"              # Thiết lập provider là openai để hệ thống gọi hàm openai_complete_if_cache
  model: "qwen3-14b-instruct"      # Bạn có thể điền tên bất kỳ, server cục bộ sẽ tự nhận diện mô hình đang load sẵn
  max_tokens: 4096                # Giới hạn token đầu ra cho mỗi câu trả lời
  temperature: 0.0                # Đặt bằng 0 để kết quả trích xuất thực thể đồ thị có tính chính xác cao nhất
```

Điểm cần hiểu:

- `building.provider: gemini` và `building.model: gemini-2.5-flash-lite` là backend build graph của TH11A.
- Top-level `llm.provider: openai` không được dùng trong build graph, vì code gọi `config_type="building"`.
- TH11B khác TH11A vì TH11B tạo file config runtime rồi thay `building.provider` sang `openai` và `building.model` sang `qwen3-14b-instruct`.

File source đọc config:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/src/build.py
```

Đoạn này lấy provider/model từ config đã load:

```python
# Load configuration
config_loader = ConfigLoader(config_path=config_path)
config = config_loader.get_config(config_type, override_args=override_config)

# Get provider and model
provider = config.get('provider', 'openai')
model = config.get('model', 'gpt-4o-mini')
```

File source loader:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/tgrag/src/config/config_loader.py
```

Đoạn này chứng minh chỉ lấy block theo `config_type`:

```python
def get_config(self, config_type: Literal["building", "querying"], override_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get configuration based on task type as a dictionary."""
    # Get config by type
    config = self.config.get(config_type, {}).copy()

    # Override with provided arguments
    if override_args:
        config.update({k: v for k, v in override_args.items() if v is not None})
    
    if not config:
        raise ValueError(f"No configuration found for type: {config_type}")
```

Kết luận code cho TH11A/TH11B:

- TH11A: `config_type="building"` + `building.provider="gemini"` nên dùng Gemini.
- TH11B: file runtime sửa chính block `building` sang OpenAI/local nên mới dùng `llama-server`.
- GPU/VRAM trong TH11A chỉ chứng minh server đang load model, không chứng minh build graph dùng model đó.

#### B. TH1/TH3/TH5/TH7/TH9: source Turboquant hiện tại xử lý backend ra sao?

Áp dụng cho folder:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
```

Áp dụng cho TH:

| TH | CLI | Backend do source set |
|---|---|---|
| TH1 | `--local_llm_backend turboquant` | `provider="openai"`, `base_url=http://localhost:8080/v1` |
| TH3 | `--local_llm_backend ollama` | `provider="ollama"`, `base_url=http://localhost:11434` |
| TH5 | `--provider gemini` | `provider="gemini"` |
| TH7 | `--local_llm_backend turboquant` | giống TH1, alias Qwen3 14B Q5 |
| TH9 | `--local_llm_backend ollama` | giống TH3, model `qwen3:14b` |

File source:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py
```

Đoạn source quyết định backend:

```python
def apply_runtime_overrides(args, override_config: Dict) -> Dict:
    """Apply CLI runtime overrides without mutating config files."""
    if args.local_llm_backend == "turboquant":
        provider = "openai"
        model = args.model or "qwen2.5-7b-instruct-q8-turbo3"
        llm_base_url = args.base_url or "http://localhost:8080/v1"
        embedding_provider = args.embedding_provider or "ollama"
        embedding_base_url = args.embedding_base_url or "http://localhost:11434"
        llm_max_async = args.llm_max_async or 1
        llm_timeout = args.llm_timeout or 600.0
        api_key = os.getenv("OPENAI_API_KEY") or "sk-local"
        wire_protocol = "openai-compatible-local"
    elif args.local_llm_backend == "ollama":
        provider = "ollama"
        model = args.model or "qwen3:14b"
        llm_base_url = args.base_url or "http://localhost:11434"
        embedding_provider = args.embedding_provider or "ollama"
        embedding_base_url = args.embedding_base_url or "http://localhost:11434"
        llm_max_async = args.llm_max_async
        llm_timeout = args.llm_timeout
        api_key = None
        wire_protocol = "ollama-native"
    else:
        provider = args.provider
        model = args.model
        llm_base_url = args.base_url
        embedding_provider = args.embedding_provider
        embedding_base_url = args.embedding_base_url
        llm_max_async = args.llm_max_async
        llm_timeout = args.llm_timeout
        api_key = None
        wire_protocol = provider or "config"
        if provider == "openai" and _is_local_base_url(llm_base_url):
            api_key = os.getenv("OPENAI_API_KEY") or "sk-local"
            wire_protocol = "openai-compatible-local"
        elif provider == "ollama":
            wire_protocol = "ollama-native"

    if provider:
        override_config["provider"] = provider
    if model:
        override_config["model"] = model
    if embedding_provider:
        override_config["embedding_provider"] = embedding_provider
    if llm_max_async:
        override_config["best_model_max_async"] = llm_max_async
        override_config["cheap_model_max_async"] = llm_max_async
    if llm_timeout:
        override_config["llm_timeout"] = llm_timeout
```

Đoạn source truyền runtime vào graph:

```python
runtime_config = apply_runtime_overrides(args, override_config)

if runtime_config.get("local_llm_backend") == "turboquant":
    try:
        xac_nhan_turboquant(runtime_config["llm_base_url"], strict=True)
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

try:
    graph_rag = create_temporal_graphrag_from_config(
        config_path=args.config,
        config_type="building",
        override_config=override_config if override_config else None,
        api_key=runtime_config.get("api_key") if runtime_config else None,
        base_url=runtime_config.get("llm_base_url") if runtime_config else None,
        embedding_base_url=runtime_config.get("embedding_base_url") if runtime_config else None,
    )
```

Cách đối chiếu:

- Nếu TH1/TH7 chạy đúng, build log phải có `local_llm_backend=turboquant provider=openai`.
- Nếu TH3/TH9 chạy đúng, build log phải có `local_llm_backend=ollama provider=ollama`.
- Nếu TH5 chạy đúng, cache phải ghi `gemini-2.5-flash-lite`.

#### C. TH2/TH4/TH6/TH8/TH10: source Original worktree xử lý backend ra sao?

Áp dụng cho folder:

```text
/home/guest/Projects/Research/Temporal-GraphRAG
```

Áp dụng cho TH:

| TH | CLI | Backend do source set |
|---|---|---|
| TH2 | `--local_llm_backend turboquant` | `provider="openai"`, gọi `llama-server` |
| TH4 | `--local_llm_backend normal` | `provider="ollama"`, gọi Ollama native |
| TH6 | `--provider gemini` | `provider="gemini"` |
| TH8 | `--local_llm_backend turboquant` | `provider="openai"`, gọi Qwen3 14B Q5 server |
| TH10 | `--local_llm_backend normal` | `provider="ollama"`, gọi `qwen3:14b` |

File source:

```text
/home/guest/Projects/Research/Temporal-GraphRAG/build_graph.py
```

Đoạn source quyết định backend local:

```python
def apply_local_llm_runtime(args, override_config: Dict) -> Dict:
    if not args.local_llm_backend:
        provider = args.provider
        model = args.model or args.llm_model
        llm_base_url = args.base_url or args.llm_base_url
        embedding_provider = args.embedding_provider
        embedding_base_url = args.embedding_base_url
        embedding_model = args.embedding_model
        embedding_dim = args.embedding_dim

        if provider:
            override_config["provider"] = provider
        if model:
            override_config["model"] = model
        if embedding_provider:
            override_config["embedding_provider"] = embedding_provider
        if embedding_model:
            override_config["embedding_model"] = embedding_model
        if embedding_dim:
            override_config["embedding_dim"] = embedding_dim
        if args.llm_max_async:
            override_config["best_model_max_async"] = args.llm_max_async
            override_config["cheap_model_max_async"] = args.llm_max_async
        if args.llm_timeout:
            override_config["llm_timeout"] = args.llm_timeout

        wire_protocol = provider or "config"
        if provider == "ollama":
            wire_protocol = "ollama-native"
        elif provider == "openai" and llm_base_url:
            is_local = "localhost" in llm_base_url or "127.0.0.1" in llm_base_url
            wire_protocol = "openai-compatible-local" if is_local else "openai-compatible"

        api_key = None
        if provider == "openai" and llm_base_url:
            is_local = "localhost" in llm_base_url or "127.0.0.1" in llm_base_url
            api_key = (os.getenv("OPENAI_API_KEY") or "sk-local") if is_local else os.getenv("OPENAI_API_KEY")

        return {
            "local_llm_backend": "provider_override",
            "provider": provider or "config",
            "model": model or "config",
            "llm_base_url": llm_base_url,
            "embedding_provider": embedding_provider or "config",
            "embedding_model": embedding_model or "config",
            "embedding_dim": embedding_dim,
            "embedding_base_url": embedding_base_url,
            "wire_protocol": wire_protocol,
            "api_key": api_key,
        }

    if args.local_llm_backend == "normal":
        provider = "ollama"
        model = args.llm_model or args.model or "qwen3:14b"
        llm_base_url = args.llm_base_url or args.base_url or "http://localhost:11434"
        wire_protocol = "ollama-native"
        api_key = None
    else:
        provider = "openai"
        model = args.llm_model or args.model or "qwen3-14b-instruct"
        llm_base_url = args.llm_base_url or args.base_url or "http://localhost:8080/v1"
        wire_protocol = "openai-compatible-local"
        api_key = os.getenv("OPENAI_API_KEY") or "sk-local"

    embedding_provider = args.embedding_provider or "ollama"
    embedding_model = args.embedding_model or "nomic-embed-text"
    embedding_dim = args.embedding_dim or 768
    embedding_base_url = args.embedding_base_url or "http://localhost:11434"
```

Đoạn source healthcheck và truyền runtime:

```python
runtime_config = apply_local_llm_runtime(args, override_config)

if (
    runtime_config.get("local_llm_backend") == "turboquant"
    and not args.skip_turboquant_healthcheck
):
    try:
        xac_nhan_turboquant(
            runtime_config["llm_base_url"],
            strict=args.turboquant_healthcheck,
        )
    except RuntimeError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)

try:
    graph_rag = create_temporal_graphrag_from_config(
        config_path=args.config,
        config_type="building",
        override_config=override_config if override_config else None,
        api_key=runtime_config.get("api_key") if runtime_config else None,
        base_url=runtime_config.get("llm_base_url") if runtime_config else None,
        embedding_base_url=runtime_config.get("embedding_base_url") if runtime_config else None,
    )
```

Cách đối chiếu:

- TH2/TH8: `local_llm_backend=turboquant` rơi vào nhánh `else`, provider thành `openai`, base URL thành `http://localhost:8080/v1`.
- TH4/TH10: `local_llm_backend=normal` rơi vào nhánh Ollama native, provider thành `ollama`, base URL thành `http://localhost:11434`.
- TH6: không dùng `local_llm_backend`, truyền `--provider gemini`, nên đi nhánh provider override.

#### D. TH11A 384: code gây lỗi embedding content quá dài

Áp dụng cho lỗi:

| TH | Folder output lỗi | Lỗi |
|---|---|---|
| TH11A 384 | `/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_384docs_20260522_204618` | Ollama embedding input vượt context |

Đường source hiện tại giải thích lỗi:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/storage/vector_nanovectordb.py
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/embedding.py
```

`vector_nanovectordb.py` lấy nguyên `content` để embed, chưa truncate:

```python
list_data = [
    {
        "__id__": k,
        **{k1: v1 for k1, v1 in v.items() if k1 in self.meta_fields},
    }
    for k, v in data.items()
]

contents = [v["content"] for v in data.values()]
batches = [
    contents[i : i + self._max_batch_size]
    for i in range(0, len(contents), self._max_batch_size)
]
prep_done = time.perf_counter()
print(
    f"[build-detail] vector payload prep ({self.namespace}): "
    f"{prep_done - total_start:.2f}s batches={len(batches)} batch_size={self._max_batch_size}",
    flush=True,
)

logger.info(f"Generating embeddings for {len(batches)} batches...")
embeddings_list = await asyncio.gather(
    *[self.embedding_func(batch) for batch in batches]
)
```

`embedding.py` gửi nguyên text sang Ollama `/api/embeddings`:

```python
async def ollama_embedding(
    texts: List[str],
    model: str = "nomic-embed-text",
    base_url: Optional[str] = None
) -> np.ndarray:
    """Generate embeddings using Ollama."""
    import aiohttp
    
    client_manager = get_client_manager()
    ollama_url = client_manager.get_ollama_base_url(base_url)
    
    embeddings = []
    async with aiohttp.ClientSession() as session:
        for text in texts:
            payload = {
                "model": model,
                "prompt": text,
            }
            
            async with session.post(
                f"{ollama_url}/api/embeddings",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama embedding API error {response.status}: {error_text}")
```

Cách đối chiếu với lỗi TH11A 384:

- GraphML TH11A 384 đã có node description rất dài, ví dụ node `2023` khoảng 29523 ký tự.
- `vector_nanovectordb.py` lấy nguyên description đó đưa vào `contents`.
- `embedding.py` gửi nguyên text đó sang Ollama.
- Ollama trả `input length exceeds the context length`.
- Vì lỗi xảy ra ở embedding, không phải ở `llama-server`, nên đây không phải lỗi KV TurboQuant.

Đường sửa source đúng vị trí:

```python
# Trước khi tạo batches trong vector_nanovectordb.py:
# 1. đo len/token_count của từng content
# 2. nếu vượt ngưỡng embedding thì truncate
# 3. log namespace, id, old_len, new_len
contents = [truncate_for_embedding(v["content"]) for v in data.values()]
```

Hoặc sửa ở `ollama_embedding()`:

```python
for text in texts:
    text = truncate_for_embedding(text)
    payload = {"model": model, "prompt": text}
```

Tuy nhiên sửa ở vector layer tốt hơn vì có thể log được `namespace` và `id` của entity/relation gây lỗi.

### 11.1 TH1, TH3, TH5, TH7, TH9: repo Turboquant hiện tại

Folder:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
```

Các TH dùng source này:

| TH | Ý nghĩa CLI | Source xử lý |
|---|---|---|
| TH1 | `--local_llm_backend turboquant` 7B | Ép provider thành `openai`, gọi `llama-server` qua `/v1` |
| TH3 | `--local_llm_backend ollama` 7B | Ép provider thành `ollama`, gọi Ollama native |
| TH5 | `--provider gemini` | Dùng provider Gemini từ CLI override |
| TH7 | `--local_llm_backend turboquant` 14B Q5 | Giống TH1 nhưng model alias Q5 14B |
| TH9 | `--local_llm_backend ollama` 14B | Giống TH3 nhưng model `qwen3:14b` |

File source:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/build_graph.py
```

Source nhận CLI backend/model/base URL:

```python
447     parser.add_argument(
448         '--local_llm_backend',
449         choices=['turboquant', 'ollama'],
450         default=None,
451         help='Local LLM backend override: turboquant=local llama-server OpenAI-compatible API, ollama=Ollama native API'
452     )
459     parser.add_argument(
460         '--model',
461         type=str,
462         default=None,
463         help='Override LLM model or local llama-server alias'
464     )
465     parser.add_argument(
466         '--base_url',
467         type=str,
468         default=None,
469         help='Override LLM base URL, e.g. http://localhost:8080/v1 for llama-server'
470     )
483     parser.add_argument(
484         '--llm_max_async',
485         type=int,
486         default=None,
487         help='Override max concurrent LLM calls. Defaults to 1 for --local_llm_backend turboquant'
488     )
```

Source ép backend theo `--local_llm_backend`:

```python
126 def apply_runtime_overrides(args, override_config: Dict) -> Dict:
127     """Apply CLI runtime overrides without mutating config files."""
128     if args.local_llm_backend == "turboquant":
129         provider = "openai"
130         model = args.model or "qwen2.5-7b-instruct-q8-turbo3"
131         llm_base_url = args.base_url or "http://localhost:8080/v1"
132         embedding_provider = args.embedding_provider or "ollama"
133         embedding_base_url = args.embedding_base_url or "http://localhost:11434"
134         llm_max_async = args.llm_max_async or 1
135         llm_timeout = args.llm_timeout or 600.0
136         api_key = os.getenv("OPENAI_API_KEY") or "sk-local"
137         wire_protocol = "openai-compatible-local"
138     elif args.local_llm_backend == "ollama":
139         provider = "ollama"
140         model = args.model or "qwen3:14b"
141         llm_base_url = args.base_url or "http://localhost:11434"
142         embedding_provider = args.embedding_provider or "ollama"
143         embedding_base_url = args.embedding_base_url or "http://localhost:11434"
144         llm_max_async = args.llm_max_async
145         llm_timeout = args.llm_timeout
146         api_key = None
147         wire_protocol = "ollama-native"
```

Source đưa provider/model/concurrency vào config build:

```python
164     if provider:
165         override_config["provider"] = provider
166     if model:
167         override_config["model"] = model
168     if embedding_provider:
169         override_config["embedding_provider"] = embedding_provider
170     if llm_max_async:
171         override_config["best_model_max_async"] = llm_max_async
172         override_config["cheap_model_max_async"] = llm_max_async
173     if llm_timeout:
174         override_config["llm_timeout"] = llm_timeout
```

Source chỉ healthcheck khi TH thật sự là TurboQuant, rồi truyền đúng `base_url` và `embedding_base_url`:

```python
520     if runtime_config.get("local_llm_backend") == "turboquant":
521         try:
522             xac_nhan_turboquant(runtime_config["llm_base_url"], strict=True)
523         except RuntimeError as e:
524             print(f"❌ Error: {e}")
525             sys.exit(1)
527     try:
528         graph_rag = create_temporal_graphrag_from_config(
529             config_path=args.config,
530             config_type="building",
531             override_config=override_config if override_config else None,
532             api_key=runtime_config.get("api_key") if runtime_config else None,
533             base_url=runtime_config.get("llm_base_url") if runtime_config else None,
534             embedding_base_url=runtime_config.get("embedding_base_url") if runtime_config else None,
535         )
```

Cách hiểu theo TH:

- TH1/TH7 chỉ đúng TurboQuant nếu build log có `local_llm_backend=turboquant provider=openai` và server log có `POST /v1/chat/completions`.
- TH3/TH9 là Ollama native vì source rẽ sang nhánh `provider = "ollama"`, không đi qua `llama-server`.
- TH5 là Gemini vì CLI truyền `--provider gemini`; không dùng nhánh local backend.

### 11.2 TH2, TH4, TH6, TH8, TH10: repo Original worktree hiện tại

Folder:

```text
/home/guest/Projects/Research/Temporal-GraphRAG
```

Các TH dùng source này:

| TH | Ý nghĩa CLI | Source xử lý |
|---|---|---|
| TH2 | `--local_llm_backend turboquant` 7B | Ép provider thành `openai`, gọi `llama-server` |
| TH4 | `--local_llm_backend normal` 7B | Ép provider thành `ollama`, gọi Ollama native |
| TH6 | `--provider gemini` | Dùng Gemini |
| TH8 | `--local_llm_backend turboquant` 14B Q5 | Gọi `llama-server` Q5 alias mới |
| TH10 | `--local_llm_backend normal` 14B | Gọi Ollama native `qwen3:14b` |

File source:

```text
/home/guest/Projects/Research/Temporal-GraphRAG/build_graph.py
```

Source nhận CLI cho Original worktree:

```python
506     parser.add_argument(
507         '--local_llm_backend',
508         choices=['normal', 'turboquant'],
509         default=None,
510         help='Local Qwen backend override: normal=Ollama native API, turboquant=local llama-server OpenAI-compatible API'
511     )
512     parser.add_argument(
513         '--llm_model',
514         type=str,
515         default=None,
516         help='Local LLM model name/alias. Defaults: qwen3:14b for normal, qwen3-14b-instruct for turboquant'
517     )
518     parser.add_argument(
519         '--llm_base_url',
520         type=str,
521         default=None,
522         help='Local LLM base URL. Defaults: http://localhost:11434 for normal, http://localhost:8080/v1 for turboquant'
523     )
542     parser.add_argument(
543         '--llm_max_async',
544         type=int,
545         default=None,
546         help='Override max concurrent LLM requests. Defaults to 1 for turboquant; config/default for normal.'
547     )
554     parser.add_argument(
555         '--turboquant_healthcheck',
556         action='store_true',
557         help='When using --local_llm_backend turboquant, fail if llama-server /props is unavailable'
558     )
```

Source runtime của Original worktree:

```python
152     if args.local_llm_backend == "normal":
153         provider = "ollama"
154         model = args.llm_model or args.model or "qwen3:14b"
155         llm_base_url = args.llm_base_url or args.base_url or "http://localhost:11434"
156         wire_protocol = "ollama-native"
157         api_key = None
158     else:
159         provider = "openai"
160         model = args.llm_model or args.model or "qwen3-14b-instruct"
161         llm_base_url = args.llm_base_url or args.base_url or "http://localhost:8080/v1"
162         wire_protocol = "openai-compatible-local"
163         api_key = os.getenv("OPENAI_API_KEY") or "sk-local"
165     embedding_provider = args.embedding_provider or "ollama"
166     embedding_model = args.embedding_model or "nomic-embed-text"
167     embedding_dim = args.embedding_dim or 768
168     embedding_base_url = args.embedding_base_url or "http://localhost:11434"
```

Source healthcheck và tạo graph:

```python
589     if (
590         runtime_config.get("local_llm_backend") == "turboquant"
591         and not args.skip_turboquant_healthcheck
592     ):
593         try:
594             xac_nhan_turboquant(
595                 runtime_config["llm_base_url"],
596                 strict=args.turboquant_healthcheck,
597             )
602     try:
603         graph_rag = create_temporal_graphrag_from_config(
604             config_path=args.config,
605             config_type="building",
606             override_config=override_config if override_config else None,
607             api_key=runtime_config.get("api_key") if runtime_config else None,
608             base_url=runtime_config.get("llm_base_url") if runtime_config else None,
609             embedding_base_url=runtime_config.get("embedding_base_url") if runtime_config else None,
610         )
```

Cách hiểu theo TH:

- TH2/TH8 dùng `--local_llm_backend turboquant`, nên source dùng `provider=openai` và `llm_base_url=http://localhost:8080/v1`.
- TH4/TH10 dùng `--local_llm_backend normal`, nên source dùng `provider=ollama` và `llm_base_url=http://localhost:11434`.
- TH6 dùng `--provider gemini`, nên đi theo provider override, không local LLM.

### 11.3 TH11A/TH11B: worktree `c1f1ea2`

Folder:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2
```

Các TH dùng source này:

| TH | Cách chạy | Source xử lý |
|---|---|---|
| TH11A | Không truyền `--config`, dùng config gốc | Build dùng block `building` trong config, tức Gemini |
| TH11B | Truyền config runtime đã sửa `provider=openai` | Build dùng local `llama-server` alias `qwen3-14b-instruct` |

Healthcheck top-level gây nhầm backend trong TH11A:

```python
42 def xac_nhan_turboquant():
43     # Lấy thông tin URL từ file .env
44     base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:8080/v1")
46     # Chuyển đổi sang endpoint kiểm tra thuộc tính của llama-server
47     props_url = base_url.replace("/v1", "").rstrip("/") + "/props"
49     try:
50         # Gửi request kiểm tra tới server
51         with urllib.request.urlopen(props_url, timeout=3) as response:
52             if response.status == 200:
55                 print("\n" + "═"*65)
56                 print("🚀 [TURBOQUANT+ VALIDATION] KẾT NỐI SERVER THÀNH CÔNG!")
57                 print(f" 🔹 API Endpoint  : {base_url}")
58                 print(f" 🔹 Nhân xử lý    : Llama-Server C++ (Tích hợp tối ưu TurboQuant+)")
59                 print(" 🔹 Trạng thái KV : Đang tự động nén trực tiếp trên VRAM GPU")
67 # Gọi hàm kiểm tra ngay khi chạy file
68 xac_nhan_turboquant()
```

Config gốc TH11A vẫn là Gemini ở block `building`:

```yaml
7  building:
14   provider: "gemini"  # LLM provider: openai, azure, bedrock, gemini, ollama
15   model: "gemini-2.5-flash-lite"
18   embedding_provider: "ollama"
21   chunk_size: 1200
22   chunk_overlap: 100
28   enable_community_summary: true
84 llm:
85   provider: "openai"
86   model: "qwen3-14b-instruct"
```

Điểm gây nhầm: top-level `llm` có OpenAI/Qwen, nhưng build graph không dùng block này. Build graph gọi config type `building`:

```python
381         graph_rag = create_temporal_graphrag_from_config(
382             config_path=args.config,
383             config_type="building",
384             override_config=override_config if override_config else None
385         )
```

`create_temporal_graphrag_from_config` lấy provider/model từ config đã load theo `config_type`:

```python
157     # Load configuration
158     config_loader = ConfigLoader(config_path=config_path)
159     config = config_loader.get_config(config_type, override_args=override_config)
161     # Get provider and model
162     provider = config.get('provider', 'openai')
163     model = config.get('model', 'gpt-4o-mini')
```

`ConfigLoader` chỉ lấy block đúng theo `config_type`:

```python
48 def get_config(self, config_type: Literal["building", "querying"], override_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
49     """Get configuration based on task type as a dictionary."""
50     # Get config by type
51     config = self.config.get(config_type, {}).copy()
```

Kết luận source cho TH11A:

- Healthcheck gọi `/props` nên log in ra TurboQuant.
- Server Qwen3 Q5 được load nên GPU/VRAM bị chiếm.
- Nhưng provider/model build graph lấy từ `building`, nên TH11A vẫn là Gemini.
- Bằng chứng cuối cùng nằm trong `kv_store_llm_response_cache.json`: model là `gemini-2.5-flash-lite`.

Kết luận source cho TH11B:

- TH11B tạo file runtime config và thay `provider: "gemini"` thành `provider: "openai"`.
- Vì `create_temporal_graphrag_from_config(..., config_type="building")` đọc block `building`, lần này build thật sự dùng OpenAI-compatible local server.
- Bằng chứng cache TH11B ghi `qwen3-14b-instruct`.

### 11.4 Source lỗi TH11A 384: embedding content quá dài

Folder source hiện tại dùng để giải thích lỗi embedding:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
```

File vector store lấy toàn bộ `content` đem embed, hiện chưa có bước truncate:

```python
99  list_data = [
100     {
101         "__id__": k,
102         **{k1: v1 for k1, v1 in v.items() if k1 in self.meta_fields},
103     }
104     for k, v in data.items()
105 ]
107 contents = [v["content"] for v in data.values()]
108 batches = [
109     contents[i : i + self._max_batch_size]
110     for i in range(0, len(contents), self._max_batch_size)
111 ]
119 logger.info(f"Generating embeddings for {len(batches)} batches...")
120 embeddings_list = await asyncio.gather(
121     *[self.embedding_func(batch) for batch in batches]
122 )
```

File Ollama embedding gửi nguyên text sang endpoint legacy `/api/embeddings`:

```python
118 async def ollama_embedding(
119     texts: List[str],
120     model: str = "nomic-embed-text",
121     base_url: Optional[str] = None
122 ) -> np.ndarray:
138     embeddings = []
139     async with aiohttp.ClientSession() as session:
140         for text in texts:
141             payload = {
142                 "model": model,
143                 "prompt": text,
144             }
146             async with session.post(
147                 f"{ollama_url}/api/embeddings",
148                 json=payload
149             ) as response:
150                 if response.status != 200:
151                     error_text = await response.text()
152                     raise Exception(f"Ollama embedding API error {response.status}: {error_text}")
```

Cách hiểu lỗi TH11A 384:

- Output GraphML TH11A 384 có entity description rất dài, ví dụ node `2023` khoảng 29523 ký tự.
- Source lấy nguyên description này đưa vào `content` để embed.
- Ollama `nomic-embed-text` không nhận input dài như vậy nên trả `input length exceeds the context length`.
- Đây là lỗi embedding input, không phải lỗi KV của `llama-server`.

Đường sửa đúng:

- Thêm truncate/cap ở `vector_nanovectordb.py` trước khi gọi `embedding_func`.
- Hoặc cap description ngay sau merge entity/relation trong graph build.
- Khi fail embedding, log ra namespace, id, độ dài content và top-N content dài nhất.

## 15. Mapping log và output đúng theo TH

### 6.1 TH1: TQ + Turbo 7B

Build logs:

```text
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_001docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_010docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_050docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_100docs.log
```

Server log:

```text
Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_7b_p4c64k_20260522_105607.log
```

Outputs:

```text
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_001docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_010docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_050docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_100docs
```

### 6.2 TH2: Original + Turbo 7B

Build logs:

```text
Temporal-GraphRAG/logs/build_graph/cmp_orig_turbo_7b_p4c64knp4096_001docs.log
Temporal-GraphRAG/logs/build_graph/cmp_orig_turbo_7b_p4c64knp4096_010docs.log
Temporal-GraphRAG/logs/build_graph/cmp_orig_turbo_7b_p4c64knp4096_050docs.log
```

Server log:

```text
Temporal-GraphRAG/logs/llama_server/cmp_orig_turbo_7b_p4c64k_20260522_121901.log
```

Outputs:

```text
Temporal-GraphRAG/outputs/build_graph/cmp_orig_turbo_7b_p4c64knp4096_001docs
Temporal-GraphRAG/outputs/build_graph/cmp_orig_turbo_7b_p4c64knp4096_010docs
Temporal-GraphRAG/outputs/build_graph/cmp_orig_turbo_7b_p4c64knp4096_050docs
```

Không thấy 100 docs đúng tên TH2.

### 6.3 TH3: TQ + Ollama 7B

```text
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_ollama_7b_api_001docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_ollama_7b_api_010docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_ollama_7b_api_050docs.log
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_ollama_7b_api_001docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_ollama_7b_api_010docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_ollama_7b_api_050docs
```

### 6.4 TH4: Original + Ollama 7B

```text
Temporal-GraphRAG/logs/build_graph/cmp_orig_ollama_7b_api_001docs.log
Temporal-GraphRAG/logs/build_graph/cmp_orig_ollama_7b_api_010docs.log
Temporal-GraphRAG/logs/build_graph/cmp_orig_ollama_7b_api_050docs.log
Temporal-GraphRAG/outputs/build_graph/cmp_orig_ollama_7b_api_001docs
Temporal-GraphRAG/outputs/build_graph/cmp_orig_ollama_7b_api_010docs
Temporal-GraphRAG/outputs/build_graph/cmp_orig_ollama_7b_api_050docs
```

### 6.5 TH5: TQ + Gemini

```text
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_gemini_api_001docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_gemini_api_010docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_gemini_api_050docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_gemini_api_100docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_gemini_api_384docs.log
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_gemini_api_001docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_gemini_api_010docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_gemini_api_050docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_gemini_api_100docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_gemini_api_384docs
```

### 6.6 TH6: Original + Gemini

```text
Temporal-GraphRAG/logs/build_graph/cmp_orig_gemini_api_001docs.log
Temporal-GraphRAG/logs/build_graph/cmp_orig_gemini_api_010docs.log
Temporal-GraphRAG/logs/build_graph/cmp_orig_gemini_api_050docs.log
Temporal-GraphRAG/logs/build_graph/cmp_orig_gemini_api_100docs.log
Temporal-GraphRAG/logs/build_graph/cmp_orig_gemini_api_384docs.log
Temporal-GraphRAG/outputs/build_graph/cmp_orig_gemini_api_001docs
Temporal-GraphRAG/outputs/build_graph/cmp_orig_gemini_api_010docs
Temporal-GraphRAG/outputs/build_graph/cmp_orig_gemini_api_050docs
Temporal-GraphRAG/outputs/build_graph/cmp_orig_gemini_api_100docs
Temporal-GraphRAG/outputs/build_graph/cmp_orig_gemini_api_384docs
```

TH6 384 đã có log/output mới xác nhận build hoàn tất:

```text
Temporal-GraphRAG/logs/build_graph/cmp_orig_gemini_api_384docs.log
Temporal-GraphRAG/outputs/build_graph/cmp_orig_gemini_api_384docs
```

Kết quả chính:

- `Graph building completed successfully`.
- `Total elapsed: 11673.70s`.
- `new chunks: 1462`.
- `Processed 1462(100%) chunks, 41895 entities(duplicated), 20596 relations(duplicated)`.
- Output có đủ `kv_store_full_docs.json`, `kv_store_text_chunks.json`, `kv_store_community_reports.json`, `vdb_entities.json`, `vdb_entities_new.json`, `vdb_relations.json`, `graph_chunk_entity_relation.graphml`.
- Có 2 dòng `ERROR - Failed to generate community report after 3 attempts`, nhưng run vẫn persist đủ output và kết thúc success.

### 6.7 TH7-TH10

Các log/output cũ theo pattern Q8 14B chưa có dữ liệu hoàn chỉnh, và cấu hình Q8 14B đã có bằng chứng OOM VRAM ở TH11. Vì vậy phần lệnh TH7-TH10 phía dưới đã được cập nhật lại theo hướng:

- TH7/TH8 dùng Qwen3 14B **Q5**, không dùng Q8.
- TH7 server hiện theo ghi chú đang chạy đúng alias `qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096`, model `Qwen3-14B-Q5_0.gguf`, `-c 32768`, `--parallel 2`, `--n-predict 4096`, server log có request thành công và `truncated = 0`.
- TH8 có thể dùng chung server Q5 với TH7 nếu alias đúng; nếu chưa có server thì start theo block TH8 mới.
- TH9/TH10 dùng Ollama `qwen3:14b`, không dùng llama-server. Nên stop llama-server trước để tránh tranh GPU và làm sai số benchmark.

Pattern output/log mới cần tìm:

```text
cmp_tq_turbo_14bq5_p2c32knp4096_*
cmp_orig_turbo_14bq5_p2c32knp4096_*
cmp_tq_ollama_14b_api_*
cmp_orig_ollama_14b_api_*
```

Kết quả TH7 Q5 đã có trong folder Turboquant:

```text
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_001docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_005docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_010docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_050docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_100docs.log
Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_384docs.log
```

```text
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_001docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_005docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_010docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_050docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_100docs
Temporal-GraphRAG-Turboquant/outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_384docs
```

TH7 server log chính:

```text
Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_14bq5_p2c32k_20260523_004207.log
```

Server log xác nhận Q5 local chạy đúng:

- Model file: `Qwen3-14B-Q5_0.gguf`.
- `llama_context: n_ctx = 32768`.
- `llama_context: n_ctx_seq = 16384`.
- `llama_kv_cache`: K `q8_0`, V `turbo3`, KV buffer khoảng `1860 MiB`.
- `n_slots = 2`, mỗi slot `n_ctx = 16384`.
- Có nhiều request `POST /v1/chat/completions 200`.
- Các request cuối có `truncated = 0`.
- Decode thường khoảng `52-55 tokens/s`; prompt eval khoảng `2900-3400 tokens/s`.

### 6.8 TH11A

Build logs:

```text
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/build_graph/th11a_c1_original_001docs_20260522_204618.log
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/build_graph/th11a_c1_original_005docs_20260522_204618.log
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/build_graph/th11a_c1_original_010docs_20260522_204618.log
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/build_graph/th11a_c1_original_050docs_20260522_204618.log
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/build_graph/th11a_c1_original_100docs_20260522_204618.log
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/build_graph/th11a_c1_original_384docs_20260522_204618.log
```

Outputs:

```text
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_001docs_20260522_204618
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_005docs_20260522_204618
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_010docs_20260522_204618
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_050docs_20260522_204618
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_100docs_20260522_204618
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11a_c1_original_384docs_20260522_204618
```

Server log liên quan:

```text
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/llama_server/srv_th11_c1_14bq5_top_level_20260522_204437.log
```

### 6.9 TH11B

```text
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/build_graph/th11b_c1_openai14b_001docs_20260522_211255.log
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/build_graph/th11b_c1_openai14b_005docs_20260522_211255.log
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/configs_runtime/th11b_c1_openai14b_20260522_211255.yaml
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11b_c1_openai14b_001docs_20260522_211255
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/outputs/build_graph/th11b_c1_openai14b_005docs_20260522_211255
```

Server logs:

```text
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/llama_server/srv_th11_c1_14bq5_top_level_20260522_204437.log
Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/llama_server/srv_th11_c1_14b_top_level_20260522_204437.log
```

File `srv_th11_c1_14b_top_level_20260522_204437.log` là Q8 fail OOM. File Q5 là server chạy được.

## 16. Full lệnh kịch bản gốc TH1-TH10 và TH11

Phần này giữ lại lệnh gốc để đối chiếu. Các lệnh này phản ánh kịch bản đã định nghĩa, không phải tất cả đều là cấu hình khuyến nghị hiện tại.

### TH1 Server: TQ + Turbo 7B

```bash
tmux new -s srv_tq_turbo_7b_p4c64k
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant
mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server
./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096 \
  --host 127.0.0.1 --port 8080 \
  -ctk q8_0 -ctv turbo3 -fa on -ngl 99 \
  -c 65536 --parallel 4 --n-predict 4096 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_7b_p4c64k_$(date +%Y%m%d_%H%M%S).log
```

### TH1 Build

```bash
tmux new -s bld_tq_turbo_7b_p4c64k
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
mkdir -p logs/build_graph outputs/build_graph
for D in 1 10 50 100; do
  L=$(printf "%03ddocs" "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_${L} \
    --model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider ollama \
    --embedding_base_url http://localhost:11434 \
    --num_docs "$D" \
    --llm_max_async 4 \
    --llm_timeout 600 \
    2>&1 | tee logs/build_graph/cmp_tq_turbo_7b_p4c64knp4096_${L}.log
done
```

### TH2 Server: Original + Turbo 7B

```bash
tmux new -s srv_orig_turbo_7b_p4c64k
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant
mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG/logs/llama_server
./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096 \
  --host 127.0.0.1 --port 8080 \
  -ctk q8_0 -ctv turbo3 -fa on -ngl 99 \
  -c 65536 --parallel 4 --n-predict 4096 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG/logs/llama_server/cmp_orig_turbo_7b_p4c64k_$(date +%Y%m%d_%H%M%S).log
```

### TH2 Build

```bash
tmux new -s bld_orig_turbo_7b_p4c64k
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG
mkdir -p logs/build_graph outputs/build_graph
for D in 1 10 50 100; do
  L=$(printf "%03ddocs" "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_orig_turbo_7b_p4c64knp4096_${L} \
    --local_llm_backend turboquant \
    --llm_model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096 \
    --llm_base_url http://localhost:8080/v1 \
    --embedding_base_url http://localhost:11434 \
    --embedding_model nomic-embed-text \
    --embedding_dim 768 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --num_docs "$D" \
    --llm_max_async 4 \
    --llm_timeout 600 \
    --turboquant_healthcheck \
    2>&1 | tee logs/build_graph/cmp_orig_turbo_7b_p4c64knp4096_${L}.log
done
```

### TH3 Build: TQ + Ollama 7B

```bash
tmux new -s bld_tq_ollama_7b
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
mkdir -p logs/build_graph outputs/build_graph
for D in 1 10 50 100; do
  L=$(printf "%03ddocs" "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_ollama_7b_api_${L} \
    --model qwen2.5:7b-instruct \
    --base_url http://localhost:11434 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend ollama \
    --embedding_provider ollama \
    --embedding_base_url http://localhost:11434 \
    --num_docs "$D" \
    --llm_max_async 4 \
    --llm_timeout 600 \
    2>&1 | tee logs/build_graph/cmp_tq_ollama_7b_api_${L}.log
done
```

### TH4 Build: Original + Ollama 7B

```bash
tmux new -s bld_orig_ollama_7b
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG
mkdir -p logs/build_graph outputs/build_graph
for D in 1 10 50 100; do
  L=$(printf "%03ddocs" "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_orig_ollama_7b_api_${L} \
    --local_llm_backend normal \
    --llm_model qwen2.5:7b-instruct \
    --llm_base_url http://localhost:11434 \
    --embedding_base_url http://localhost:11434 \
    --embedding_model nomic-embed-text \
    --embedding_dim 768 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --num_docs "$D" \
    --llm_max_async 4 \
    --llm_timeout 600 \
    2>&1 | tee logs/build_graph/cmp_orig_ollama_7b_api_${L}.log
done
```

### TH5 Build: TQ + Gemini

```bash
tmux new -s bld_tq_gemini
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
mkdir -p logs/build_graph outputs/build_graph
for D in 1 10 50 100; do
  L=$(printf "%03ddocs" "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_gemini_api_${L} \
    --provider gemini \
    --model gemini-2.5-flash-lite \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --embedding_provider ollama \
    --embedding_base_url http://localhost:11434 \
    --num_docs "$D" \
    --llm_max_async 4 \
    --llm_timeout 600 \
    2>&1 | tee logs/build_graph/cmp_tq_gemini_api_${L}.log
done
```

Thực tế TH5 có thêm 384 docs và đã success.

### TH6 Build: Original + Gemini

```bash
tmux new -s bld_orig_gemini
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG
mkdir -p logs/build_graph outputs/build_graph
for D in 1 10 50 100; do
  L=$(printf "%03ddocs" "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_orig_gemini_api_${L} \
    --provider gemini \
    --model gemini-2.5-flash-lite \
    --embedding_provider ollama \
    --embedding_base_url http://localhost:11434 \
    --embedding_model nomic-embed-text \
    --embedding_dim 768 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --num_docs "$D" \
    --llm_max_async 4 \
    --llm_timeout 600 \
    2>&1 | tee logs/build_graph/cmp_orig_gemini_api_${L}.log
done
```

Thực tế TH6 hiện đã có thêm 384 docs chạy thành công; vẫn không phải local LLM vì LLM extraction dùng Gemini API.

### TH7 Server: TQ + TurboQuant 14B Q5

Trạng thái hiện tại theo ghi chú chạy thực tế:

- Server TH7 đang chạy đúng alias `qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096`.
- Process server hiện tại dùng `Qwen3-14B-Q5_0.gguf`.
- Context `-c 32768`, `--parallel 2`, `--n-predict 4096`.
- Server log có request thành công, `truncated = 0`, decode khoảng 62-66 tokens/s, nên server OK.

Nếu server này đang chạy đúng alias thì không cần start lại. Nếu cần start lại TH7 server từ Turboquant output folder, dùng mẫu tương tự TH8 nhưng log về repo Turboquant:

```bash
tmux new -s srv_tq_turbo_14bq5_p2c32k
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/Qwen3-14B-Q5_0.gguf \
  --alias qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 2 \
  --n-predict 4096 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/cmp_tq_turbo_14bq5_p2c32k_$(date +%Y%m%d_%H%M%S).log
```

### TH7 Build: TQ + TurboQuant 14B Q5, chạy 5/10/50/100 docs

Bỏ 1 doc vì theo ghi chú đã có process 001docs đang/đã chạy. Nếu muốn benchmark sạch, đợi process 001docs xong rồi mới chạy block này; chạy song song sẽ tranh cùng llama-server và làm sai thời gian.

```bash
tmux new -s bld_tq_turbo_14bq5_p2c32k_005_100docs
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

mkdir -p logs/build_graph outputs/build_graph

for D in 5 10 50 100; do
  L=$(printf "%03ddocs" "$D")

  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_${L} \
    --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider ollama \
    --embedding_base_url http://localhost:11434 \
    --num_docs "$D" \
    --llm_max_async 2 \
    --llm_timeout 900 \
    2>&1 | tee logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_${L}.log
done
```

Check trong lúc chạy:

```bash
grep -E "new chunks|chunk LLM extraction|Graph building completed|timed out|ERROR|Total elapsed" \
  /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_*.log
```

### TH8 Server: Original Repo + TurboQuant 14B Q5

Lý do sửa TH8 từ Q8 sang Q5:

- Qwen3 14B Q8 đã có bằng chứng OOM VRAM khi tạo KV cache ở TH11 server Q8.
- Q5 giảm VRAM cho weights, để còn chỗ cho KV cache ở `-c 32768`.
- Giữ `-ctk q8_0 -ctv turbo3` để nén KV phần V nhưng giữ K an toàn hơn.
- TH8 có thể dùng chung server Q5 với TH7 nếu server đang chạy đúng alias `qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096`.

Tmux:

```bash
tmux new -s srv_orig_turbo_14bq5_p2c32k
```

Lệnh server:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG/logs/llama_server

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/Qwen3-14B-Q5_0.gguf \
  --alias qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 2 \
  --n-predict 4096 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG/logs/llama_server/cmp_orig_turbo_14bq5_p2c32k_$(date +%Y%m%d_%H%M%S).log
```

### TH8 Build: Original Repo + TurboQuant 14B Q5

Tmux:

```bash
tmux new -s bld_orig_turbo_14bq5_p2c32k
```

Lệnh build:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG

mkdir -p logs/build_graph outputs/build_graph

for D in 1 10 50; do
  L=$(printf "%03ddocs" "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_orig_turbo_14bq5_p2c32knp4096_${L} \
    --local_llm_backend turboquant \
    --llm_model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
    --llm_base_url http://localhost:8080/v1 \
    --embedding_base_url http://localhost:11434 \
    --embedding_model nomic-embed-text \
    --embedding_dim 768 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --num_docs "$D" \
    --llm_max_async 2 \
    --llm_timeout 900 \
    --turboquant_healthcheck \
    2>&1 | tee logs/build_graph/cmp_orig_turbo_14bq5_p2c32knp4096_${L}.log
done
```

### TH9 Build: Turboquant Repo + Ollama 14B

Trước khi chạy TH9, stop llama-server TH7/TH8 nếu đang chạy. Lý do: TH9 dùng Ollama `qwen3:14b`, không dùng llama-server; nếu để llama-server giữ Qwen3 14B trong VRAM thì Ollama sẽ tranh GPU, dễ chậm/OOM và thời gian benchmark không sạch.

Tmux:

```bash
tmux new -s bld_tq_ollama_14b
```

Lệnh build:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

mkdir -p logs/build_graph outputs/build_graph

ollama pull qwen3:14b
ollama pull nomic-embed-text

for D in 1 10 50; do
  L=$(printf "%03ddocs" "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_ollama_14b_api_${L} \
    --model qwen3:14b \
    --base_url http://localhost:11434 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend ollama \
    --embedding_provider ollama \
    --embedding_base_url http://localhost:11434 \
    --num_docs "$D" \
    --llm_max_async 1 \
    --llm_timeout 900 \
    2>&1 | tee logs/build_graph/cmp_tq_ollama_14b_api_${L}.log
done
```

### TH10 Build: Original Repo + Ollama 14B

Không chạy song song TH10 với TH9 nếu muốn đo tốc độ sạch, vì cả hai đều gọi Ollama `qwen3:14b` và `nomic-embed-text`, dễ tranh GPU/CPU/RAM.

Tmux:

```bash
tmux new -s bld_orig_ollama_14b
```

Lệnh build:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG

mkdir -p logs/build_graph outputs/build_graph

ollama pull qwen3:14b
ollama pull nomic-embed-text

for D in 1 10 50; do
  L=$(printf "%03ddocs" "$D")
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_orig_ollama_14b_api_${L} \
    --local_llm_backend normal \
    --llm_model qwen3:14b \
    --llm_base_url http://localhost:11434 \
    --embedding_base_url http://localhost:11434 \
    --embedding_model nomic-embed-text \
    --embedding_dim 768 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --num_docs "$D" \
    --llm_max_async 1 \
    --llm_timeout 900 \
    2>&1 | tee logs/build_graph/cmp_orig_ollama_14b_api_${L}.log
done
```

### Check nhanh TH7-TH10

```bash
grep -E "new chunks|chunk LLM extraction|Graph building completed|timed out|ERROR|Total elapsed" \
  /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_turbo_14bq5_p2c32knp4096_*.log

grep -E "new chunks|chunk LLM extraction|Graph building completed|timed out|ERROR|Total elapsed" \
  /home/guest/Projects/Research/Temporal-GraphRAG/logs/build_graph/cmp_orig_turbo_14bq5_p2c32knp4096_*.log

grep -E "new chunks|chunk LLM extraction|Graph building completed|timed out|ERROR|Total elapsed" \
  /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/cmp_tq_ollama_14b_api_*.log

grep -E "new chunks|chunk LLM extraction|Graph building completed|timed out|ERROR|Total elapsed" \
  /home/guest/Projects/Research/Temporal-GraphRAG/logs/build_graph/cmp_orig_ollama_14b_api_*.log
```

### TH11 Start llama-server 14B Q5

```bash
tmux new -s srv_th11_c1_14b_top_level
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

RUN_ID=$(date +%Y%m%d_%H%M%S)
echo "RUN_ID=${RUN_ID}"

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/llama_server

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/Qwen3-14B-Q5_0.gguf \
  --alias qwen3-14b-instruct \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2/logs/llama_server/srv_th11_c1_14bq5_top_level_${RUN_ID}.log
```

### TH11A Build: c1f1ea2 nguyên bản

```bash
tmux new -s bld_th11a_c1_original_all
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2

RUN_ID=$(date +%Y%m%d_%H%M%S)
echo "RUN_ID=${RUN_ID}"

mkdir -p logs/build_graph outputs/build_graph results/usage

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

for D in 1 5 10 50; do
  L=$(printf "%03ddocs" "$D")
  export TG_RAG_USAGE_LOG=results/usage/th11a_c1_original_${L}_${RUN_ID}.jsonl

  python -u build_graph.py \
    --output_dir outputs/build_graph/th11a_c1_original_${L}_${RUN_ID} \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --num_docs "$D" \
    2>&1 | tee logs/build_graph/th11a_c1_original_${L}_${RUN_ID}.log
done
```

Thực tế đã có thêm 100 và 384 docs với RUN_ID `20260522_204618`.

### TH11B Build: ép c1f1ea2 dùng llama-server

```bash
tmux new -s bld_th11b_c1_openai14b_all
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant-th11-c1f1ea2

RUN_ID=$(date +%Y%m%d_%H%M%S)
echo "RUN_ID=${RUN_ID}"

mkdir -p logs/build_graph outputs/build_graph configs_runtime results/usage

cp tgrag/configs/config.yaml configs_runtime/th11b_c1_openai14b_${RUN_ID}.yaml

perl -0pi -e 's/provider: "gemini"/provider: "openai"/g' configs_runtime/th11b_c1_openai14b_${RUN_ID}.yaml
perl -0pi -e 's/model: "gemini-2\.5-flash-lite"/model: "qwen3-14b-instruct"/g' configs_runtime/th11b_c1_openai14b_${RUN_ID}.yaml
perl -0pi -e 's/model: "gemini-2\.5-flash"/model: "qwen3-14b-instruct"/g' configs_runtime/th11b_c1_openai14b_${RUN_ID}.yaml

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

for D in 1 5 10 50; do
  L=$(printf "%03ddocs" "$D")
  export TG_RAG_USAGE_LOG=results/usage/th11b_c1_openai14b_${L}_${RUN_ID}.jsonl

  python -u build_graph.py \
    --config configs_runtime/th11b_c1_openai14b_${RUN_ID}.yaml \
    --output_dir outputs/build_graph/th11b_c1_openai14b_${L}_${RUN_ID} \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --num_docs "$D" \
    2>&1 | tee logs/build_graph/th11b_c1_openai14b_${L}_${RUN_ID}.log
done
```

Thực tế chỉ thấy 1 docs success và 5 docs incomplete với RUN_ID `20260522_211255`.

## 17. Checklist kiểm tra sau mỗi run

### 15.1 Kiểm backend thật sự

```bash
rg -n 'model|gemini-2.5-flash-lite|qwen3-14b-instruct|qwen2.5:7b-instruct|qwen25' \
  outputs/build_graph/<OUTPUT_FOLDER>/kv_store_llm_response_cache.json
```

Nếu cache ghi Gemini thì không phải local LLM. Nếu cache ghi alias của llama-server và server log có `POST /v1/chat/completions` thì mới là local llama-server.

### 15.2 Kiểm lỗi community context

```bash
rg -n 'exceeds available context size|context length|error|Error' \
  outputs/build_graph/<OUTPUT_FOLDER>/kv_store_community_reports.json
```

### 15.3 Kiểm lỗi build graph

```bash
rg -n 'Error during graph building|Ollama embedding API error|exceeds available context size|Traceback' \
  logs/build_graph/<BUILD_LOG>.log
```

### 15.4 Kiểm server thật sự nhận request

```bash
rg -n 'POST /v1/chat/completions|exceeds available context size|n_ctx|n_ctx_seq|slot|cudaMalloc failed|decode|prompt eval' \
  logs/llama_server/<SERVER_LOG>.log
```

### 15.5 Kiểm output đã hoàn tất chưa

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

Nếu chỉ có `kv_store_llm_response_cache.json` thì run chưa hoàn tất.

## 18. Ước lượng thời gian khi chạy 384 docs

| Cấu hình | Cơ sở ước lượng | Ước lượng 384 docs | Rủi ro |
|---|---|---|---|
| TH5 Gemini | đã có kết quả thật 384 docs | 12779.23s, khoảng 3h33m | không phải local LLM |
| 7B TurboQuant p4/c64k cũ | TH1 50 docs 3283s nhưng có lỗi context | có thể nhiều giờ, nhưng không khuyến nghị | community report lỗi do 16k slot |
| 7B TurboQuant p2/c64k mới | giảm parallel nên mỗi slot nhiều context hơn | có thể chậm hơn p4, nhưng sạch hơn | cần test 50/100 trước |
| 7B TurboQuant p1/c64k | an toàn context nhất | chậm hơn p2 | phù hợp nếu p2 vẫn lỗi context |
| 14B Q5 p1/c32k | TH11B 1 doc 442.59s | rất lâu, không nên chạy 384 ngay | tốc độ thấp, 5 docs còn chưa xong |

Cách ước lượng sau khi chạy lại:

```text
seconds_per_chunk = elapsed_seconds / số_chunks_đã_xử_lý
ước lượng 384 = seconds_per_chunk * 1462 + thời gian community + thời gian embedding/persist
```

Nhưng community reports không tuyến tính hoàn toàn, vì càng nhiều docs thì community prompt càng dài, nguy cơ context/embedding lỗi tăng.

## 19. Bổ sung: chọn embedding cho Temporal GraphRAG / ECT-QA

### 17.1 Kết luận nhanh

Với bài toán hiện tại, `nomic-embed-text` mặc định qua Ollama **không đủ để gọi là cấu hình ổn định cho full 384 docs**. Nó đủ để debug nhanh và chạy mốc nhỏ, nhưng log TH7 100 và TH11A 384 cho thấy lỗi thật nằm ở bước embedding entity/relation sau merge:

```text
Ollama embedding API error 500: {"error":"the input length exceeds the context length"}
```

Điểm then chốt: lỗi này không phải do LLM extraction, không phải do KV TurboQuant, cũng không phải do chunking ban đầu. Lỗi xảy ra sau khi Temporal GraphRAG đã gom/merge nhiều description vào cùng một entity hoặc relation, rồi source gửi nguyên content dài sang Ollama embedding.

Khuyến nghị thực dụng cho 16GB VRAM:

| Mục tiêu | Embedding nên dùng | Lý do | Điều kiện |
|---|---|---|---|
| Debug nhanh / mốc 1-50 docs | `nomic-embed-text` | Nhẹ, nhanh, đang chạy được với source hiện tại | Phải cap/truncate content vì Ollama model page ghi 2K context |
| Cấu hình cân bằng cho Temporal GraphRAG local | `bge-m3` | 567M/1.2GB, 8K context trên Ollama, hợp với 16GB hơn Qwen3 4B, có nền tảng dense/sparse/multi-vector | Cần patch source để chọn `embedding_model` và `embedding_dim=1024`; nếu dùng qua Ollama thì hiện chỉ tận dụng dense vector |
| Chất lượng dense local cao hơn | `qwen3-embedding:4b` | 4B, context 32K/40K, dimension 2560, instruction-aware, benchmark mạnh | Dễ tranh VRAM với Qwen3 14B Q5; nên chạy CPU/Ollama riêng hoặc không chạy cùng lúc với llama-server 14B |
| Retrieval hybrid đúng nghĩa | BGE-M3 qua `FlagEmbedding` hoặc hybrid BM25+dense | Dùng được sparse + dense + multi-vector thay vì chỉ dense | Cần sửa retrieval/vector store nhiều hơn, không chỉ đổi model Ollama |

Kết luận setup: nếu mục tiêu là **apply TurboQuant vào local LLM** và vẫn muốn build ổn định trên 16GB VRAM, hướng hợp lý nhất là:

```text
LLM extraction/community: Qwen3 14B Q5 qua llama-server TurboQuant
Embedding baseline ổn định: bge-m3 qua Ollama hoặc service riêng
Fallback nhanh: nomic-embed-text, nhưng chỉ sau khi cap content
High-quality dense test: qwen3-embedding:4b, nhưng không nên chạy tranh GPU với llama-server 14B
```

### 17.2 ECT-QA cần embedding khác normal RAG ở đâu?

Nguồn ECT-QA trên Hugging Face mô tả dataset gồm 480 earnings call transcripts từ 24 công ty giai đoạn 2020-2024, 1,105 specific questions và 100 abstract questions, phục vụ time-sensitive QA cho RAG/GraphRAG. Base corpus là 2020-2023 với 384 transcripts, new corpus là 2024 với 96 transcripts. Các câu hỏi có single-time, multi-time và relative-time reasoning.

Vì vậy embedding trong Temporal GraphRAG không chỉ dùng để “search document”. Nó ảnh hưởng trực tiếp tới:

- Entity retrieval: lấy đúng entity như `CHINA`, `FREE CASH FLOW`, `CROCS`, `JD.COM`.
- Temporal separation: phân biệt cùng entity nhưng khác quý/năm.
- Graph neighborhood quality: lấy đúng cạnh/neighbor theo thời gian.
- Community report quality: community bị tạo từ graph; graph noisy thì report cũng noisy.
- Multi-hop retrieval: sai seed node hoặc sai temporal neighborhood là sai cả reasoning chain.

Với ECT-QA, nhiều transcript cùng công ty lặp lại entity qua nhiều quý. Nếu embedding space kéo các mô tả “cùng entity nhưng khác thời điểm” quá gần nhau, graph dễ merge bẩn. Nếu embedding input quá dài, vector đại diện bị loãng hoặc fail context như TH7/TH11A.

### 17.3 Vì sao `nomic-embed-text` chưa đủ cho full 384?

Ollama page của `nomic-embed-text` ghi các biến thể trong Ollama có context window 2K. Trong source hiện tại, `ollama_embedding()` mặc định model là `nomic-embed-text` và gửi payload tới `/api/embeddings`:

```python
@wrap_embedding_func_with_attrs(embedding_dim=768, max_token_size=8192)
async def ollama_embedding(
    texts: List[str],
    model: str = "nomic-embed-text",
    base_url: Optional[str] = None
) -> np.ndarray:
    ...
    payload = {
        "model": model,
        "prompt": text,
    }
    async with session.post(
        f"{ollama_url}/api/embeddings",
        json=payload
    ) as response:
        if response.status != 200:
            error_text = await response.text()
            raise Exception(f"Ollama embedding API error {response.status}: {error_text}")
```

Trong TH7 100, source tạo entity vector content như sau:

```python
"content": dp["entity_name"] + " " + dp.get("description", "")
```

Với local Qwen3 14B Q5, description một số entity rất dài:

| Run | Max node description | Kết quả |
|---|---:|---|
| TH7 50 | khoảng 9308 chars | Pass nhưng đã nguy hiểm |
| TH7 100 | khoảng 16408 chars | Fail ở `entity_vdb.upsert` |
| TH11A 384 | khoảng 29523 chars | Fail embedding |
| TH6 384 Gemini | khoảng 2934 chars | Pass |

Do đó vấn đề không phải “Ollama embedding luôn tệ”. Vấn đề là `nomic-embed-text` qua Ollama đang quá ngắn cho entity/relation content sau merge. Nếu tiếp tục dùng `nomic`, bắt buộc phải giới hạn input:

```text
embedding_max_tokens_nomic ~= 1500-1800 tokens
hoặc embedding_max_chars ~= 6000-8000 chars
```

Nhưng với Temporal GraphRAG, truncate thô chỉ là guard chống fail. Cách tốt hơn là summarize/cap description sau merge để mỗi entity vector vẫn đại diện rõ theo thời gian.

### 17.4 Vì sao nghiêng về BGE-M3 cho cấu hình cân bằng?

BGE-M3 phù hợp case này hơn `nomic` vì ba lý do:

1. BGE-M3 được thiết kế multi-functionality: dense retrieval, sparse retrieval và multi-vector retrieval.
2. BGE-M3 hỗ trợ multi-granularity tới 8192 tokens, hợp hơn với event summaries, community summaries và entity descriptions dài.
3. BGE-M3 nhỏ hơn nhiều so với `qwen3-embedding:4b`, nên hợp với máy 16GB VRAM khi `llama-server` Qwen3 14B Q5 đã chiếm phần lớn VRAM.

Lưu ý quan trọng: nếu chỉ gọi `bge-m3` qua Ollama `/api/embed` hoặc `/api/embeddings`, pipeline hiện tại vẫn chỉ nhận **dense vector**. Như vậy ta chưa tận dụng đầy đủ sparse và multi-vector của BGE-M3. Tuy nhiên, ngay cả dense-only, BGE-M3 vẫn đáng thử vì context 8K và embedding space ổn hơn cho long/semi-structured retrieval.

Muốn dùng đúng “hybrid native” của BGE-M3 cho Temporal GraphRAG thì cần sửa retrieval layer:

```text
dense vector score
+ sparse lexical/BM25 score theo entity_name, timestamp, company, quarter
+ optional multi-vector/ColBERT score cho long description/community report
+ RRF hoặc weighted fusion
```

Nếu chưa sửa hybrid retrieval, bước hợp lý là dùng `bge-m3` dense trước để thay `nomic`, sau đó mới thêm BM25/sparse.

### 17.5 Qwen3-Embedding:4B có nên dùng không?

`qwen3-embedding:4b` là lựa chọn chất lượng cao hơn cho dense retrieval. Qwen model card ghi Qwen3-Embedding-4B có context length 32K, embedding dimension tới 2560, hỗ trợ custom dimensions và instruction-aware usage. Ollama library ghi `qwen3-embedding:4b` khoảng 2.5GB với 40K context window.

Nhưng với setup hiện tại:

- `llama-server` Qwen3 14B Q5 TH7 đã projected dùng khoảng 11.4GB VRAM.
- 16GB VRAM không còn nhiều dư địa nếu Ollama cũng cố load `qwen3-embedding:4b` lên GPU.
- Nếu chạy cùng lúc có thể tranh GPU, làm build chậm hoặc OOM.

Do đó `qwen3-embedding:4b` nên là test chất lượng, không phải baseline ổn định đầu tiên. Nếu dùng, nên chạy theo một trong hai cách:

```text
Cách A: stop llama-server, chỉ benchmark embedding/query riêng.
Cách B: ép embedding chạy CPU hoặc service riêng, chấp nhận chậm hơn.
Cách C: dùng qwen3-embedding:0.6b trước nếu cần nhẹ hơn.
```

Với Temporal GraphRAG/ECT-QA, `qwen3-embedding:4b` có thể tốt cho semantic quality, nhưng không thay thế được guard input length. Description quá dài vẫn nên cap/summarize, vì embedding một đoạn quá dài thường làm vector bị loãng theo temporal signal.

### 17.6 Source hiện tại chưa cho đổi embedding model bằng CLI

Trong repo Turboquant hiện tại, `build_graph.py` chỉ có:

```text
--embedding_provider
--embedding_base_url
```

Ollama docs hiện mô tả endpoint mới `/api/embed` cho embedding và ghi endpoint này trả vector đã L2-normalized. Source hiện tại vẫn gọi endpoint legacy `/api/embeddings`. Endpoint legacy vẫn đang chạy trong log, nhưng nếu đã patch embedding model thì nên cân nhắc chuyển wrapper sang `/api/embed` để đồng bộ với docs mới.

Chưa có:

```text
--embedding_model
--embedding_dim
```

Trong `tgrag/src/build.py`, nhánh Ollama đang hardcode:

```python
elif embedding_provider == "ollama":
    return await ollama_embedding(texts, base_url=base_url)
...
elif embedding_provider == "ollama":
    return EmbeddingFunc(
        embedding_dim=768,
        func=embedding_wrapper,
        max_token_size=8192
    )
```

Vì vậy nếu chỉ chạy:

```bash
ollama pull bge-m3
```

thì build graph vẫn dùng `nomic-embed-text`, trừ khi sửa source. Patch cần có trước khi benchmark embedding:

```text
1. Thêm CLI: --embedding_model, --embedding_dim, --embedding_max_chars hoặc --embedding_max_tokens.
2. Truyền embedding_model vào create_embedding_function().
3. Gọi ollama_embedding(texts, model=embedding_model, base_url=base_url).
4. Set đúng embedding_dim:
   - nomic-embed-text: 768
   - bge-m3: 1024
   - qwen3-embedding:0.6b: 1024
   - qwen3-embedding:4b: 2560
   - qwen3-embedding:8b: 4096
5. Rebuild toàn bộ vector store sau khi đổi embedding model/dim. Không được dùng lẫn output cũ.
```

Lệnh mục tiêu sau khi đã patch source:

```bash
ollama pull bge-m3
ollama pull qwen3-embedding:4b

# Baseline cân bằng nên test trước
python -u build_graph.py \
  --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_bgem3_p2c32knp4096_050docs \
  --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --embedding_model bge-m3 \
  --embedding_dim 1024 \
  --num_docs 50 \
  --llm_max_async 2 \
  --llm_timeout 900
```

### 17.6.1 Nếu không dùng Ollama embedding mà chuyển sang HuggingFace local

Phân tích này là **hướng setup, chưa code**. Kết luận ngắn: ý tưởng chuyển embedding cùng model từ Ollama sang HuggingFace là hợp lý, nhưng không phải chỉ đổi lệnh chạy là xong. Source hiện tại chưa có nhánh HuggingFace native, và vector store phải rebuild toàn bộ sau khi đổi model/dim.

Điểm đúng trong nghi vấn của bạn:

| Điểm nghi vấn | Kết luận | Bằng chứng/giải thích |
|---|---|---|
| Ollama `nomic-embed-text` bị context ngắn hơn model gốc HF | Đúng với model page hiện tại của Ollama | Trang Ollama `nomic-embed-text` ghi context 2K, trong khi HuggingFace `nomic-ai/nomic-embed-text-v1.5` ghi sequence length 8192 và dimension 768 |
| Dùng cùng model qua HuggingFace có thể giảm lỗi `input length exceeds context length` | Đúng một phần | Nếu dùng HF đúng `model_max_length=8192`, input dài vừa phải có thể qua được; nhưng entity description 16K-29K ký tự vẫn có thể vượt 8192 tokens hoặc làm vector bị loãng |
| Chuyển HF là thay thế được guard/truncate | Không đúng | Dù HF context dài hơn, Temporal GraphRAG vẫn merge description dài theo entity. Vẫn phải cap/log content trước embedding |
| Có thể dùng HuggingFace chung với `llama-server` TurboQuant | Đúng | LLM extraction/community vẫn đi qua `llama-server` TurboQuant; embedding là pipeline riêng, có thể chạy bằng HF trên CPU/GPU/service khác |

Source hiện tại đang giới hạn việc này:

```python
# tgrag/src/build.py
elif embedding_provider == "ollama":
    return await ollama_embedding(texts, base_url=base_url)
...
elif embedding_provider == "ollama":
    return EmbeddingFunc(
        embedding_dim=768,
        func=embedding_wrapper,
        max_token_size=8192
    )
```

và:

```python
# tgrag/src/llm/embedding.py
async def ollama_embedding(
    texts: List[str],
    model: str = "nomic-embed-text",
    base_url: Optional[str] = None
) -> np.ndarray:
    payload = {
        "model": model,
        "prompt": text,
    }
    session.post(f"{ollama_url}/api/embeddings", json=payload)
```

Nghĩa là hiện tại:

```text
--embedding_provider ollama
-> luôn gọi ollama_embedding(...)
-> model default vẫn là nomic-embed-text
-> embedding_dim của Ollama bị hardcode 768
-> chưa có --embedding_model / --embedding_dim / --embedding_max_tokens
-> chưa có embedding_provider=huggingface
```

Nếu muốn dùng HuggingFace native, hướng setup đúng nên là:

| Thành phần | Setup đề xuất |
|---|---|
| LLM build graph | Giữ TH7/TH1 như cũ: `--local_llm_backend turboquant`, `--base_url http://localhost:8080/v1`, model alias local từ `llama-server` |
| Embedding provider mới | Thêm nhánh `embedding_provider=huggingface` hoặc `sentence_transformers` |
| Model HF cùng model hiện tại | `nomic-ai/nomic-embed-text-v1.5` |
| Dim | 768 nếu dùng full nomic vector; nếu dùng Matryoshka truncate thì phải set dim tương ứng và rebuild vector store |
| Max tokens | 8192 theo HF model card, nhưng nên đặt guard thấp hơn, ví dụ 6000-7500 tokens, để tránh sát ngưỡng |
| Prefix | Với Nomic nên dùng prefix `search_document:` cho entity/relation/community content; query sau này dùng `search_query:` |
| Runtime | Nếu dùng Qwen3 14B Q5 trên GPU, nên để embedding HF chạy CPU hoặc batch nhỏ. Nếu ép HF embedding lên GPU cùng lúc, có thể tranh VRAM với `llama-server` |
| Output | Bắt buộc tạo output folder mới; không dùng lẫn vector store cũ vì model/dim khác nhau |

Có hai cách triển khai:

| Cách | Mô tả | Ưu điểm | Rủi ro |
|---|---|---|---|
| A. Patch native HuggingFace trong repo | Thêm `huggingface_embedding()` dùng `sentence-transformers` hoặc `FlagEmbedding`, rồi thêm CLI `--embedding_model --embedding_dim --embedding_max_tokens` | Rõ nhất, kiểm soát được max length, batch size, device, prefix, logging | Cần sửa source và test lại vector store |
| B. Chạy embedding server OpenAI-compatible | Dựng service như Infinity/Text Embeddings Inference rồi gọi qua HTTP | Tách embedding thành service riêng, dễ chạy CPU/GPU riêng | Source hiện tại `openai_embedding()` hardcode `text-embedding-3-small` và `embedding_dim=1536`, nên vẫn cần patch để truyền model/dim |
| C. Tiếp tục dùng Ollama nhưng đổi model | Dùng `bge-m3`/`qwen3-embedding` qua Ollama sau khi patch `embedding_model` | Ít thay đổi hạ tầng nhất | Vẫn phụ thuộc context/model config của Ollama và chỉ lấy dense vector |

#### Hướng triển khai chi tiết để không ảnh hưởng Ollama hiện tại

Mục tiêu triển khai là **thêm HuggingFace như một provider mới**, không sửa đè nhánh Ollama hiện tại. Khi không truyền `--embedding_provider huggingface`, toàn bộ TH cũ dùng Ollama vẫn chạy như cũ.

Các file nên thêm/sửa theo hướng ít phá nhất:

| Việc | File | Cách làm | Có ảnh hưởng Ollama không? |
|---|---|---|---|
| Thêm dependency HF | `requirements.txt` | Thêm optional dependency `sentence-transformers`, `transformers`, `torch`, `huggingface_hub` | Không, chỉ cài thêm thư viện |
| Tạo wrapper HF riêng | `tgrag/src/llm/huggingface_embedding.py` | Tạo file mới, không sửa logic `ollama_embedding()` | Không |
| Export wrapper | `tgrag/src/llm/__init__.py` | Import `huggingface_embedding` và thêm vào `__all__` | Không |
| Cho CLI nhận provider mới | `build_graph.py` | Thêm choice `huggingface` và các option model/dim/max_tokens/device/batch | Không, default vẫn là Ollama |
| Đọc config mới | `tgrag/src/build.py` | Truyền `embedding_model`, `embedding_dim`, `embedding_max_tokens` xuống `create_embedding_function()` | Không |
| Guard input dài | `tgrag/src/storage/vector_nanovectordb.py` | Truncate/log trước khi gọi bất kỳ embedding provider nào | Có tác dụng tốt cho cả Ollama và HF, nhưng nên bật bằng config để kiểm soát |

Dependency đề xuất trong `requirements.txt`:

```text
# HuggingFace local embeddings, optional
sentence-transformers>=3.0.0
transformers>=4.40.0
huggingface_hub>=0.23.0
accelerate>=0.30.0
# torch nên cài theo CUDA/CPU của máy; nếu môi trường đã có torch thì không cần thêm dòng này.
```

Token HuggingFace:

```text
- Với nomic-ai/nomic-embed-text-v1.5 và BAAI/bge-m3 public: thường không bắt buộc HF token.
- Nếu model private/gated hoặc muốn tránh rate/download issue: dùng HF_TOKEN qua env, không ghi token vào YAML/code.
- Nếu muốn cache model trong workspace: set HF_HOME hoặc TRANSFORMERS_CACHE.
```

Lệnh setup token/cache:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false

# Chỉ cần nếu model private/gated hoặc muốn login sẵn.
# Không lưu token vào repo.
export HF_TOKEN=hf_xxx
# hoặc: huggingface-cli login
```

File mới nên đặt ở:

```text
/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/tgrag/src/llm/huggingface_embedding.py
```

Code mẫu cho file mới, chỉ là thiết kế để patch sau:

```python
import asyncio
from typing import List

import numpy as np

_HF_EMBEDDERS = {}


def _get_hf_embedder(model_name: str, device: str, max_tokens: int, trust_remote_code: bool):
    key = (model_name, device, max_tokens, trust_remote_code)
    if key not in _HF_EMBEDDERS:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(
            model_name,
            device=device,
            trust_remote_code=trust_remote_code,
        )
        model.max_seq_length = max_tokens
        _HF_EMBEDDERS[key] = model
    return _HF_EMBEDDERS[key]


async def huggingface_embedding(
    texts: List[str],
    model: str = "nomic-ai/nomic-embed-text-v1.5",
    device: str = "cpu",
    batch_size: int = 16,
    max_tokens: int = 7500,
    prefix: str = "search_document: ",
    normalize_embeddings: bool = True,
    trust_remote_code: bool = True,
) -> np.ndarray:
    def _encode() -> np.ndarray:
        embedder = _get_hf_embedder(model, device, max_tokens, trust_remote_code)
        prepared = [text if not prefix or text.startswith(prefix) else prefix + text for text in texts]
        vectors = embedder.encode(
            prepared,
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.astype(np.float32)

    return await asyncio.to_thread(_encode)
```

Cần thêm import trong `tgrag/src/llm/__init__.py`:

```diff
+from .huggingface_embedding import huggingface_embedding
...
+    "huggingface_embedding",
```

Cần sửa `tgrag/src/build.py` để import:

```diff
 from .llm import (
     openai_embedding,
     azure_openai_embedding,
     amazon_bedrock_embedding,
     ollama_embedding,
+    huggingface_embedding,
 )
```

Sau khi patch xong, cách chạy đúng local LLM + HF embedding + TurboQuant là:

```bash
# 1. Start llama-server TurboQuant cho LLM, giữ như TH7 Q5.
cd /home/guest/Projects/Research/llama-cpp-turboquant
./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/Qwen3-14B-Q5_0.gguf \
  --alias qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 2 \
  --n-predict 4096
```

```bash
# 2. Build graph với HF embedding. Lệnh này chỉ chạy được sau khi patch CLI/source.
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TOKENIZERS_PARALLELISM=false

python -u build_graph.py \
  --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_hf_nomic_p2c32knp4096_050docs \
  --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cpu \
  --embedding_batch_size 16 \
  --num_docs 50 \
  --llm_max_async 2 \
  --llm_timeout 1200
```

Check log bắt buộc sau khi chạy:

```bash
grep -E "runtime|embedding_provider|embedding_model|embedding content lengths|vector upsert|Ollama embedding API error|Graph building completed|Total elapsed" \
  logs/build_graph/cmp_tq_turbo_14bq5_hf_nomic_p2c32knp4096_050docs.log
```

Kỳ vọng đúng:

```text
[runtime] local_llm_backend=turboquant provider=openai model=qwen3-14b-q5-...
[runtime] embedding_provider=huggingface embedding_model=nomic-ai/nomic-embed-text-v1.5 embedding_dim=768
server log có POST /v1/chat/completions cho LLM extraction/community
build log không còn Ollama embedding API error
output folder mới có đủ full_docs/text_chunks/vdb/community/GraphML
```

Nếu muốn dùng BGE-M3 HF thay cùng cách:

```bash
python -u build_graph.py \
  --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_hf_bgem3_p2c32knp4096_050docs \
  --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model BAAI/bge-m3 \
  --embedding_dim 1024 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cpu \
  --embedding_batch_size 8 \
  --num_docs 50 \
  --llm_max_async 2 \
  --llm_timeout 1200
```

Điểm quan trọng: đổi embedding model/dim thì phải dùng output folder mới. Không được dùng lại `vdb_entities.json`, `vdb_relations.json` cũ vì vector dimension và embedding space khác nhau.

Quy trình dùng thực tế sau khi quyết định patch source:

```text
Bước 1. Không xóa nhánh Ollama hiện tại. Chỉ thêm nhánh provider mới `huggingface`.
Bước 2. Thêm dependency HF và tải model vào HF cache.
Bước 3. Start `llama-server` TurboQuant như TH1/TH7 để phục vụ LLM extraction.
Bước 4. Chạy `build_graph.py` với `--embedding_provider huggingface`.
Bước 5. Kiểm log runtime: LLM phải là `base_url=http://localhost:8080/v1`; embedding phải là `huggingface`.
Bước 6. Nếu muốn quay lại Ollama, chỉ đổi CLI về `--embedding_provider ollama`; không cần revert code.
```

Lệnh cài/tải model nên chạy trước khi benchmark:

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

# Cài dependency sau khi đã quyết định patch. Nếu torch đã có sẵn trong env thì không cần cài lại torch.
pip install sentence-transformers transformers huggingface_hub accelerate

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TOKENIZERS_PARALLELISM=false

# Kiểm tra tải model public, không ghi token vào repo.
python - <<'PY_CHECK'
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True, device='cpu')
model.max_seq_length = 7500
vec = model.encode(['search_document: test temporal graph embedding'], normalize_embeddings=True)
print(vec.shape)
PY_CHECK
```

Nếu dùng model private/gated thì mới cần token:

```bash
export HF_TOKEN=hf_xxx
# hoặc dùng interactive login ngoài repo:
huggingface-cli login
```

Cần nhớ: các CLI `--embedding_model`, `--embedding_dim`, `--embedding_max_tokens`, `--embedding_max_chars`, `--embedding_device`, `--embedding_batch_size` chỉ chạy được sau khi đã áp các diff trong mục 17.6.2. Trước khi patch, source hiện tại chưa nhận các tham số này.

Với bài toán hiện tại, thứ tự nên làm là:

```text
1. Patch embedding guard trước: log/truncate theo token hoặc char trước khi gọi embedding.
2. Thêm CLI/config: --embedding_provider, --embedding_model, --embedding_dim, --embedding_max_tokens, --embedding_device, --embedding_batch_size.
3. Thêm provider huggingface native.
4. Test cùng model hiện tại: nomic-ai/nomic-embed-text-v1.5, dim=768, max_tokens<=8192.
5. Chạy lại TH7 50 -> 100. Nếu TH7 100 qua embedding thì mới chạy 384.
6. Sau đó mới so BGE-M3 HF: BAAI/bge-m3, dim=1024, max_tokens<=8192.
```

Lệnh mục tiêu sau khi đã patch source có thể có dạng:

```bash
python -u build_graph.py \
  --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_hf_nomic_p2c32knp4096_100docs \
  --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_device cpu \
  --embedding_batch_size 16 \
  --num_docs 100 \
  --llm_max_async 2 \
  --llm_timeout 900
```

Nếu đổi sang BGE-M3 HF:

```bash
python -u build_graph.py \
  --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_hf_bgem3_p2c32knp4096_100docs \
  --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model BAAI/bge-m3 \
  --embedding_dim 1024 \
  --embedding_max_tokens 7500 \
  --embedding_device cpu \
  --embedding_batch_size 8 \
  --num_docs 100 \
  --llm_max_async 2 \
  --llm_timeout 900
```

Giải thích vì sao cách này đúng với mục tiêu local LLM + embedding + TurboQuant:

```text
llama-server TurboQuant chỉ phục vụ LLM extraction/community qua /v1/chat/completions.
HuggingFace embedding phục vụ vector store entity/relation/community, không cần đi qua llama-server.
Hai phần này tách nhau, nên đổi embedding sang HF không làm mất TurboQuant ở local LLM.
```

Nhưng vẫn phải giữ guard input length. Lý do: lỗi TH7 100 xảy ra vì sau merge graph có entity description dài khoảng 16K ký tự; TH11A 384 từng thấy khoảng 29K ký tự. HF 8192 tokens giúp nhiều hơn Ollama 2K, nhưng không nên để một vector đại diện cho một entity bị nhồi quá nhiều quý/năm vì sẽ làm mất tín hiệu temporal.

### 17.6.2 Source đã rà và hướng code diff đề xuất cho HuggingFace embedding

Mục này ghi rõ theo source hiện tại của `Temporal-GraphRAG-Turboquant`, kết hợp với vai trò của `llama-cpp-turboquant`.

Kết luận sau khi rà source:

| File/source | Hiện tại đang làm gì | Vấn đề khi muốn dùng HF embedding |
|---|---|---|
| `build_graph.py` | CLI chỉ có `--embedding_provider` và `--embedding_base_url`; `choices` chỉ gồm `ollama/openai/azure/bedrock` | Chưa truyền được `embedding_model`, `embedding_dim`, `embedding_max_tokens`, `embedding_device`, `embedding_batch_size`; chưa chọn được `huggingface` |
| `build_graph.py -> apply_runtime_overrides()` | Khi `--local_llm_backend turboquant`, ép LLM provider thành `openai` và embedding default là `ollama` | Đúng cho TH1/TH7 hiện tại, nhưng nếu muốn HF thì phải cho override embedding provider/model/dim riêng, không được ảnh hưởng LLM provider |
| `tgrag/src/build.py -> create_embedding_function()` | Nhánh `ollama` gọi `ollama_embedding(texts, base_url=base_url)`; dim hardcode 768 | Không truyền được model; nếu `ollama pull bge-m3` thì vẫn gọi default `nomic-embed-text` |
| `tgrag/src/build.py -> create_temporal_graphrag_from_config()` | Chỉ xử lý key `embedding_provider` và `embedding_base_url` | Chưa đọc các key mới như `embedding_model`, `embedding_dim`, `embedding_max_tokens` |
| `tgrag/src/llm/embedding.py` | `ollama_embedding()` default `model="nomic-embed-text"` và gọi `/api/embeddings` | Chưa có hàm `huggingface_embedding()`; OpenAI embedding cũng hardcode `text-embedding-3-small` |
| `tgrag/src/storage/vector_nanovectordb.py` | Lấy `contents = [v["content"] ...]` rồi gọi embedding theo batch | Không truncate/log content dài; đây là nơi TH7 100 chết ở `entity_vdb.upsert` |
| `tgrag/src/core/building.py` | Tạo entity content bằng `entity_name + description`; relation content bằng description | Description sau merge có thể phình rất dài trước khi embedding |
| `llama-cpp-turboquant` | `llama-server` phục vụ LLM chat/completions cho TurboQuant; cũng có thể serve embedding model nếu start riêng với `--embedding` | Không phải nơi tốt nhất để sửa HF native embedding. Nếu dùng HF native thì embedding tách khỏi `llama-server`; nếu dùng GGUF embedding thì nên start server embedding riêng port khác |

Do đó code diff đúng nên đi theo hướng: **LLM vẫn qua `llama-server` TurboQuant, embedding thêm provider riêng `huggingface` trong repo Temporal-GraphRAG-Turboquant**.

#### Diff 1: thêm CLI embedding đầy đủ trong `build_graph.py`

Pseudo-diff, chưa áp dụng code:

```diff
# build_graph.py
 parser.add_argument(
     '--embedding_provider',
-    choices=['ollama', 'openai', 'azure', 'bedrock'],
+    choices=['ollama', 'openai', 'azure', 'bedrock', 'huggingface'],
     default=None,
     help='Override embedding provider from config'
 )
+
+parser.add_argument('--embedding_model', type=str, default=None)
+parser.add_argument('--embedding_dim', type=int, default=None)
+parser.add_argument('--embedding_max_tokens', type=int, default=None)
+parser.add_argument('--embedding_max_chars', type=int, default=None)
+parser.add_argument('--embedding_device', type=str, default=None)       # cpu/cuda
+parser.add_argument('--embedding_batch_size', type=int, default=None)
+parser.add_argument('--embedding_prefix', type=str, default=None)       # search_document:
```

Trong `apply_runtime_overrides()` cần thêm vào `override_config`:

```diff
 if embedding_provider:
     override_config["embedding_provider"] = embedding_provider
+if args.embedding_model:
+    override_config["embedding_model"] = args.embedding_model
+if args.embedding_dim:
+    override_config["embedding_dim"] = args.embedding_dim
+if args.embedding_max_tokens:
+    override_config["embedding_max_tokens"] = args.embedding_max_tokens
+if args.embedding_max_chars:
+    override_config["embedding_max_chars"] = args.embedding_max_chars
+if args.embedding_device:
+    override_config["embedding_device"] = args.embedding_device
+if args.embedding_batch_size:
+    override_config["embedding_batch_size"] = args.embedding_batch_size
+if args.embedding_prefix:
+    override_config["embedding_prefix"] = args.embedding_prefix
```

và runtime print nên in thêm:

```diff
 print(
     f"[runtime] embedding_provider={runtime_config['embedding_provider']} "
     f"embedding_base_url={runtime_config['embedding_base_url']}"
 )
+print(
+    f"[runtime] embedding_model={runtime_config.get('embedding_model')} "
+    f"embedding_dim={runtime_config.get('embedding_dim')} "
+    f"embedding_max_tokens={runtime_config.get('embedding_max_tokens')} "
+    f"embedding_device={runtime_config.get('embedding_device')}"
+)
```

Lý do: nếu không log các giá trị này, rất dễ lặp lại nhầm lẫn như TH11A: nhìn server/GPU nhưng không biết backend thật.

#### Diff 2: mở rộng `create_embedding_function()` trong `tgrag/src/build.py`

Pseudo-diff:

```diff
 def create_embedding_function(
     embedding_provider: str,
     api_key: Optional[str] = None,
     base_url: Optional[str] = None,
+    embedding_model: Optional[str] = None,
+    embedding_dim: Optional[int] = None,
+    embedding_max_tokens: Optional[int] = None,
+    embedding_device: Optional[str] = None,
+    embedding_batch_size: Optional[int] = None,
+    embedding_prefix: Optional[str] = None,
 ):
```

Trong wrapper:

```diff
         elif embedding_provider == "ollama":
-            return await ollama_embedding(texts, base_url=base_url)
+            return await ollama_embedding(
+                texts,
+                model=embedding_model or "nomic-embed-text",
+                base_url=base_url,
+            )
+        elif embedding_provider == "huggingface":
+            return await huggingface_embedding(
+                texts,
+                model=embedding_model or "nomic-ai/nomic-embed-text-v1.5",
+                device=embedding_device or "cpu",
+                batch_size=embedding_batch_size or 16,
+                max_tokens=embedding_max_tokens or 8192,
+                prefix=embedding_prefix or "search_document: ",
+            )
```

Khi trả `EmbeddingFunc`:

```diff
     elif embedding_provider == "ollama":
         return EmbeddingFunc(
-            embedding_dim=768,
+            embedding_dim=embedding_dim or 768,
             func=embedding_wrapper,
-            max_token_size=8192
+            max_token_size=embedding_max_tokens or 8192
         )
+    elif embedding_provider == "huggingface":
+        return EmbeddingFunc(
+            embedding_dim=embedding_dim or 768,
+            func=embedding_wrapper,
+            max_token_size=embedding_max_tokens or 8192
+        )
```

Nếu muốn dùng embedding server OpenAI-compatible thay vì HF native, cũng nên sửa `openai_embedding()` để nhận `model=embedding_model`, vì hiện tại đang hardcode `text-embedding-3-small`.

#### Diff 3: đọc config mới trong `create_temporal_graphrag_from_config()`

Pseudo-diff:

```diff
 embedding_provider = config.get('embedding_provider', provider)
+embedding_model = config.get('embedding_model')
+embedding_dim = config.get('embedding_dim')
+embedding_max_tokens = config.get('embedding_max_tokens')
+embedding_device = config.get('embedding_device', 'cpu')
+embedding_batch_size = config.get('embedding_batch_size', config.get('embedding_batch_num', 16))
+embedding_prefix = config.get('embedding_prefix', 'search_document: ')
```

và truyền xuống:

```diff
 embedding_func = create_embedding_function(
     embedding_provider=embedding_provider,
     api_key=embedding_api_key,
-    base_url=resolved_embedding_base_url
+    base_url=resolved_embedding_base_url,
+    embedding_model=embedding_model,
+    embedding_dim=embedding_dim,
+    embedding_max_tokens=embedding_max_tokens,
+    embedding_device=embedding_device,
+    embedding_batch_size=embedding_batch_size,
+    embedding_prefix=embedding_prefix,
 )
```

Với `embedding_provider == "huggingface"` thì không cần API key và không cần `embedding_base_url`.

#### Diff 4: thêm `huggingface_embedding()` trong `tgrag/src/llm/embedding.py`

Pseudo-code, chưa áp dụng:

```diff
+_HF_EMBEDDERS = {}
+
+def _get_hf_embedder(model: str, device: str, max_tokens: int):
+    key = (model, device, max_tokens)
+    if key not in _HF_EMBEDDERS:
+        from sentence_transformers import SentenceTransformer
+        st_model = SentenceTransformer(
+            model,
+            device=device,
+            trust_remote_code=True,
+        )
+        st_model.max_seq_length = max_tokens
+        _HF_EMBEDDERS[key] = st_model
+    return _HF_EMBEDDERS[key]
+
+async def huggingface_embedding(
+    texts: List[str],
+    model: str = "nomic-ai/nomic-embed-text-v1.5",
+    device: str = "cpu",
+    batch_size: int = 16,
+    max_tokens: int = 8192,
+    prefix: str = "search_document: ",
+) -> np.ndarray:
+    def _encode():
+        st_model = _get_hf_embedder(model, device, max_tokens)
+        prepared = [t if t.startswith(prefix) else prefix + t for t in texts]
+        return st_model.encode(
+            prepared,
+            batch_size=batch_size,
+            normalize_embeddings=True,
+            convert_to_numpy=True,
+            show_progress_bar=False,
+        )
+
+    return await asyncio.to_thread(_encode)
```

Cần import thêm `asyncio`. Với `nomic-ai/nomic-embed-text-v1.5`, `trust_remote_code=True` là điểm cần chú ý. Với `BAAI/bge-m3`, có thể dùng `sentence-transformers`; nếu muốn dense+sparse+multi-vector đúng nghĩa thì dùng `FlagEmbedding`, nhưng đó là thay đổi retrieval layer lớn hơn.

#### Diff 5: guard input length ở `vector_nanovectordb.py`

Đây là điểm bắt buộc để không lặp lại TH7 100. HF 8192 tokens tốt hơn Ollama 2K, nhưng vẫn cần guard vì entity description có thể phình quá dài.

Pseudo-diff:

```diff
-contents = [v["content"] for v in data.values()]
+raw_contents = [v["content"] for v in data.values()]
+max_chars = self.global_config.get("embedding_max_chars")
+contents = []
+truncated = 0
+max_len = 0
+for item, content in zip(list_data, raw_contents):
+    max_len = max(max_len, len(content))
+    if max_chars and len(content) > max_chars:
+        truncated += 1
+        logger.warning(
+            "Truncate embedding content namespace=%s id=%s len=%s max_chars=%s entity=%s",
+            self.namespace,
+            item.get("__id__"),
+            len(content),
+            max_chars,
+            item.get("entity_name"),
+        )
+        content = content[:max_chars]
+    contents.append(content)
+print(
+    f"[build-detail] embedding content lengths ({self.namespace}): "
+    f"items={len(contents)} max_chars={max_len} truncated={truncated}",
+    flush=True,
+)
```

Nếu muốn chuẩn hơn char truncate, dùng tokenizer theo embedding model để cắt token. Nhưng bước char guard vẫn nên có trước để tránh crash ngay.

#### Diff 6: giảm độ phình ngay tại `building.py`

Hiện tại entity vector payload:

```python
"content": dp["entity_name"] + " " + dp.get("description", "")
```

Nên đổi theo hướng có hàm helper:

```diff
+def _build_embedding_content(name: str, description: str, max_chars: Optional[int]) -> str:
+    content = f"{name} {description or ''}".strip()
+    if max_chars and len(content) > max_chars:
+        return content[:max_chars]
+    return content
```

và dùng:

```diff
-"content": dp["entity_name"] + " " + dp.get("description", ""),
+"content": _build_embedding_content(
+    dp["entity_name"],
+    dp.get("description", ""),
+    global_config.get("embedding_max_chars"),
+),
```

Tuy nhiên tôi vẫn ưu tiên guard ở `vector_nanovectordb.py` vì đó là điểm cuối trước khi gọi embedding. Guard ở `building.py` giúp graph/vector content sạch hơn, còn guard ở vector store giúp chống fail toàn cục.

#### Diff 7: cấu hình YAML/CLI sau khi patch

Config runtime hoặc CLI nên có đủ:

```yaml
embedding_provider: "huggingface"
embedding_model: "nomic-ai/nomic-embed-text-v1.5"
embedding_dim: 768
embedding_max_tokens: 7500
embedding_max_chars: 24000
embedding_device: "cpu"
embedding_batch_size: 16
embedding_prefix: "search_document: "
```

Lệnh TH7 sau khi patch:

```bash
python -u build_graph.py \
  --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_hf_nomic_p2c32knp4096_100docs \
  --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cpu \
  --embedding_batch_size 16 \
  --num_docs 100 \
  --llm_max_async 2 \
  --llm_timeout 900
```

Sau đó mới chạy lại 384. Không dùng chung output cũ vì vector dimension/model đã đổi.

#### Nếu muốn dùng `llama-cpp-turboquant` cho embedding thay vì HF native

`llama-server` có endpoint embedding nếu start với `--embedding`, nhưng nên tách server embedding riêng, ví dụ port `8090`, không dùng chung server chat Qwen3 14B Q5 ở port `8080`:

```text
port 8080: Qwen3 14B Q5 chat/completions, có TurboQuant KV, dùng cho LLM extraction/community.
port 8090: embedding model GGUF, start với --embedding, dùng cho /v1/embeddings.
```

Cách này vẫn cần patch source vì `openai_embedding()` hiện hardcode model/dim. Nếu mục tiêu của bạn là **cùng embedding model gốc trên HuggingFace** và tránh giới hạn Ollama, thì patch HF native trong repo là đường rõ nhất.

### 17.7 Chunking/sliding window hiện tại và nên chỉnh gì?

Source hiện tại đã có sliding/fixed token window ở bước chunk document:

```python
step_size = max(1, max_token_size_minus_title - overlap_token_size)
for start in range(0, len(tokens), step_size):
    chunk = title_tokens + tokens[start: start + max_token_size_minus_title]
```

Config hiện tại:

```yaml
chunk_size: 1200
chunk_overlap: 100
```

Với ECT-QA, Hugging Face preview cho thấy transcript cleaned_content khoảng 6.38k-32.5k chars và token_count khoảng 1.2k-5.88k. Vì vậy `chunk_size=1200`, `chunk_overlap=100` là hợp lý cho extraction local LLM. Không nên tăng mạnh chunk size ngay, vì Qwen3 14B Q5 TH7 đang có `n_ctx_seq=16384` mỗi slot và `--n-predict=4096`; chunk lớn hơn sẽ làm prompt dài hơn, chậm hơn và tăng nguy cơ community/report context lỗi.

Vấn đề cần thêm không phải document sliding window, mà là **embedding-content window sau merge**:

| Stage | Hiện tại | Nên chỉnh |
|---|---|---|
| Document chunking | 1200/100, đã có sliding window | Giữ 1000-1200, overlap 100-150 |
| Entity description merge | Có thể phình rất dài | Cap/summarize description sau merge |
| Entity/relation embedding | Gửi nguyên `content` | Truncate/log hoặc split window trước embedding |
| Temporal identity | Entity chung dễ gom nhiều quý | Embed thêm metadata thời gian/company/quarter hoặc tạo per-time vector |

Khuyến nghị cụ thể:

```text
chunk_size: 1000-1200
chunk_overlap: 100-150
embedding_max_chars:
  nomic-embed-text: 6000-8000 chars
  bge-m3: 16000-24000 chars, nhưng vẫn nên summarize/cap
  qwen3-embedding:4b: có thể dài hơn, nhưng không nên embed description vô hạn
entity_description_max_tokens_after_merge: 512-1024 tokens
relation_description_max_tokens_after_merge: 512-1024 tokens
```

Nếu muốn giữ đầy đủ thông tin dài, không nên nhét hết vào một vector. Nên tạo nhiều vector nhỏ hơn:

```text
ent-<entity>-summary                 # summary tổng hợp ngắn
ent-<entity>-<year>-<quarter>         # temporal slice
rel-<src>-<tgt>-<timestamp>           # relation theo thời gian
community-<id>-summary               # community report ngắn
```

Cách này giúp retrieval không bị “semantic blur”: cùng entity nhưng khác thời điểm vẫn tách được temporal neighborhood.

### 17.7.1 LLM extraction chunks: vì sao chậm và có nên tăng chunk size?

Source hiện tại chunk document ở `tgrag/src/temporal_graphrag.py` rồi gọi `get_chunks(...)` với:

```python
chunk_func=self.chunk_func,
overlap_token_size=self.chunk_overlap_token_size,
max_token_size=self.chunk_token_size,
```

Hàm chunking chính ở `tgrag/src/core/chunking.py` dùng sliding window theo token:

```python
step_size = max(1, max_token_size_minus_title - overlap_token_size)
for start in range(0, len(tokens), step_size):
    chunk = title_tokens + tokens[start: start + max_token_size_minus_title]
```

Với config hiện tại:

```yaml
chunk_size: 1200
chunk_overlap: 100
```

thì mỗi chunk là khoảng 1200 tokens, bước nhảy khoảng 1100 tokens. Log thực tế cho thấy:

```text
TH7 100 docs: 391 chunks
TH7 384 docs: 1462 chunks
TH1 50 docs: 199 chunks
```

Trong `extract_entities`, mỗi chunk không chỉ gọi LLM một lần. Source hiện tại làm:

```text
1. Gọi extraction prompt chính cho chunk.
2. Gọi continue/gleaning prompt theo entity_extract_max_gleaning.
3. Nếu response lỗi/quá ngắn/malformed, retry tối đa 3 attempt với prompt đơn giản hơn.
```

Vì `entity_extract_max_gleaning` mặc định là 1, một chunk bình thường có thể tạo ít nhất khoảng 2 request LLM. Do đó TH7 100 với 391 chunks có thể tương đương khoảng 782 request LLM trước khi tính retry. Đây là lý do stage `chunk LLM extraction + parsing` rất lâu.

Ở giai đoạn này build graph đang làm các việc sau:

```text
1. Đọc corpus và chia docs thành chunks.
2. Với từng chunk, gửi prompt extraction sang local LLM qua `llama-server`.
3. Parse response thành entity/relation.
4. Gleaning/continue để cố lấy thêm entity/relation còn thiếu.
5. Retry nếu response lỗi format hoặc quá ngắn.
6. Sau khi đủ chunks mới merge entity/relation và ghi vector store.
```

Nếu timeout hoặc dừng giữa chừng, kết quả dễ bị thiếu theo hai kiểu:

```text
- Thiếu chunk đã extract: một số chunk chưa kịp chạy hoặc response bị timeout.
- Output incomplete: cache có thể đã có một phần LLM response, nhưng graph/vector/community/GraphML chưa persist đủ.
```

Vì vậy với local LLM không nên chỉ nhìn `llm_timeout`. Timeout cao hơn giúp request dài không chết sớm, nhưng không sửa được lỗi prompt quá dài, output bị truncate, hoặc parser fail. Chỉ nên tăng `--llm_timeout` cùng lúc với log số chunk đã xử lý, số retry, số response malformed và trạng thái output cuối.

Câu hỏi “ít chunk lớn hơn có tốt hơn nhiều chunk nhỏ không?”: **có thể tốt hơn, nhưng chỉ tới một ngưỡng**.

| Hướng | Lợi ích | Rủi ro |
|---|---|---|
| Nhiều chunk nhỏ, ví dụ 1200/100 | Prompt ngắn, extraction dễ chính xác hơn, mỗi chunk fail mất ít dữ liệu | Rất nhiều request LLM, overhead cao, build lâu |
| Ít chunk lớn, ví dụ 2000-2400 tokens | Giảm số chunk và số request, có thể giảm trùng entity do overlap | Mỗi request lâu hơn, output nhiều hơn, dễ timeout/truncate/malformed, fail một chunk mất nhiều dữ liệu hơn |
| Chunk quá lớn, ví dụ 4000+ | Request ít hơn nhiều | Local 14B Q5 có thể chậm mạnh; output extraction có thể vượt `--n-predict`; parser dễ miss entity/relation; temporal separation kém hơn |

Đúng là mỗi chunk phải mang lại toàn bộ instruction/prompt extraction, nên nhiều chunk nhỏ tạo overhead prefill và overhead HTTP lớn. Nhưng với local LLM, thời gian không chỉ nằm ở prompt overhead. Phần decode output cũng rất lớn vì model phải sinh danh sách entity/relation. Khi chunk lớn hơn, output thường dài hơn, dễ gặp ba vấn đề:

```text
1. Request đơn lẻ lâu hơn nên sát timeout hơn.
2. Output dài hơn nên dễ bị cắt bởi --n-predict hoặc parser nhận response chưa đủ.
3. Một chunk lớn chứa nhiều sự kiện/quý/năm hơn, làm LLM dễ trộn temporal relation.
```

Vì vậy mục tiêu không phải biến `50 chunk x 15s` thành `5 chunk x 40s` bằng mọi giá. Mục tiêu đúng là tìm điểm cân bằng để giảm số request nhưng vẫn giữ extraction chính xác và relation theo thời gian không bị trộn.

Với GPU 16GB và Qwen3 14B Q5 p2/c32k, không nên nhảy thẳng từ 1200 lên 4000. Nên test theo lưới nhỏ:

```text
Baseline: chunk_size=1200, chunk_overlap=100
Test 1:   chunk_size=1600, chunk_overlap=120
Test 2:   chunk_size=2000, chunk_overlap=150
Test 3:   chunk_size=2400, chunk_overlap=200
```

Lệnh test chunk size, sau khi đã fix embedding guard:

```bash
for CS in 1600 2000 2400; do
  python -u build_graph.py \
    --output_dir outputs/build_graph/cmp_tq_turbo_14bq5_hf_nomic_cs${CS}_050docs \
    --model qwen3-14b-q5-ctkq8-ctvturbo3-c32k-p2-np4096 \
    --base_url http://localhost:8080/v1 \
    --corpus_path ect-qa/corpus/base.jsonl.gz \
    --local_llm_backend turboquant \
    --embedding_provider huggingface \
    --embedding_model nomic-ai/nomic-embed-text-v1.5 \
    --embedding_dim 768 \
    --embedding_max_tokens 7500 \
    --embedding_max_chars 24000 \
    --embedding_device cpu \
    --embedding_batch_size 16 \
    --chunk_size "$CS" \
    --chunk_overlap 150 \
    --num_docs 50 \
    --llm_max_async 2 \
    --llm_timeout 1200 \
    2>&1 | tee logs/build_graph/cmp_tq_turbo_14bq5_hf_nomic_cs${CS}_050docs.log
done
```

Tiêu chí chọn chunk size không chỉ là nhanh hơn:

```text
1. Số chunks giảm bao nhiêu.
2. chunk LLM extraction + parsing giảm bao nhiêu.
3. Số malformed/too short/retry có tăng không.
4. Entities/relations trên mỗi doc có tụt bất thường không.
5. Community report có tăng lỗi context không.
6. Embedding content max length sau merge có tăng hay giảm.
7. Output cuối có đủ vdb/community/GraphML không.
```

Khuyến nghị hiện tại:

```text
7B local TurboQuant: thử 1200 -> 1600 trước, không tăng quá mạnh vì 7B dễ miss extraction.
14B Q5 local TurboQuant: thử 1600/2000/2400 sau khi fix embedding. Nếu 2400 ổn và extraction quality không giảm, mới cân nhắc cao hơn.
Nếu request timeout: tăng --llm_timeout 1200 hoặc 1800, nhưng đừng dùng timeout để che lỗi prompt quá dài.
Nếu server context report lỗi: giảm --parallel về 1 để mỗi slot có context lớn hơn, hoặc giảm chunk/community prompt.
```

Nói ngắn gọn: tăng chunk size là hướng đáng test để giảm số request, nhưng điểm nghẽn của TH7 100 hiện không chỉ là số chunk. Sau extraction còn có merge description và embedding input length. Vì vậy phải fix embedding guard trước, rồi mới benchmark chunk size.

### 17.7.2 Merge entity/relation: xử lý description phình dài thế nào?

Source hiện tại merge entity trong `_merge_nodes_then_upsert()` bằng cách gom description trùng entity:

```python
description = GRAPH_FIELD_SEP.join(
    sorted(set([dp["description"] for dp in nodes_data] + already_description))
)
description = await _handle_entity_relation_summary(entity_name, description, global_config)
```

Cơ chế summary có tồn tại, nhưng chưa đủ an toàn:

```python
if len(tokens) < summary_max_tokens:
    return description
...
summary = await use_llm_func(use_prompt, max_tokens=summary_max_tokens)
if summary is None or len(summary) == 0:
    return description
except Exception:
    return description
```

Nghĩa là nếu summary fail, code quay về description gốc rất dài. Đây là lý do entity như `CHINA`, `2023`, `FREE CASH FLOW` có thể phình lớn khi chạy nhiều docs/quý/năm.

Với relation, source hiện tại có hai dạng:

```text
_merge_edges_then_upsert(): relation không temporal, join nhiều description thành một string.
_merge_temporal_edges_then_upsert(): relation temporal, description là dict theo timestamp.
```

Đoạn relation temporal quan trọng:

```python
already_description.update(dp['description'])
...
await knwoledge_graph_inst.upsert_edge(
    src_id,
    tgt_id,
    edge_data=dict(description=already_description, source_id=already_source_ids, order=order)
)
```

Sau đó relation vector payload đang tạo một vector cho từng timestamp:

```python
data_for_vdb_relation = {
    compute_mdhash_id(dp["src_id"]+'_'+dp["tgt_id"]+'_'+timestamp, prefix="rel-"): {
        "content": des,
        "entity_name": dp["src_id"]+'_'+dp["tgt_id"]+'_'+timestamp,
    }
    for dp in valid_relations_data for timestamp, des in dp.get('description', {}).items()
}
```

Điểm tốt: relation vector đã tách theo timestamp. Điểm chưa tốt: `des` vẫn có thể dài, và community report vẫn có thể kéo description dài vào prompt.

Hướng xử lý đúng:

| Layer | Entity | Relation |
|---|---|---|
| Graph node/edge | Giữ summary ngắn, có hard cap sau summary | Giữ description theo timestamp, mỗi timestamp có cap riêng |
| Vector content | Không embed toàn bộ raw description; embed summary + metadata | Embed `timestamp + src + tgt + short relation summary` |
| Evidence/raw text | Giữ trong `source_id` hoặc evidence store riêng | Giữ raw/chunk reference riêng, không nhét hết vào vector |
| Community report | Dùng summary đã cap | Dùng relation summary đã cap, không dùng raw long description |

Cấu trúc relation content nên là:

```text
timestamp: 2023-Q2
source: CROCS, INC.
target: ASIA
relation_summary: Asia revenue increased/decreased ...
evidence: chunk ids only, not full raw text
```

Không nên để relation vector chỉ là một đoạn description dài không có `src/tgt/timestamp`, vì temporal retrieval cần đủ ba tín hiệu:

```text
entity keyword + temporal timestamp + relation semantics
```

Với một relation giữa hai node, cách xử lý nên tách rõ ba phần thay vì nối tất cả description vào một chuỗi:

```text
1. Canonical relation summary: mô tả ngắn quan hệ chính giữa src và tgt.
2. Temporal slices: mỗi timestamp/quý/năm có một summary ngắn riêng.
3. Evidence references: giữ chunk/source_id để trace lại raw text, không nhét toàn bộ raw text vào vector.
```

Ví dụ với relation `CROCS, INC. -> ASIA`, không nên embed một description dài gom tất cả quý. Nên tạo nội dung vector kiểu:

```text
timestamp: 2023-Q2
source: CROCS, INC.
target: ASIA
relation: Asia revenue increased in Q2 2023 due to ...
evidence_source_id: chunk-...
```

Nếu một relation có nhiều timestamp thì mỗi timestamp là một vector hoặc một record riêng. Khi query hỏi theo thời gian, retrieval sẽ dễ kéo đúng temporal neighborhood hơn. Nếu merge tất cả vào một description dài, embedding space sẽ gần với entity chung nhưng yếu ở phân biệt thời điểm, đây là lỗi rất nguy hiểm với ECT-QA.

Pseudo-diff hard cap sau summary:

```diff
+def _hard_cap_text(text: str, max_chars: int | None) -> str:
+    if not text or not max_chars:
+        return text or ""
+    return text if len(text) <= max_chars else text[:max_chars]
```

Trong `_merge_nodes_then_upsert()`:

```diff
 description = await _handle_entity_relation_summary(
     entity_name, description, global_config
 )
+description = _hard_cap_text(
+    description,
+    global_config.get("entity_description_max_chars_after_merge", 6000),
+)
```

Trong `_merge_temporal_edges_then_upsert()`:

```diff
 for dp in edges_data:
     already_description.update(dp['description'])
     already_source_ids.update(dp['source_id'])
+
+relation_max_chars = global_config.get("relation_description_max_chars_after_merge", 4000)
+already_description = {
+    ts: _hard_cap_text(desc, relation_max_chars)
+    for ts, desc in already_description.items()
+}
```

Trong relation vector payload:

```diff
 "content": des,
+"content": f"timestamp: {timestamp}
source: {dp['src_id']}
target: {dp['tgt_id']}
relation: {des}",
```

và vẫn cần cap trong `vector_nanovectordb.py` trước embedding để tránh crash nếu một chỗ nào đó lọt content dài.

Config đề xuất:

```yaml
entity_summary_to_max_tokens: 500
entity_description_max_chars_after_merge: 6000
relation_description_max_chars_after_merge: 4000
embedding_max_chars: 24000       # HF/BGE-M3 có thể cao hơn; nomic Ollama nên thấp hơn
community_edge_description_max_chars: 2000
community_node_description_max_chars: 2000
```

Với Temporal GraphRAG, hướng tốt hơn nữa là tách vector theo temporal slice:

```text
ent-CHINA-summary                  # node canonical ngắn
ent-CHINA-2023-Q2                  # vector theo quý
ent-FREE_CASH_FLOW-2022-Q4         # vector theo metric + thời gian
rel-CROCS-ASIA-2023-Q2             # relation theo timestamp
```

Cách này giải quyết đúng bản chất ECT-QA: cùng entity nhưng khác thời điểm phải gần nhau về entity lineage, nhưng không được merge thành một vector mơ hồ làm mất temporal distinction.

### 17.8 Fine-tune có cần không?

Chưa nên fine-tune ngay. Trình tự đúng hơn:

1. Sửa source cho phép chọn embedding model và cap/truncate content.
2. Benchmark `nomic`, `bge-m3`, `qwen3-embedding:0.6b`, `qwen3-embedding:4b` trên cùng 50/100 docs.
3. Đánh giá retrieval trước answer: seed node hit, temporal edge hit, supporting chunk hit, community relevance.
4. Chỉ fine-tune khi đã có ground-truth mapping question -> supporting chunks/nodes/edges.

ECT-QA có câu hỏi và corpus đủ tốt để làm evaluation, nhưng fine-tune embedding cần positive/negative pairs rõ ràng. Nếu chưa có annotation supporting evidence, fine-tune dễ làm overfit và khó biết lỗi do embedding hay do graph extraction.

### 17.9 Hướng chạy ổn định nên chọn

Với mục tiêu hiện tại là **local LLM + TurboQuant + full ECT-QA 384 docs**, hướng nên chọn:

```text
Folder chính: /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
LLM: Qwen3 14B Q5 qua llama-server TurboQuant
Server: -c 32768 --parallel 2 --n-predict 4096 -ctk q8_0 -ctv turbo3
Build: --llm_max_async 2 --llm_timeout 900
Chunk: 1200/100 hoặc 1000/100 nếu muốn giảm prompt dài
Embedding phase 1: bge-m3 dense qua Ollama, sau khi patch embedding_model/dim
Embedding guard: cap/log content trước embedding bắt buộc
Full hybrid phase 2: thêm BM25/sparse hoặc BGE-M3 sparse/multi-vector nếu cần cải thiện retrieval quality
```

Nếu chưa patch source embedding, cấu hình ổn định nhất vẫn là:

```text
Chạy local LLM tới 50 docs để benchmark TurboQuant.
Không chạy 100/384 local với nomic mặc định nếu chưa cap/truncate embedding content.
```

Nguồn web đã đối chiếu:

- ECT-QA Hugging Face: https://huggingface.co/datasets/austinmyc/ECT-QA
- BGE-M3 docs: https://bge-model.com/bge/bge_m3.html
- Ollama bge-m3: https://ollama.com/library/bge-m3
- Ollama nomic-embed-text: https://ollama.com/library/nomic-embed-text
- Ollama embeddings docs: https://docs.ollama.com/capabilities/embeddings
- Qwen3-Embedding-4B model card: https://huggingface.co/Qwen/Qwen3-Embedding-4B
- Ollama qwen3-embedding: https://ollama.com/library/qwen3-embedding

## 20. Ghi chú từ tài liệu web

### 10.1 llama-server và context/parallel

Tài liệu `llama.cpp` server mô tả `llama-server` hỗ trợ OpenAI-compatible chat completions, parallel decoding và continuous batching. Các tham số quan trọng gồm:

- `-c` hoặc `--ctx-size`: kích thước prompt context.
- `-n` hoặc `--n-predict`: số token sinh ra.
- `-fa` hoặc `--flash-attn`: bật flash attention.
- `-ctk` hoặc `--cache-type-k`: kiểu KV cache cho K.
- `-ctv` hoặc `--cache-type-v`: kiểu KV cache cho V.
- `-ngl` hoặc `--n-gpu-layers`: số layer offload lên GPU.

Điều quan trọng với benchmark này: log server mới là nguồn xác nhận context thực tế theo slot. Với TH1/TH2, dù CLI ghi `-c 65536`, log cho thấy slot context chỉ khoảng 16384 khi chạy `--parallel 4`.

Nguồn: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md

### 10.2 TurboQuant: nén KV cache, không phải đổi model GGUF

TurboQuant là kiểu nén KV cache được thêm vào llama.cpp, dùng cache type như `turbo3`/`turbo4` cho K/V.

Điểm cần hiểu:

- Model GGUF vẫn là model Q8/Q5/Q4 bình thường.
- TurboQuant áp dụng lên KV cache lúc inference qua `-ctk` và `-ctv`.
- K precision ảnh hưởng attention routing nhiều hơn V, nên cấu hình an toàn thường giữ K cao hơn, ví dụ `-ctk q8_0 -ctv turbo3` hoặc `turbo4`.
- Cấu hình symmetric `-ctk turbo3 -ctv turbo3` tiết kiệm hơn nhưng cần tự validate chất lượng.

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

### 10.3 Ollama embedding và lỗi context

Tài liệu Ollama API mới khuyến nghị endpoint `/api/embed`. Endpoint này có tham số `truncate`, mặc định là true, dùng để cắt input vượt context window. Nếu `truncate=false` thì trả lỗi.

Repo hiện tại đang gọi endpoint legacy `/api/embeddings` bằng payload `model + prompt`. Khi input quá dài, Ollama trả lỗi context như TH11A 384.

Trang model Ollama của `nomic-embed-text` ghi context window là 2K trong Ollama library. Vì vậy entity description dài hàng chục nghìn ký tự có rủi ro vượt context rất cao.

Nguồn:

- https://docs.ollama.com/api/embed
- https://ollama.com/library/nomic-embed-text

Cách xử lý trong code:

- Truncate nội dung trước khi gọi embedding.
- Đổi sang `/api/embed` và truyền `truncate=true` nếu chấp nhận cắt âm thầm.
- Tốt nhất là vừa giới hạn description ở graph layer, vừa log các content quá dài.

### 10.4 GraphRAG indexing vốn tốn LLM và dễ sinh prompt dài

Tài liệu Microsoft GraphRAG mô tả pipeline indexing gồm entity extraction, relationship extraction, community detection, community summaries/reports và embeddings. Standard GraphRAG dùng LLM cho entity extraction, relationship extraction, summarization và community reports.

Điều này khớp với log ở đây:

- Thời gian chủ yếu nằm ở LLM extraction và community reports.
- Community report prompt dễ dài vì gom nhiều entity/relationship descriptions.
- Embedding fail có thể xảy ra nếu entity/relation description hoặc community content vượt context embedding.

Nguồn:

- https://microsoft.github.io/graphrag/index/overview/
- https://microsoft.github.io/graphrag/index/methods/
- https://microsoft.github.io/graphrag/config/yaml/

## 21. Nguồn tham khảo web

- llama.cpp server README: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- TurboQuant plus repo: https://github.com/TheTom/turboquant_plus
- TurboQuant asymmetric KV compression notes: https://github.com/TheTom/turboquant_plus/blob/main/docs/papers/asymmetric-kv-compression.md
- llama.cpp TurboQuant discussion: https://github.com/ggml-org/llama.cpp/discussions/20969
- Ollama embed API: https://docs.ollama.com/api/embed
- Ollama nomic-embed-text model page: https://ollama.com/library/nomic-embed-text
- Microsoft GraphRAG indexing overview: https://microsoft.github.io/graphrag/index/overview/
- Microsoft GraphRAG methods: https://microsoft.github.io/graphrag/index/methods/
- Microsoft GraphRAG detailed config: https://microsoft.github.io/graphrag/config/yaml/

- Ollama bge-m3 model page: https://ollama.com/library/bge-m3
- Ollama qwen3-embedding model page: https://ollama.com/library/qwen3-embedding
- Ollama embeddings capability docs: https://docs.ollama.com/capabilities/embeddings
- Ollama context length docs: https://docs.ollama.com/context-length
- Ollama FAQ context window: https://docs.ollama.com/faq
- Nomic nomic-embed-text-v1.5 Hugging Face: https://huggingface.co/nomic-ai/nomic-embed-text-v1.5
- BAAI bge-m3 Hugging Face: https://huggingface.co/BAAI/bge-m3
- ECT-QA Hugging Face dataset: https://huggingface.co/datasets/austinmyc/ECT-QA
- TG-RAG arXiv paper: https://arxiv.org/abs/2510.13590
- Temporal-GraphRAG GitHub: https://github.com/hanjiale/Temporal-GraphRAG
- DeepWiki ECT-QA benchmark dataset: https://deepwiki.com/hanjiale/Temporal-GraphRAG/8-ect-qa-benchmark-dataset
