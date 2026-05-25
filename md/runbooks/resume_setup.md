# Resume Setup Cho Build Graph Local LLM + TurboQuant

Tài liệu này phân tích cơ chế resume cho giai đoạn **build graph** của `Temporal-GraphRAG-Turboquant`, trong bối cảnh chạy:

- Local LLM qua `llama-server` TurboQuant.
- Local embedding qua HuggingFace hoặc Ollama.
- Dataset ECT-QA `base.jsonl.gz` khoảng 384 docs.
- Mục tiêu thực tế: nếu build lỗi ở 50/100/384 docs thì lần sau có thể chạy tiếp, tránh mất hàng giờ LLM extraction.

Tài liệu này **chưa sửa code**. Phần code bên dưới là diff minh họa để biết cần chỉnh file nào, chỉnh ở đâu, và mức độ thay đổi ra sao.

---

## 1. Kết Luận Nhanh

Source hiện tại có resume rất hạn chế:

| Mức resume | Hiện có chưa | Ý nghĩa thực tế |
|---|---:|---|
| Skip document đã build xong | Có, nhưng chỉ sau khi run pass hoàn toàn | Dựa vào `kv_store_full_docs.json`; nếu run lỗi trước bước cuối thì không có doc nào được đánh dấu xong |
| Skip chunk đã build xong | Có, nhưng chỉ sau khi run pass hoàn toàn | Dựa vào `kv_store_text_chunks.json`; cũng chỉ ghi sau community report |
| Cache LLM response giữa chừng | Có | `kv_store_llm_response_cache.json` được ghi sau từng LLM call nên rerun có thể đỡ gọi lại LLM, nhưng không phải resume có kiểm soát theo chunk |
| Resume đúng doc range 50 -> 100 -> 384 | Chưa có CLI rõ | `--num_docs` luôn lấy từ đầu corpus, không có `--doc_start`/`--doc_end` |
| Resume chunk extraction sau crash | Chưa có | Source đang `asyncio.gather` toàn bộ chunks, kết quả structured chỉ nằm trong RAM tới khi merge/upsert xong |
| Rebuild community-only | Chưa có | Nếu mọi docs đã tồn tại, `ainsert()` return sớm nên không có cách chỉ rebuild community reports |
| Resume vector upsert/entity embedding | Chưa có | Nếu fail ở embedding, output có thể còn rỗng dù LLM extraction đã chạy nhiều giờ |

Vì vậy, cơ chế nên làm theo 2 tầng:

1. **Tầng an toàn tối thiểu:** thêm `--doc_start`, `--doc_end`, `--resume_manifest`; chạy theo batch 50/100/384 vào cùng `output_dir`.
2. **Tầng thật sự tiết kiệm thời gian:** thêm checkpoint theo chunk extraction để lỗi ở embedding/community không bắt gọi lại toàn bộ LLM extraction.

---

## 2. Kết Quả Log Hiện Tại Cần Nhớ

### 2.1 HF Nomic 7B mới chỉ có 1/5/10 docs

Các log hiện có:

```text
logs/build_graph/cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_001docs.log
logs/build_graph/cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_005docs.log
logs/build_graph/cmp_tq_turbo_7b_p2c64knp3072_hf_nomic_010docs.log
```

Kết quả output đã kiểm:

| Run | Docs | Chunks | Entities VDB | Relations VDB | Communities | Community error | Embedding error | Tổng thời gian |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| HF 001 | 1 | 5 | 82 | 81 | 2 | 0 | 0 | 131.58s |
| HF 005 | 5 | 19 | 268 | 325 | 11 | 0 | 0 | 598.84s |
| HF 010 | 10 | 39 | 519 | 603 | 22 | 0 | 0 | 1118.82s |

Điều này cho thấy patch HuggingFace embedding đang đi đúng hướng:

- Không còn `Ollama embedding API error`.
- Không có `Truncate embedding content` ở 1/5/10 docs.
- Không có community error ở 1/5/10 docs.
- Server log `llama-server` có `n_ctx_slot = 32768`, `truncated = 0`.

Tuy nhiên chưa có log HF cho 50/100/384 docs, nên chưa thể kết luận full 384 đã ổn.

### 2.2 So với TH cũ dùng Ollama embedding / p4

Các lỗi quan trọng đã có bằng chứng:

| Run cũ | Kết quả | Vấn đề chính |
|---|---|---|
| `cmp_tq_turbo_7b_p4c64knp4096_050docs` | pass nhưng community reports có 14 error reports | Server p4 chia `-c 65536` thành 4 slot, mỗi slot chỉ khoảng 16K context; nhiều community prompt vượt 16K |
| `cmp_tq_turbo_7b_p4c64knp4096_100docs` | incomplete | Log dừng trong extraction; không có kết thúc build sạch |
| `cmp_tq_turbo_14bq5_p2c32knp4096_100docs` | fail | Lỗi thật ở `entity_vdb.upsert` -> Ollama embedding input quá dài |
| `cmp_tq_turbo_14bq5_p2c32knp4096_384docs` | incomplete/chưa pass | Log cho thấy đang xử lý extraction, chưa có `Graph building completed successfully` |

Ví dụ lỗi embedding 14B 100 docs:

```text
Ollama embedding API error 500: {"error":"the input length exceeds the context length"}

extract_entities
-> entity_vdb.upsert(data_for_vdb)
-> vector_nanovectordb.py
-> ollama_embedding(...)
```

Điểm nguy hiểm: trong output `cmp_tq_turbo_14bq5_p2c32knp4096_100docs`, các file chính đếm ra:

```text
docs=0
chunks=0
communities=0
entities=0
relations=0
```

Nghĩa là LLM extraction đã chạy rất lâu, nhưng vì fail trước bước cuối nên `full_docs/text_chunks` chưa được đánh dấu xong. Rerun theo source hiện tại sẽ không biết đã xử lý đến đâu.

---

## 3. Build Graph Hiện Tại Chạy Qua Những Giai Đoạn Nào

Luồng chính nằm ở:

```text
build_graph.py
-> create_temporal_graphrag_from_config(...)
-> TemporalGraphRAG.insert(...)
-> TemporalGraphRAG.ainsert(...)
-> extract_entities(...)
-> building_temporal_hierarchy(...)
-> generate_temporal_report(...)
-> full_docs/text_chunks upsert
-> _insert_done persist all storages
```

### 3.1 Load documents

Hiện tại `build_graph.py` chỉ có:

```python
def load_documents_from_corpus(corpus_path: Path, num_docs: int = 3) -> List[Dict]:
    ...
    with gzip.open(corpus_path, 'rt', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= num_docs:
                break
            doc = json.loads(line)
            documents.append(doc)
```

Vấn đề:

- `--num_docs 100` luôn load docs `0..99`.
- Không có cách chỉ load docs `50..99`.
- Nếu muốn chạy theo batch thật sự, cần thêm `--doc_start` và `--doc_end`.

### 3.2 Dedup docs/chunks

Trong `TemporalGraphRAG.ainsert()`:

```python
new_doc_dicts = {
    compute_mdhash_id(c['doc'].strip(), prefix="doc-"): {
        "doc": c['doc'].strip(),
        "title": c['title'].strip()
    }
    for c in dict_or_dicts
}
_add_doc_keys = await self.full_docs.filter_keys(list(new_doc_dicts.keys()))
new_doc_dicts = {k: v for k, v in new_doc_dicts.items() if k in _add_doc_keys}
```

Sau đó chunk cũng dedup:

```python
_add_chunk_keys = await self.text_chunks.filter_keys(list(inserting_chunks.keys()))
inserting_chunks = {
    k: v for k, v in inserting_chunks.items() if k in _add_chunk_keys
}
```

Điểm tốt:

- Nếu run trước đã pass và ghi `kv_store_full_docs.json`, rerun cùng `output_dir` sẽ skip docs cũ.

Điểm yếu:

- `full_docs` và `text_chunks` chỉ được upsert ở cuối:

```python
await self.full_docs.upsert(new_doc_dicts)
await self.text_chunks.upsert(inserting_chunks)
```

Đoạn này nằm **sau** entity extraction, vector embedding, temporal hierarchy và community reports. Nếu fail ở embedding hoặc community, docs/chunks chưa được đánh dấu xong.

### 3.3 Chunk LLM extraction

Trong `extract_entities()`:

```python
results = await asyncio.gather(
    *[_process_single_content(c) for c in ordered_chunks]
)
```

Vấn đề:

- Tất cả chunk extraction chạy trong một `gather`.
- Kết quả parse entity/relation của từng chunk chỉ nằm trong RAM.
- Không có file `chunk_extractions` để biết chunk nào đã extract xong.
- Nếu fail ở embedding sau đó, structured extraction không được giữ lại.

Điểm còn cứu được:

- LLM response cache có thể ghi từng request trong `completion.py`:

```python
await hashing_kv.upsert(
    {args_hash: {"return": response_text, "model": model, "usage": usage}}
)
await hashing_kv.index_done_callback()
```

Nghĩa là rerun có thể cache hit cho các prompt đã gọi thành công. Nhưng đây chỉ là cache prompt-level, không phải resume chunk-level có manifest.

### 3.4 Entity/relation merge và embedding

Sau extraction, source gom entity/relation, merge vào graph, rồi tạo payload embedding:

```python
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

Lỗi 100/384 với Ollama embedding nằm ở đây:

- Entity như `CHINA`, `2023`, `FREE CASH FLOW` có description bị gom từ nhiều chunks/quý/năm.
- `content` gửi nguyên vào embedding.
- Ollama `nomic-embed-text` có context thấp hơn HF model gốc, nên fail `input length exceeds the context length`.

HF Nomic hiện đã có guard:

```text
embedding_max_chars=24000
embedding_max_tokens=7500
```

Nhưng full 384 vẫn cần kiểm vì description có thể vượt 24K chars và bị truncate.

### 3.5 Community report

Community report hiện chạy sau vector upsert:

```python
await generate_temporal_report(
    self.community_reports,
    knowledge_graph_inst=self.chunk_entity_relation_graph,
    temporal_hierarchy_graph_inst=self.temporal_hierarchy_graph,
    global_config=asdict(self)
)
```

Trong `generate_temporal_report()`, nếu LLM fail 3 lần thì source không raise, mà tạo error report:

```python
return {
    "title": f"Error Report for {community.get('name', 'Unknown')}",
    "summary": f"Failed to generate report: {str(e)}",
    "rating": 0.0,
    "rating_explanation": "Report generation failed",
    "findings": []
}
```

Vì vậy một run có thể `Graph building completed successfully`, nhưng community đã bị hỏng một phần. Đây là lý do phải kiểm `kv_store_community_reports.json`, không chỉ nhìn dòng pass.


### 3.6 Vì sao nhìn `output_dir` hiện tại vẫn rất khó resume

Một thư mục `outputs/build_graph/{output_dir}` hiện có thể chứa đồng thời:

- `kv_store_llm_response_cache.json`
- `kv_store_full_docs.json`
- `kv_store_text_chunks.json`
- `vdb_entities.json`
- `vdb_relations.json`
- `graph_chunk_entity_relation.graphml`
- `graph_temporal_hierarchy.graphml`
- `kv_store_community_reports.json`

Nhìn bên ngoài thì tưởng đủ để suy ra stage nào đã xong, nhưng thực tế không đơn giản vì các file này **không cùng một mức độ authoritative**.

Phân loại đúng nên là:

| File | Có ý nghĩa gì | Có dùng làm mốc resume chắc chắn được không |
|---|---|---|
| `kv_store_llm_response_cache.json` | Chứng minh một số prompt LLM đã gọi thành công | Không đủ. Chỉ là cache prompt-level, không biết đã merge thành chunk/entity/relation chưa |
| `kv_store_full_docs.json` | Chứng minh doc đã pass toàn pipeline tới cuối và đã persist | Có, nhưng chỉ cho doc-level skip sau khi run pass tới cuối |
| `kv_store_text_chunks.json` | Chứng minh chunk đã pass pipeline tới cuối và đã persist | Có, nhưng cũng chỉ sau khi run pass tới cuối |
| `graph_chunk_entity_relation.graphml` | Có graph tạm trong lúc build | Không. Có thể đã được ghi ra trước khi vector/community hoàn tất |
| `graph_temporal_hierarchy.graphml` | Có hierarchy graph tạm | Không. Có thể là snapshot giữa chừng |
| `vdb_entities.json`, `vdb_relations.json` | Có vector DB đã persist | Không hẳn. Có file nhưng `data` vẫn có thể rỗng hoặc chưa đồng bộ với graph |
| `kv_store_community_reports.json` | Có community reports đã persist | Chỉ dùng được nếu kiểm thêm nội dung report; file tồn tại chưa chắc report hợp lệ |

Điểm mấu chốt:

- `full_docs` và `text_chunks` mới là mốc mạnh nhất để biết một doc/chunk đã hoàn tất end-to-end.
- `llm_response_cache` chỉ cho biết request-level progress, không cho biết graph-level progress.
- `graphml` và `vdb_*.json` ở source hiện tại có thể là sản phẩm giữa chừng, không nên xem là checkpoint tin cậy để resume.

### 3.7 Nếu run dừng giữa chừng thì có nên xóa "chunk cũ" hay không

Với source hiện tại, **không nên xóa thủ công từng chunk** hoặc cố giữ một phần graph/vector rồi xóa phần khác, vì chưa có metadata nối ngược:

- chunk nào đã extract xong
- chunk nào đã merge vào entity/relation graph
- entity nào sinh từ những chunk nào
- vector nào đã upsert xong theo batch nào

Hiện tại source không có bảng như:

```text
chunk_id -> extraction_done -> merged_into_graph -> embedded_into_vdb -> community_done
```

Nên nếu tự xóa "một ít chunk cũ", trạng thái output rất dễ thành:

- graph còn node/edge nhưng text chunk đã mất
- vector DB còn embedding nhưng entity merge đã khác
- community report đang dựa trên graph cũ

Nguyên tắc an toàn hiện tại nên là:

| Trạng thái output_dir | Nên làm gì |
|---|---|
| Chỉ có `kv_store_llm_response_cache.json`, còn `full_docs/text_chunks/community/vdb/graphml` đều thiếu hoặc rỗng | Giữ cache, rerun lại. Đây là trạng thái "mới chỉ có prompt cache" |
| Có `graphml` nhưng `full_docs/text_chunks` vẫn rỗng | Không tin `graphml` đó là output hoàn chỉnh. Giữ cache, còn graph/vector/community tạm nên coi là rác trung gian |
| Có `full_docs` + `text_chunks` + `vdb` + `graphml` + `community` và counts hợp lý | Coi là run pass hoàn chỉnh |
| Có `full_docs/text_chunks` rồi nhưng community có nhiều error report | Không xóa docs/chunks. Chỉ nên rebuild community sau khi có mode `community-only` |

Vì vậy ở thiết kế resume, mục tiêu không phải là "xóa chunk cũ cho khéo", mà là:

1. Biết chunk nào đã hoàn tất bằng checkpoint riêng.
2. Chỉ skip chunk đã checkpoint.
3. Chỉ rebuild đúng stage bị fail.
4. Tránh yêu cầu người chạy phải xóa tay các file trong `output_dir`.

---

## 4. Vì Sao Cần Resume Cho 50/100/384 Docs

ECT-QA `base.jsonl.gz` là workload dài:

- 384 docs earnings call transcript.
- Khoảng 1462 chunks với `chunk_size=1200`, `chunk_overlap=100`.
- Local LLM extraction là bottleneck lớn nhất.
- Entity/relation description phình theo số docs.
- Community prompts càng về cuối càng dài.

Ở log HF 7B mới:

| Docs | Chunks | Chunk LLM extraction | Community report | Tổng |
|---:|---:|---:|---:|---:|
| 1 | 5 | 83.42s | 28.81s | 131.58s |
| 5 | 19 | 482.10s | 86.25s | 598.84s |
| 10 | 39 | 921.16s | 138.43s | 1118.82s |

Nếu scale tuyến tính thô:

- 50 docs khoảng 199 chunks.
- 100 docs khoảng 391 chunks.
- 384 docs khoảng 1462 chunks.

Nếu lỗi ở phút cuối của 100/384 mà không có checkpoint, chi phí chạy lại rất lớn.

---

## 5. Resume Hiện Tại Có Thể Dùng Ngay Không Cần Sửa Code

Có một workaround, nhưng chỉ dùng được khi mỗi bước trước đó **pass hoàn toàn**.

Ý tưởng:

1. Dùng **cùng một `output_dir`**.
2. Chạy tăng dần `--num_docs`: 50 -> 100 -> 384.
3. Nếu 50 pass, `kv_store_full_docs.json` có 50 docs.
4. Khi chạy `--num_docs 100`, source load docs 0..99 nhưng skip 50 docs đầu vì đã có trong `full_docs`.
5. Source chỉ build 50 docs mới.

Lệnh mẫu hiện tại:

```bash
RUN_DIR=outputs/build_graph/tq_7b_hf_nomic_resume_base384

for D in 50 100 384; do
  L=$(printf "%03ddocs" "$D")
  export TG_RAG_USAGE_LOG=results/usage/tq_7b_hf_nomic_resume_${L}.jsonl

  python -u build_graph.py \
    --output_dir "${RUN_DIR}" \
    --model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
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
    --embedding_batch_num 16 \
    --embedding_max_async 1 \
    --embedding_prefix "search_document: " \
    --chunk_size 1200 \
    --chunk_overlap 100 \
    --num_docs "$D" \
    --llm_max_async 2 \
    --llm_timeout 900 \
    2>&1 | tee logs/build_graph/tq_7b_hf_nomic_resume_${L}.log
done
```

Hạn chế của workaround này:

- Nếu 50 fail trước `full_docs/text_chunks upsert`, chạy lại 50 vẫn phải làm lại.
- Nếu 100 fail ở embedding, run sau không biết đã extract xong bao nhiêu chunks.
- Community reports sẽ bị drop/rebuild mỗi lần nếu `enable_incremental=false`.
- Không kiểm soát được range docs chính xác, vì `--num_docs` luôn lấy từ đầu.

Do đó workaround chỉ nên dùng để test nhanh. Với 384 docs local LLM, nên thêm resume thật.

---

## 6. Thiết Kế Resume Đề Xuất

### 6.1 Level 1: Doc-range resume

Mục tiêu:

- Cho phép chạy đúng range:
  - `0..50`
  - `50..100`
  - `100..384`
- Ghi manifest biết range nào đã pass.
- Không thay đổi logic graph chính.

CLI đề xuất:

```text
--doc_start 0
--doc_end 50
--resume_manifest outputs/build_graph/.../resume_manifest.json
--resume_mode doc-range
```

Manifest đề xuất:

```json
{
  "corpus_path": "ect-qa/corpus/base.jsonl.gz",
  "output_dir": "outputs/build_graph/tq_7b_hf_nomic_resume_base384",
  "chunk_size": 1200,
  "chunk_overlap": 100,
  "embedding_provider": "huggingface",
  "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
  "ranges": [
    {
      "doc_start": 0,
      "doc_end": 50,
      "status": "completed",
      "docs_loaded": 50,
      "completed_at": "..."
    }
  ]
}
```

Level này không cứu được nếu fail giữa một range, nhưng giúp tổ chức run 50/100/384 rõ ràng hơn và tránh nhầm output folder.

### 6.2 Level 2: Chunk extraction checkpoint

Mục tiêu:

- Nếu fail ở embedding/community sau khi đã extract xong chunks, rerun không gọi LLM extraction lại.
- Lưu structured extraction theo `chunk_id`.

File đề xuất:

```text
kv_store_chunk_extractions.json
```

Key nên gồm:

```text
chunk_id + model + prompt_version + chunk_content_hash
```

Value nên gồm:

```json
{
  "chunk_id": "chunk-...",
  "model": "qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072",
  "prompt_name": "temporal_entity_extraction_new",
  "content_hash": "md5...",
  "nodes": {...},
  "edges": {...},
  "raw_response_chars": 12345,
  "created_at": "..."
}
```

Level này là quan trọng nhất cho 100/384 docs.

### 6.3 Level 3: Community rebuild-only

Mục tiêu:

- Cho phép build graph/vector theo nhiều batch.
- Community report chỉ rebuild ở cuối.

CLI đề xuất:

```text
--disable_community_summary
--rebuild_communities_only
--preserve_communities
```

Lý do cần mode riêng:

- Nếu mọi docs đã có trong `full_docs`, `ainsert()` hiện return sớm:

```python
if not len(new_doc_dicts):
    logger.warning(f"All docs are already in the storage")
    return
```

Vì vậy không thể dùng source hiện tại để chỉ rebuild community trên graph đã có.

### 6.4 Level 4: Vector upsert checkpoint

Chưa cần làm ngay nếu đã có HF embedding + `embedding_max_chars`, nhưng nên ghi trong kế hoạch.

Vấn đề:

- `entity_vdb.upsert()` hiện embed toàn bộ batches bằng `asyncio.gather`.
- Nếu fail giữa embedding, phần đã embed có thể chưa persist.
- Output vector chỉ ghi khi `_insert_done()` gọi `index_done_callback`.

Nếu 384 vẫn hay fail ở vector, cần thêm:

- Ghi vector theo batch.
- Skip item đã có embedding.
- Persist sau mỗi N batches.


### 6.5 Ma trận quyết định theo trạng thái `output_dir`

Đây là phần quan trọng nhất khi vận hành thực tế, vì mỗi lần fail bạn cần quyết định:

- giữ nguyên thư mục cũ rồi rerun
- giữ cache nhưng bỏ phần graph/vector/community tạm
- hay chuyển sang `output_dir` mới

Ma trận an toàn nên là:

| Dấu hiệu trong `output_dir` | Giai đoạn nhiều khả năng đã tới | Có nên tin output hiện tại không | Cách resume hợp lý |
|---|---|---|---|
| Chỉ có `kv_store_llm_response_cache.json` | Đã gọi một phần LLM extraction | Không | Giữ cache, rerun cùng config; sau khi có `chunk_extraction_cache` thì resume sẽ rõ ràng hơn |
| Có `graph_chunk_entity_relation.graphml` nhưng `full_docs=0`, `text_chunks=0`, `vdb.data=0` | Đã merge graph trong RAM/ghi snapshot, nhưng fail trước persist cuối | Không | Không dùng graph này làm output chuẩn; nên rebuild từ extraction cache hoặc LLM cache |
| `full_docs > 0`, `text_chunks > 0`, `vdb.data > 0`, `community` thiếu | Đã pass extraction + vector, fail ở community/persist community | Tạm tin phần docs/chunks/vector, nhưng chưa tin cộng đồng | Cần `community-only rebuild` thay vì rerun cả extraction |
| `full_docs > 0`, `text_chunks > 0`, `community` có nhiều `"Error Report"` | Run pass kỹ thuật nhưng fail chất lượng community | Tin docs/chunks/vector, không tin community | Giữ nguyên graph/vector, đổi profile server rồi rebuild community-only |
| Tất cả file đều đủ, counts đúng, community error = 0 | Pass toàn pipeline | Có | Dùng làm base cho range tiếp theo hoặc eval |

Trong thiết kế code mới, quyết định resume nên được lấy từ:

1. `resume_manifest.json`
2. `kv_store_chunk_extractions.json`
3. counts của `full_docs/text_chunks/community/vdb`
4. log stage cuối cùng bị fail

chứ không nên dựa vào việc người dùng tự nhìn vài file rồi xóa tay.

---

## 7. File Cần Chỉnh Và Diff Minh Họa

### 7.1 `build_graph.py`: thêm doc_start/doc_end

Code cũ:

```python
def load_documents_from_corpus(corpus_path: Path, num_docs: int = 3) -> List[Dict]:
    documents = []
    with gzip.open(corpus_path, 'rt', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= num_docs:
                break
            doc = json.loads(line)
            documents.append(doc)
    print(f"✅ Loaded {len(documents)} documents from corpus")
    return documents
```

Diff đề xuất:

```diff
-def load_documents_from_corpus(corpus_path: Path, num_docs: int = 3) -> List[Dict]:
+def load_documents_from_corpus(
+    corpus_path: Path,
+    num_docs: int = 3,
+    doc_start: int = 0,
+    doc_end: int | None = None,
+) -> List[Dict]:
     documents = []
+    effective_end = doc_end if doc_end is not None else doc_start + num_docs
     with gzip.open(corpus_path, 'rt', encoding='utf-8') as f:
         for i, line in enumerate(f):
-            if i >= num_docs:
+            if i < doc_start:
+                continue
+            if i >= effective_end:
                 break
             doc = json.loads(line)
+            doc["_resume_doc_index"] = i
             documents.append(doc)
-    print(f"✅ Loaded {len(documents)} documents from corpus")
+    print(
+        f"✅ Loaded {len(documents)} documents from corpus "
+        f"(doc_start={doc_start}, doc_end={effective_end})"
+    )
     return documents
```

Thêm CLI args:

```diff
 parser.add_argument(
     '--num_docs',
     type=int,
     default=3,
     help='Number of documents to process from the corpus'
 )
+parser.add_argument(
+    '--doc_start',
+    type=int,
+    default=0,
+    help='0-based start offset for JSONL corpus resume ranges'
+)
+parser.add_argument(
+    '--doc_end',
+    type=int,
+    default=None,
+    help='Exclusive end offset for JSONL corpus resume ranges'
+)
+parser.add_argument(
+    '--resume_manifest',
+    type=str,
+    default=None,
+    help='Path to resume manifest JSON for build range tracking'
+)
```

Đổi chỗ gọi:

```diff
-documents = load_documents_from_corpus(corpus_path, args.num_docs)
+documents = load_documents_from_corpus(
+    corpus_path,
+    num_docs=args.num_docs,
+    doc_start=args.doc_start,
+    doc_end=args.doc_end,
+)
```

### 7.2 `build_graph.py`: ghi manifest sau khi build pass

Thêm helper:

```diff
+def update_resume_manifest(path: str, entry: Dict) -> None:
+    if not path:
+        return
+    manifest_path = Path(path)
+    manifest_path.parent.mkdir(parents=True, exist_ok=True)
+    if manifest_path.exists():
+        with open(manifest_path, "r", encoding="utf-8") as f:
+            manifest = json.load(f)
+    else:
+        manifest = {"ranges": []}
+    manifest["ranges"].append(entry)
+    with open(manifest_path, "w", encoding="utf-8") as f:
+        json.dump(manifest, f, indent=2, ensure_ascii=False)
```

Gọi sau khi build thành công:

```diff
 graph_rag.insert(prepared_docs)
 print("\n✅ Graph building completed successfully!")
+update_resume_manifest(args.resume_manifest, {
+    "doc_start": args.doc_start,
+    "doc_end": args.doc_end if args.doc_end is not None else args.doc_start + args.num_docs,
+    "docs_loaded": len(prepared_docs),
+    "output_dir": graph_rag.working_dir,
+    "status": "completed",
+    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
+})
```

### 7.3 `build_graph.py`: expose community flags

Hiện source config đã có `enable_community_summary`, `enable_incremental`, `preserve_communities`, nhưng `build_graph.py` chưa expose rõ ở CLI.

Diff đề xuất:

```diff
+parser.add_argument(
+    '--disable_community_summary',
+    action='store_true',
+    help='Skip community report generation for intermediate resume batches'
+)
+parser.add_argument(
+    '--enable_incremental',
+    action='store_true',
+    help='Enable incremental mode for same output_dir resume runs'
+)
+parser.add_argument(
+    '--preserve_communities',
+    action='store_true',
+    help='Preserve existing community reports when incremental mode is enabled'
+)
```

Override config:

```diff
 if args.output_dir:
     override_config['working_dir'] = args.output_dir
+if args.disable_community_summary:
+    override_config['enable_community_summary'] = False
+if args.enable_incremental:
+    override_config['enable_incremental'] = True
+if args.preserve_communities:
+    override_config['preserve_communities'] = True
```

Lưu ý: `--disable_community_summary` chỉ nên dùng khi có thêm `--rebuild_communities_only`, vì nếu không thì output cuối sẽ thiếu community reports.

### 7.4 `TemporalGraphRAG.ainsert()`: thêm community-only mode

Code cũ:

```python
if not len(new_doc_dicts):
    logger.warning(f"All docs are already in the storage")
    return
```

Diff đề xuất:

```diff
 if not len(new_doc_dicts):
+    if self.addon_params.get("rebuild_communities_only", False):
+        logger.info("[Resume] No new docs, rebuilding community reports only")
+        await self.community_reports.drop()
+        await generate_temporal_report(
+            self.community_reports,
+            knowledge_graph_inst=self.chunk_entity_relation_graph,
+            temporal_hierarchy_graph_inst=self.temporal_hierarchy_graph,
+            global_config=asdict(self),
+        )
+        await self._insert_done()
+        return
     logger.warning(f"All docs are already in the storage")
     return
```

Thay đổi này nhỏ nhưng cần cẩn thận:

- Không đụng extraction/embedding.
- Chỉ cho phép rebuild community khi không có docs mới.
- Cần truyền `addon_params["rebuild_communities_only"] = True` từ config/CLI.

### 7.5 `core/building.py`: thêm chunk extraction checkpoint

Code cũ:

```python
async def _process_single_content(chunk_key_dp: tuple[str, TextChunkSchema]):
    chunk_key = chunk_key_dp[0]
    chunk_dp = chunk_key_dp[1]
    content = chunk_dp["content"]
    ...
    raw_llm_result = await use_llm_func(hint_prompt)
    ...
    return dict(maybe_nodes), dict(maybe_edges)
```

Diff minh họa:

```diff
 async def _process_single_content(chunk_key_dp: tuple[str, TextChunkSchema]):
     chunk_key = chunk_key_dp[0]
     chunk_dp = chunk_key_dp[1]
     content = chunk_dp["content"]
+    extraction_cache = global_config.get("chunk_extraction_cache")
+    extraction_model = global_config.get("best_model_id") or global_config.get("model")
+    extraction_cache_key = compute_mdhash_id(
+        f"{chunk_key}:{extraction_model}:{compute_mdhash_id(content)}",
+        prefix="chunk-extract-",
+    )
+
+    if extraction_cache is not None:
+        cached = await extraction_cache.get_by_id(extraction_cache_key)
+        if cached is not None:
+            print(f"[resume] chunk extraction cache hit: {chunk_key}", flush=True)
+            return cached["nodes"], cached["edges"]
 
     ...
     raw_llm_result = await use_llm_func(hint_prompt)
     ...
-    return dict(maybe_nodes), dict(maybe_edges)
+    result_nodes = dict(maybe_nodes)
+    result_edges = dict(maybe_edges)
+    if extraction_cache is not None:
+        await extraction_cache.upsert({
+            extraction_cache_key: {
+                "chunk_key": chunk_key,
+                "model": extraction_model,
+                "nodes": result_nodes,
+                "edges": result_edges,
+                "content_chars": len(content),
+            }
+        })
+        await extraction_cache.index_done_callback()
+    return result_nodes, result_edges
```

Điểm cần thêm:

- Import `compute_mdhash_id` nếu file chưa có sẵn trong scope.
- Truyền `chunk_extraction_cache` vào `global_config`.
- Tạo storage mới trong `TemporalGraphRAG.__post_init__`.

### 7.6 `TemporalGraphRAG.__post_init__`: thêm storage cho chunk extraction cache

Diff minh họa:

```diff
 self.llm_response_cache = (
     self.key_string_value_json_storage_cls(
         namespace="llm_response_cache", global_config=asdict(self)
     )
     if self.enable_llm_cache
     else None
 )
+
+self.chunk_extraction_cache = self.key_string_value_json_storage_cls(
+    namespace="chunk_extractions",
+    global_config=asdict(self),
+) if self.addon_params.get("enable_chunk_extraction_cache", False) else None
```

Sau đó khi gọi `entity_extraction_func`, truyền vào global config:

```diff
-global_config=asdict(self),
+global_config={**asdict(self), "chunk_extraction_cache": self.chunk_extraction_cache},
```

Và persist ở `_insert_done()`:

```diff
 for storage_inst in [
     self.full_docs,
     self.text_chunks,
     self.llm_response_cache,
+    self.chunk_extraction_cache,
     self.community_reports,
```

---

## 8. Lệnh Chạy Sau Khi Có Resume CLI

### 8.1 Start server 7B TurboQuant

```bash
tmux new -s srv_tq_turbo_7b_p2c64k_hf_nomic
```

```bash
conda activate turboquant
cd /home/guest/Projects/Research/llama-cpp-turboquant

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 65536 \
  --parallel 2 \
  --n-predict 3072 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/tq_7b_hf_resume_$(date +%Y%m%d_%H%M%S).log
```

### 8.2 Build 50/100/384 theo doc range

```bash
tmux new -s bld_tq_7b_hf_resume_050_384docs
```

```bash
conda activate turboquant
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false

RUN_DIR=outputs/build_graph/tq_7b_hf_nomic_resume_base384
MANIFEST=${RUN_DIR}/resume_manifest.json
mkdir -p logs/build_graph results/usage "${RUN_DIR}"

run_range () {
  START=$1
  END=$2
  LABEL=$(printf "%03d_%03d" "$START" "$END")
  export TG_RAG_USAGE_LOG=results/usage/tq_7b_hf_resume_${LABEL}.jsonl

  python -u build_graph.py \
    --output_dir "${RUN_DIR}" \
    --resume_manifest "${MANIFEST}" \
    --doc_start "$START" \
    --doc_end "$END" \
    --model qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p2-np3072 \
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
    --embedding_batch_num 16 \
    --embedding_max_async 1 \
    --embedding_prefix "search_document: " \
    --chunk_size 1200 \
    --chunk_overlap 100 \
    --llm_max_async 2 \
    --llm_timeout 900 \
    2>&1 | tee logs/build_graph/tq_7b_hf_resume_${LABEL}.log
}

run_range 0 50
run_range 50 100
run_range 100 384
```

Nếu lỗi ở community context:

```text
server: --parallel 1
build:  --llm_max_async 1
```

Lý do: `--parallel 2` với `-c 65536` cho slot khoảng 32768 context. Nếu community prompt vượt 32K, cần p1 để có slot 65536.

### 8.3 Rerun khi fail

Nếu fail ở range `100..384`, chạy lại đúng range đó:

```bash
run_range 100 384
```

Với Level 2 chunk extraction cache:

- Chunk đã extract xong sẽ `cache hit`.
- Chỉ chunk chưa hoàn tất mới gọi LLM lại.
- Nếu fail ở embedding/community, rerun không mất toàn bộ thời gian extraction.


### 8.4 Ví dụ resume theo đúng các TH đã fail thực tế

#### Case A: fail rất sớm ở extraction

Run thực tế:

```text
cmp_tq_turbo_7b_p4c64knp4096_100docs
```

Trạng thái output:

- `kv_store_llm_response_cache.json`: có 24 entries
- `kv_store_full_docs.json`: missing
- `kv_store_text_chunks.json`: missing
- `graph_chunk_entity_relation.graphml`: missing

Ý nghĩa:

- Source mới chỉ kịp gọi một ít request extraction.
- Chưa có graph merge hữu ích.
- Chưa có docs/chunks persist.

Resume hiện tại sẽ ra sao:

- Rerun gần như phải bắt đầu lại extraction.
- Chỉ có lợi nhỏ từ 24 cache hit prompt-level.

Resume sau khi có Level 1 + Level 2:

- `resume_manifest` biết range nào đang chạy dở.
- `chunk_extraction_cache` sẽ skip đúng các chunk đã extract xong, không chỉ skip theo prompt cache mơ hồ.

#### Case B: fail sau extraction, ngay ở embedding

Run thực tế:

```text
cmp_tq_turbo_14bq5_p2c32knp4096_100docs
```

Trạng thái output:

- `kv_store_llm_response_cache.json`: 864 entries
- `graph_chunk_entity_relation.graphml`: tồn tại, khoảng 3.7MB
- `vdb_entities.json`: tồn tại nhưng `data_len=0`
- `vdb_relations.json`: tồn tại nhưng `data_len=0`
- `kv_store_full_docs.json`: `0`
- `kv_store_text_chunks.json`: `0`
- lỗi log: `Ollama embedding API error 500: {"error":"the input length exceeds the context length"}`

Ý nghĩa:

- Chunk extraction gần như đã chạy xong một khối lớn.
- Graph relation/entity đã được dựng tới mức nào đó.
- Nhưng persist cuối cho docs/chunks không diễn ra.
- Vector stage fail trước khi commit được dữ liệu hữu ích.

Resume hiện tại sẽ ra sao:

- Không có cách biết chunk nào đã extract xong ngoài prompt cache.
- Không nên tin `graphml` và `vdb_*.json` hiện có là output chuẩn.
- Rerun có thể cache hit nhiều prompt, nhưng orchestration vẫn phải đi lại gần như toàn bộ.

Resume sau khi có Level 2 + Level 4:

- Chunk extraction đọc `kv_store_chunk_extractions.json` để skip toàn bộ chunk đã hoàn tất.
- Vector upsert đọc checkpoint batch để chỉ làm tiếp phần entity/relation chưa embed xong.
- Không cần người chạy xóa tay graph/vector trung gian.

#### Case C: pass kỹ thuật nhưng fail chất lượng community

Run thực tế:

```text
cmp_tq_turbo_7b_p4c64knp4096_050docs
```

Trạng thái output:

- `full_docs=50`
- `text_chunks=199`
- `community_reports=75`
- có 14 `Error Report`
- log vẫn có `Graph building completed successfully`

Ý nghĩa:

- Extraction, graph merge, vector, persist đều đã xong.
- Lỗi nằm ở community stage, nhưng source hiện tại nuốt lỗi thành error report.

Resume hiện tại sẽ ra sao:

- Nếu rerun cùng `output_dir`, source thấy docs đã có rồi và return sớm.
- Không có cách chỉ rebuild community sau khi đổi từ p4 sang p1.

Resume sau khi có Level 3:

- Giữ nguyên docs/chunks/vector/graph.
- Chạy `--rebuild_communities_only`.
- Drop community cũ, build lại community với profile context lớn hơn.

#### Case D: fail rất muộn nhưng chưa có persist docs/chunks

Run thực tế:

```text
cmp_tq_turbo_14bq5_p2c32knp4096_384docs
```

Trạng thái output:

- `kv_store_llm_response_cache.json`: 622 entries
- `full_docs/text_chunks/community/vdb/graphml`: đều thiếu
- log cho thấy đang đi qua extraction progress rất dài, nhưng chưa có `Graph building completed successfully`

Ý nghĩa:

- Đây là case tốn thời gian nhất: đã đốt nhiều giờ extraction nhưng output cuối gần như không có gì authoritative ngoài prompt cache.

Resume hiện tại sẽ ra sao:

- Có thể giữ cache để mong cache hit ở rerun.
- Nhưng không thể khẳng định rerun sẽ bỏ qua đúng các chunk đã xong, vì source không có chunk checkpoint.

Resume sau khi có Level 2:

- Mỗi chunk extract xong sẽ được ghi ngay.
- Dù fail ở embedding hay community rất muộn, lần sau source chỉ làm tiếp các chunk chưa checkpoint và đi thẳng sang stage sau.

---

## 9. Check Sau Khi Chạy 50/100/384

### 9.1 Check build log

```bash
grep -E "new documents|new chunks|Processed .*chunks|chunk LLM extraction|embedding content lengths|Truncate embedding|entity_vdb upsert|relation_vdb upsert|Failed to generate community report|Ollama embedding API error|Graph building completed|Total elapsed" \
  logs/build_graph/tq_7b_hf_resume_*.log
```

Ý nghĩa:

| Pattern | Cần nhìn gì |
|---|---|
| `new documents` | Range có đúng số docs mới không |
| `new chunks` | Có chunk mới không, số chunk có hợp lý không |
| `Processed ... chunks` | Có đạt 100% không |
| `embedding content lengths` | Entity/relation content có phình quá dài không |
| `Truncate embedding` | Có phải truncate không; truncate nhiều là tín hiệu cần xử lý merge description |
| `Failed to generate community report` | Community không mất nhưng có error report, cần tính là quality failure |
| `Ollama embedding API error` | Không được xuất hiện khi dùng HF |
| `Graph building completed` | Chỉ pass khi có dòng này |

### 9.2 Check output counts

```bash
python - <<'PY'
import json
from pathlib import Path

d = Path("outputs/build_graph/tq_7b_hf_nomic_resume_base384")

def load(name):
    p = d / name
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

full_docs = load("kv_store_full_docs.json")
text_chunks = load("kv_store_text_chunks.json")
communities = load("kv_store_community_reports.json")
entities = load("vdb_entities.json").get("data", {})
relations = load("vdb_relations.json").get("data", {})

community_errors = 0
for value in communities.values():
    raw = json.dumps(value, ensure_ascii=False)
    if "Failed to generate report" in raw or "Error Report" in raw:
        community_errors += 1

print("docs", len(full_docs))
print("chunks", len(text_chunks))
print("communities", len(communities))
print("community_errors", community_errors)
print("entities", len(entities))
print("relations", len(relations))
PY
```

Tiêu chí pass cho 384:

```text
docs = 384
chunks khoảng 1462
community_errors = 0 hoặc rất thấp và có giải thích
entities > 0
relations > 0
không có Ollama embedding API error
cache model là alias local Qwen, không phải Gemini
```

### 9.3 Check server log

```bash
grep -E "n_ctx|n_ctx_slot|truncated|POST /v1/chat/completions|exceeds|error" \
  logs/llama_server/tq_7b_hf_resume_*.log
```

Nếu thấy:

```text
truncated = 0
```

là tốt. Nếu thấy context error:

```text
request (...) exceeds the available context size
```

thì community prompt đang vượt slot context, cần đổi `--parallel 1` hoặc giảm prompt/community payload.

---

## 10. Phân Tích Lỗi Theo Giai Đoạn Build

### 10.1 Lỗi chunk extraction

Giai đoạn chạy:

```text
chunk content
-> temporal_entity_extraction_new prompt
-> local Qwen qua llama-server
-> parse entity/relation records
```

Rủi ro:

- Local LLM decode lâu.
- Timeout từng request.
- Một chunk trả output malformed, source retry 3 lần rồi có thể trả empty dict.
- Nếu process chết giữa `asyncio.gather`, chưa có structured checkpoint.

Kiểm chứng:

- HF 10 docs: `Processed 39(100%) chunks`, pass.
- 14B 384 log hiện tại chưa có pass, mới thấy progress extraction, chưa có vector/community/final.
- 7B 100 cũ incomplete, log không có `Graph building completed`.

Hướng fix:

- Thêm chunk extraction checkpoint.
- Bật usage log để biết request nào lâu/lỗi.
- Dùng `--llm_max_async` khớp `--parallel`.

### 10.2 Lỗi embedding input quá dài

Giai đoạn chạy:

```text
merge entity/relation
-> tạo content embedding
-> entity_vdb.upsert / relation_vdb.upsert
-> embedding provider
```

Rủi ro:

- Entity description tích lũy quá dài khi cùng entity xuất hiện nhiều quý/năm.
- Relation description cũng có thể phình theo timestamp.
- Ollama embedding context thấp, dễ fail.

Kiểm chứng:

- 14B 100 docs fail ở `entity_vdb.upsert`.
- TH11A 384 cũ fail sau khi đã xử lý xong 1462 chunks, lỗi thật là embedding input dài.
- HF 1/5/10 chưa fail; max entity content mới khoảng 2.2K chars.

Hướng fix:

- Dùng HF Nomic thay Ollama embedding.
- Giữ `--embedding_max_chars 24000`.
- Log top content dài nhất.
- Nếu full 384 có nhiều truncate, xử lý tiếp ở merge layer: tách description theo temporal slice hoặc summarize description trước embedding.

### 10.3 Lỗi community context

Giai đoạn chạy:

```text
temporal hierarchy graph
-> pack nodes/edges into community prompt
-> local Qwen community report
-> kv_store_community_reports.json
```

Rủi ro:

- `--parallel N` chia context thành slot nhỏ.
- p4/c64k chỉ còn khoảng 16K context/slot.
- Community prompt có thể 20K-70K tokens.

Kiểm chứng:

- 7B p4 50 docs pass nhưng có 14 community error reports.
- 14B p2 50 docs cũng có nhiều community context errors vì c32k/p2 chỉ 16K per slot.
- New 7B p2/c64k 10 docs chưa lỗi vì slot 32K và prompt hiện chưa vượt.

Hướng fix:

- 7B nên dùng `-c 65536 --parallel 2` trước.
- Nếu 50/100/384 còn lỗi community, đổi sang `--parallel 1`, `--llm_max_async 1`.
- Về code, cần thêm community-only rebuild để có thể sửa community mà không rebuild extraction.

### 10.4 Lỗi output incomplete

Giai đoạn chạy:

```text
fail trước full_docs/text_chunks upsert
-> _insert_done vẫn persist storage
-> nhưng storage chưa có data cần thiết
```

Kiểm chứng:

- 14B 100 fail embedding, output đếm ra docs/chunks/entities/relations đều 0.

Hướng fix:

- Không dùng output incomplete làm mốc.
- Cần resume manifest/chunk cache.
- Không đánh dấu doc complete trước khi graph/vector/community đã pass, vì nếu đánh dấu sớm thì rerun sẽ skip doc nhưng graph lại thiếu.

---

## 11. Khuyến Nghị Chạy Tiếp Hiện Tại

Với trạng thái hiện tại, thứ tự nên làm:

1. Chạy HF 7B lên 50 docs trước, cùng profile p2/c64k.
2. Nếu 50 pass và `community_errors=0`, chạy 100.
3. Nếu 100 pass, chạy 384.
4. Nếu lỗi community context, đổi server sang p1 rồi rerun.
5. Nếu lỗi embedding/truncate nhiều, giữ HF nhưng cần xử lý merge description.

Không nên chạy thẳng 384 khi chưa có resume chunk-level, vì nếu fail ở embedding/community sau nhiều giờ thì vẫn mất nhiều thời gian.

---

## 12. Minimal Acceptance Cho Cơ Chế Resume

Một cơ chế resume được tính là đạt khi:

```text
1. Có thể chạy doc range 0..50, 50..100, 100..384.
2. Có manifest ghi range nào pass/fail.
3. Rerun cùng range không gọi lại chunk extraction đã hoàn tất.
4. Nếu fail ở embedding, rerun cache hit chunk extraction.
5. Nếu fail ở community, có thể rebuild community-only.
6. Output cuối có đủ docs/chunks/vectors/GraphML/community reports.
7. Log chỉ rõ stage fail: chunk extraction, vector embedding, community, persist.
```

---

## 13. Tóm Tắt Quyết Định

Để chạy full 384 docs ổn định với local LLM + TurboQuant, không nên chỉ dựa vào `--num_docs` và output folder riêng lẻ.

Hướng đúng là:

```text
HF embedding đã giải quyết nhóm lỗi embedding context tốt hơn Ollama.
TurboQuant p2/c64k đang giảm lỗi community context so với p4/c64k.
Nhưng build 384 vẫn cần resume vì extraction quá lâu và lỗi cuối pipeline rất tốn chi phí.
```

Patch nên ưu tiên theo thứ tự:

1. `--doc_start`, `--doc_end`, `--resume_manifest`.
2. `chunk_extraction_cache`.
3. `--rebuild_communities_only`.
4. Vector batch checkpoint nếu 384 vẫn fail ở embedding.

