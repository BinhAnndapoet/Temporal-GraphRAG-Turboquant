# Demo Setup & DB Graph Flow for `demo.py`

Tài liệu này mô tả chi tiết cách `demo.py` hoạt động, DB Graph được truyền vào như thế nào, và toàn bộ các bước setup để chạy demo một cách ổn định.

Mục tiêu là giúp bạn trả lời 3 câu hỏi:

1. `demo.py` có khớp với source code hiện tại không?
2. DB Graph đi vào demo bằng đường nào?
3. Cần chuẩn bị những gì để demo chạy được từ đầu đến cuối?

---

## TL;DR — Canonical workflow để chạy lại demo không lỗi

Đây là luồng khuyến nghị duy nhất cho localLLM + Turboquant runtime (`llama-server`):

### Cách nhanh nhất (1 lệnh, tránh lỗi startup timing)

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
bash scripts/run_demo_stack.sh
```

Sau khi chạy xong script:

- Server endpoint `http://localhost:8080/v1/models` đã ready
- Demo chạy tại `http://127.0.0.1:8501`
- Trong UI, chọn preset: `Local Turboquant (recommended)`

### Bước 1: Start server

```bash
tmux kill-session -t llm_srv 2>/dev/null || true
tmux new -s llm_srv -d
tmux send-keys -t llm_srv "conda activate turboquant && cd /home/guest/Projects/Research/llama-cpp-turboquant && ./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072 \
  --host 127.0.0.1 --port 8080 \
  -ctk q8_0 -ctv turbo3 -fa on -ngl 99 \
  -c 131072 --parallel 4 --n-predict 3072" C-m

curl -sS http://localhost:8080/v1/models
```

### Bước 2: Start demo

```bash
tmux kill-session -t demo 2>/dev/null || true
tmux new -s demo -d
tmux send-keys -t demo "cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant && conda activate turboquant && streamlit run demo.py --server.port 8501" C-m
```

### Bước 3: Điền UI đúng 100%

- `Provider (API path)`: `openai`  ✅ (khuyến nghị cho local llama-server)
- `Model`: `qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072`
- `Base URL`: `http://localhost:8080/v1`
- `Working Directory`: folder `outputs/build_graph/BUILD_*` đúng run bạn đã build
- `Query Mode`: `local`
- `Enable Entity Retrieval`: ON
- `Seed Node Method`: `entities`

### Bước 3.1: Dùng Preset để tránh nhập sai

Trong sidebar demo, chọn:

`Quick Preset` → `Local Turboquant (recommended)` → `Apply Preset`

Preset này tự điền các trường quan trọng:

- Provider: `openai`
- Base URL: `http://localhost:8080/v1`
- Query Mode: `local`
- Retrieval: `Enable Entity Retrieval=ON`, `Seed Node Method=entities`

Sau đó bạn chỉ cần kiểm tra lại:

- `Model` khớp alias server
- `Working Directory` đúng folder `BUILD_*`

### Khi nào mới chọn `Provider = turboquant`?

Chỉ khi bạn muốn test nhánh provider turboquant trong app logic. Runtime server vẫn là cùng `llama-server`.

---

## 1. Kết luận nhanh

`demo.py` hiện đang khớp với source code theo đúng hướng sau:

- Demo dùng `create_temporal_graphrag_from_config()` để khởi tạo graph runtime.
- Demo tạo `QueryParam` giống luồng query thật của repo.
- Demo gọi `graph_rag.query(question, param=query_param)`.
- Ở `local` mode, query trả về cả `response` và `retrieval_detail`, nên demo có thể render graph traversal.

Điểm cần nhớ nhất:

- **DB Graph không được truyền vào như một object DB riêng từ UI**.
- Demo chủ yếu truyền **`working_dir`**.
- Từ `working_dir`, source code tự load toàn bộ graph artifacts đã build sẵn.

Nếu bạn muốn dùng Neo4j thật sự, thì đó là một nhánh riêng qua `addon_params.neo4j_url` và `addon_params.neo4j_auth`, nhưng `demo.py` hiện tại **chưa expose UI cho phần đó**.

### 1.1 Ma trận quyết định Provider / Key / Base URL (rất quan trọng)

Đây là quy tắc chuẩn để tránh nhầm giữa OpenAI cloud và local `llama-server` trong thư mục:

`/home/guest/Projects/Research/llama-cpp-turboquant`

| Trường hợp thực tế | Provider trong demo/query | Base URL | Key cần dùng |
|---|---|---|---|
| OpenAI cloud thật | `openai` | `https://api.openai.com/v1` (hoặc proxy) | `OPENAI_API_KEY` **thật** |
| Local `llama-server` (OpenAI-compatible, khuyến nghị) | `openai` | `http://localhost:8080/v1` | `OPENAI_API_KEY=dummy` (non-empty) |
| Local `llama-server` nhưng muốn đi nhánh turboquant | `turboquant` | `http://localhost:8080/v1` | `OPENAI_API_KEY_TEMPORALRAG=dummy` hoặc `OPENAI_API_KEY=dummy` |
| Gemini API | `gemini` | để trống (trừ khi dùng gateway) | `GOOGLE_API_KEY` hoặc `GEMINI_API_KEY` **thật** |
| Ollama local | `ollama` | `http://localhost:11434` | Không cần key |

**Quy tắc vàng:**

- Nếu backend là `llama-server` local, hãy ưu tiên `Provider=openai` để ít lỗi nhất.
- `Model` phải khớp chính xác với `--alias` khi start `llama-server`.
- Build và Query phải dùng cùng logic provider/backend để kết quả nhất quán.

### 1.2 Build vs Query phải đồng bộ cái gì

Khi đổi provider/backend, cần giữ đồng bộ các điểm sau giữa `build_graph.py`, `query_graph.py`, và `demo.py`:

1. Cùng backend LLM (`openai` local / `turboquant` / `gemini` / `ollama`)
2. Cùng model alias (nếu local `llama-server`)
3. Cùng endpoint (`Base URL`)
4. Cùng `working_dir` (folder output đã build xong)

Nếu không đồng bộ, demo rất dễ ra `Seed Nodes = 0`, `PPR Nodes = 0`, hoặc câu trả lời fallback kiểu “Sorry...”.

---

## 2. `demo.py` đang làm gì

File `demo.py` là một Streamlit app để:

- nhập câu hỏi,
- chọn config,
- chọn provider/model/base URL,
- chạy query local/global/naive,
- hiển thị câu trả lời,
- hiển thị thống kê retrieval,
- và nếu có dữ liệu traversal, render graph bằng PyVis.

Các thư viện chính:

- `streamlit` — UI
- `networkx` — đồ thị gốc
- `pyvis` — render graph HTML
- `create_temporal_graphrag_from_config()` — khởi tạo graph runtime
- `QueryParam` — cấu hình query
- `ConfigLoader` — đọc file YAML

---

## 3. DB Graph được truyền vào như thế nào

### 3.1 Luồng thực tế

Luồng của demo không phải kiểu “mở kết nối DB rồi inject trực tiếp”.

Nó đi theo pipeline này:

1. Người dùng nhập trong sidebar:
   - `config_path`
   - `working_dir`
   - `provider`
   - `model`
   - `base_url`

2. `demo.py` gom các giá trị đó thành `override_config`.

3. Demo gọi:
   - `create_temporal_graphrag_from_config(config_path=..., config_type="querying", override_config=...)`

4. `ConfigLoader` đọc YAML config.

5. `create_temporal_graphrag_from_config()` tạo `TemporalGraphRAG` với `working_dir`.

6. `TemporalGraphRAG` load các storage artifact từ thư mục đó.

7. Khi query chạy, `graph_rag.query(...)` dùng chính các storage đã load.

### 3.2 `working_dir` là trung tâm

Trong source hiện tại, `working_dir` là điểm chốt.

Các file graph artifacts thường nằm trong đó, ví dụ:

- `graph_chunk_entity_relation.graphml`
- `graph_temporal_hierarchy.graphml`
- `kv_store_community_reports.json`
- `kv_store_full_docs.json`
- `kv_store_text_chunks.json`
- `vdb_entities.json`
- `vdb_relations.json`

Nói ngắn gọn:

> Demo không truyền “database graph” như một biến riêng biệt; demo truyền **đường dẫn tới kho graph artifacts** thông qua `working_dir`.

### 3.3 Khi nào mới là Neo4j?

Nếu bạn muốn dùng Neo4j, source hiện có lớp `Neo4jStorage`, và nó lấy thông tin từ `addon_params`:

- `addon_params.neo4j_url`
- `addon_params.neo4j_auth`

Nhưng `demo.py` hiện tại chỉ là demo visual query theo `working_dir`, nên **không phải Neo4j demo**.

---

## 4. Khớp source code ở đâu

### 4.1 `demo.py` khớp với factory tạo graph

Demo gọi:

- `create_temporal_graphrag_from_config(...)`

Đây là đúng entry point mà source đang dùng để dựng graph runtime từ YAML.

### 4.2 `query()` khớp với API hiện tại

Source `TemporalGraphRAG` hiện có:

- `query(self, query: str, param: QueryParam = QueryParam())`
- `aquery(self, query: str, param: QueryParam = QueryParam())`

Ở `local` mode, `aquery()` trả về:

- `response`
- `retrieval_detail`

Nên demo lấy tuple này là đúng.

### 4.3 Dữ liệu để render graph đã có trong `retrieval_detail`

Source `tgrag/src/core/querying.py` đang set các field như:

- `retrieval_detail["seed_nodes"]`
- `retrieval_detail["ppr_scores"]`
- `retrieval_detail["timestamps"]`
- `retrieval_detail["relation_metadata"]`

Đây chính là các trường mà demo dùng để highlight graph traversal.

### 4.4 Một sửa lỗi nhỏ đã được áp dụng

Trong `demo.py`, có chỗ gọi `logger.warning(...)` nhưng file không import logger.

Mình đã đổi sang `st.warning(...)` để tránh crash khi underlying graph object không được tìm thấy.

---

## 5. Config demo hiện tại đang ánh xạ gì

File config đang mở là `tgrag/configs/config_eval_ollama_nomic_fast.yaml`.

### 5.1 Phần `building`

```yaml
building:
  corpus_path: "./ECT_data/"
  working_dir: "./output_ollama_eval"
  provider: "gemini"
  model: "gemini-2.5-flash-lite"
  embedding_provider: "ollama"
  chunk_size: 1200
  chunk_overlap: 100
  disable_entity_summarization: true
```

Ý nghĩa:

- graph build sẽ dùng folder `./output_ollama_eval`
- LLM build là Gemini
- embedding là Ollama
- entity summarization bị tắt để tránh stall

### 5.2 Phần `querying`

```yaml
querying:
  working_dir: "./output_ollama_eval"
  provider: "gemini"
  model: "gemini-2.5-flash"
  embedding_provider: "ollama"
  mode: "local"
  top_k: 50
  enable_subgraph: true
  seed_node_method: "relations"
```

Ý nghĩa:

- query sẽ đọc lại cùng `working_dir`
- mode mặc định là `local`
- graph visualization của demo có thể hoạt động nếu query trả về `retrieval_detail`

### 5.3 Vì sao `working_dir` phải khớp?

Nếu demo trỏ sai `working_dir`, nó sẽ:

- không tìm thấy graph artifacts,
- không có traversal detail,
- hoặc query ra kết quả nhưng không render được graph.

---

## 6. Setup đầy đủ để demo

### 6.1 Chuẩn bị môi trường

Bạn cần:

- Python env của project
- dependencies của repo
- `streamlit`
- `networkx`
- `pyvis`
- provider phù hợp với config

### 6.2 Chuẩn bị biến môi trường

Tùy backend bạn dùng:

- Nếu chạy local OpenAI-compatible / TurboQuant:
  - `OPENAI_BASE_URL=http://localhost:8080/v1`
  - `OPENAI_API_KEY=<dummy-or-valid-value>`
- Nếu dùng Gemini:
  - `GOOGLE_API_KEY` hoặc `GEMINI_API_KEY`
- Nếu dùng Ollama:
  - `OLLAMA_BASE_URL=http://localhost:11434`

Nếu muốn bật log debug cho build script:

- `TG_RAG_DEBUG=true`

### 6.2.1 Phân biệt rõ `Model` vs `Base URL`

Đây là phần dễ nhầm nhất trong hình bạn gửi:

- **`Base URL` không phải là đường dẫn tới model**.
  - Nó là **địa chỉ server API** mà demo sẽ gọi để hỏi LLM.
  - Ví dụ: `http://localhost:8080/v1`, `http://localhost:11434`, hoặc URL của OpenAI/Gemini proxy.
- **`Model` là tên model mà server đó đang cung cấp**.
  - Ví dụ: `gpt-4o-mini`, `gemini-2.5-flash`, `llama3.1:8b`, `qwen2.5:14b`, `nomic-embed-text`.

Nói ngắn gọn:

> `Base URL` = “gọi đến server nào”
>
> `Model` = “trên server đó, dùng model nào”

Nếu điền sai `Base URL`, demo sẽ không kết nối được.
Nếu điền sai `Model`, demo có thể kết nối được nhưng server sẽ báo không tìm thấy model.

### 6.2.2 Điền gì cho từng provider

#### Provider = `turboquant`

- `Base URL`: endpoint của server turboquant/OpenAI-compatible mà bạn đang chạy.
  - Thường gặp: `http://localhost:8080/v1`
- `Model`: đúng tên model mà server đó đang expose.
  - Bạn lấy tên này từ lệnh/endpoint list model của server hoặc từ log khởi động.
  - Ví dụ: `qwen3-14b`, `llama3.1`, `gemma3`, hoặc tên alias mà server đang trả về.

#### Provider = `ollama`

- `Base URL`: thường là `http://localhost:11434`
- `Model`: tên model trong Ollama, ví dụ:
  - `llama3.1`
  - `qwen2.5:14b`
  - `nomic-embed-text`

#### Provider = `openai`

- `Base URL`: để trống nếu dùng OpenAI thật, hoặc điền endpoint OpenAI-compatible nếu bạn dùng proxy/local server.
  - Ví dụ local proxy: `http://localhost:8080/v1`
- `Model`: tên model OpenAI, ví dụ:
  - `gpt-4o-mini`
  - `gpt-4.1-mini`

#### Provider = `gemini`

- `Base URL`: thường để trống, trừ khi bạn dùng proxy riêng.
- `Model`: tên model Gemini, ví dụ:
  - `gemini-2.5-flash`
  - `gemini-2.5-flash-lite`

### 6.2.3 Nếu bạn không biết phải điền `Model` gì

Làm theo 1 trong 3 cách sau:

1. **Xem file config YAML** đang dùng
   - Thường trong `building.model` hoặc `querying.model` đã có sẵn model chuẩn.
2. **Xem log khởi động của server LLM**
   - Nhiều server sẽ in ra tên model đang được serve.
3. **Hỏi endpoint liệt kê model** của server nếu có
   - Với OpenAI-compatible server, thường có endpoint kiểu `/v1/models`.

Nếu vẫn chưa chắc, cách an toàn nhất là:

- dùng đúng `Provider` theo backend đang chạy,
- giữ `Base URL` khớp endpoint server,
- và copy `Model` đúng hệt tên model trong config hoặc log.

### 6.2.4 Lưu ý riêng cho `turboquant` và lỗi API key

Trong code hiện tại, khi bạn chọn `Provider = turboquant`, luồng khởi tạo vẫn đi qua phần kiểm tra `api_key` giống một provider OpenAI-compatible bình thường.

Vì vậy, nếu bạn chạy demo trong tmux và gặp lỗi:

```text
API key not found for provider 'turboquant'
```

thì cách xử lý nhanh nhất là làm đúng theo 1 trong 2 khối lệnh sau.

#### Cách 1: Giữ `Provider = turboquant`

Trong **tmux session đang chạy `demo.py`**, chạy nguyên khối lệnh này:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

# Key giả chỉ để code không chặn ở bước kiểm tra api_key
export OPENAI_API_KEY=dummy
export OPENAI_API_KEY_TEMPORALRAG=dummy

# Nếu demo.py đọc .env thì giữ .env có các biến trên cũng được,
# nhưng export trực tiếp trong tmux là cách chắc chắn nhất.

streamlit run demo.py
```

Trong UI của demo, điền:

- `Provider = turboquant`
- `Model = <tên model 7B thật mà server đang serve>`
- `Base URL = http://localhost:8080/v1`

#### Cách 2: Đổi sang `Provider = openai` cho server OpenAI-compatible local

Nếu server local của bạn có OpenAI-compatible API, cách ít lỗi hơn là dùng `openai`.

Trong **tmux session đang chạy `demo.py`**, chạy nguyên khối lệnh này:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant

# Key giả để pass bước validate nếu code yêu cầu api_key
export OPENAI_API_KEY=dummy

# Endpoint của server local
export OPENAI_BASE_URL=http://localhost:8080/v1

streamlit run demo.py
```

Trong UI của demo, điền:

- `Provider = openai`
- `Model = <tên model 7B thật mà server đang serve>`
- `Base URL = http://localhost:8080/v1`

#### Checklist để tránh sai

- Session 1: chạy **LLM server** (turboquant / llama-server / OpenAI-compatible server)
- Session 2: chạy **demo.py**
- Trong session chạy demo, luôn có một key môi trường không rỗng:
  - `OPENAI_API_KEY=dummy`
  - hoặc `OPENAI_API_KEY_TEMPORALRAG=dummy`
- `Base URL` phải trỏ đúng endpoint server
- `Model` phải là tên model 7B thật, không phải chỉ `7b`

Nếu bạn không muốn set key giả, hãy ưu tiên `Provider = openai` khi dùng server local OpenAI-compatible. Đây thường là cách ít lỗi nhất cho demo 7B.

### 6.3 Build graph trước khi demo

Demo chỉ chạy đúng khi thư mục `working_dir` đã có graph artifacts.

Nghĩa là bạn phải build xong trước, rồi mới mở demo.

Sau build, kiểm tra trong `working_dir` có các file graph/artifact cần thiết.

### 6.4 Start server nếu bạn dùng local runtime

Nếu config dùng local LLM:

- bật `llama-server` hoặc server tương ứng
- xác nhận endpoint đúng với `base_url`

### 6.5 Chạy Streamlit demo

Chạy `demo.py` từ repo root.

Sau đó ở UI:

- chọn đúng config file
- nhập đúng `working_dir`
- chọn provider/model/base URL đúng với runtime
- để `mode = local`
- bật `Show Graph Visualization`

### 6.6 Chạy query

Nhập câu hỏi phù hợp với data corpus, rồi bấm `Run Query`.

Nếu mọi thứ khớp, bạn sẽ thấy:

- câu trả lời ở cột trái
- traversal statistics
- đồ thị tương tác ở cột phải

---

## 7. Luồng render graph trong demo

### 7.1 Điều kiện để render

Demo chỉ render đồ thị khi:

- `show_graph = true`
- `mode = local`
- `retrieval_detail` tồn tại
- underlying graph object có thể được truy cập qua `graph_rag.chunk_entity_relation_graph._graph`

### 7.2 Cách highlight node

Demo phân màu node như sau:

- **Đỏ**: seed nodes
- **Cam**: selected entities
- **Vàng**: high PPR score nodes
- **Xám**: background nodes

### 7.3 Dữ liệu dùng để render

Demo lấy từ `retrieval_detail`:

- `seed_nodes`
- `ppr_scores`
- `entities`
- `timestamps`

Sau đó dùng `NetworkX` subgraph + `PyVis` để xuất HTML.

---

## 8. Checklist chạy demo an toàn

- [ ] `working_dir` đúng với thư mục build graph.
- [ ] Graph artifacts đã tồn tại trong `working_dir`.
- [ ] Server LLM đang chạy đúng endpoint.
- [ ] `provider` và `model` trong demo khớp runtime.
- [ ] Config query dùng `mode: local` nếu muốn render graph.
- [ ] `demo.py` đã được chạy trong môi trường có `streamlit`, `networkx`, `pyvis`.
- [ ] Nếu dùng Gemini, API key đã được set.
- [ ] Nếu muốn debug build, `TG_RAG_DEBUG=true` đã được bật trước khi chạy build.

---

## 9. Các lỗi hay gặp và cách hiểu

### 9.1 Không thấy graph visualization

Thường là do:

- query mode không phải `local`
- `retrieval_detail` không được trả về
- `working_dir` sai
- graph object nội bộ không load được

### 9.2 Demo chạy nhưng báo không có graph structure

Đây là tình huống khi demo không tìm thấy `chunk_entity_relation_graph._graph`.

Nó không nhất thiết là lỗi query; có thể là do cấu trúc storage nội bộ thay đổi.

### 9.3 Query có câu trả lời nhưng traversal stats rỗng

Có thể do:

- câu hỏi không đi qua flow local retrieval
- `retrieval_detail` không được populate đầy đủ trong `tgrag/src/core/querying.py`

---

## 10. Tóm tắt cuối

Nếu nhìn theo kiến trúc thực tế của repo, thì `demo.py` là:

- một **Streamlit client** cho `TemporalGraphRAG`
- đọc graph từ **`working_dir`**
- chạy **local query** để lấy `retrieval_detail`
- render traversal bằng **PyVis**

Vì vậy, để demo hoạt động trơn tru, bạn chỉ cần nhớ 3 thứ:

1. **Build xong graph trước**
2. **`working_dir` phải khớp**
3. **Query phải ở `local` mode**

Nếu bạn muốn, tài liệu tiếp theo mình có thể viết thêm là:

- `md/runbooks/demo_cli_quickstart.md` — bản siêu ngắn copy-paste,
- hoặc một bản **README demo cho người mới**.

## 11. Working directory provenance & exact artifact mapping (chi tiết hành động)

Phần này giải thích rõ ràng `working_dir` xuất phát từ đâu, file nào sẽ có trong nó sau khi build, và các bước cụ thể bạn cần làm (copy-paste) để build + chạy demo.

### 11.1 Từ đâu `working_dir` được định nghĩa

- `working_dir` có thể được đặt trong 3 nơi (ưu tiên theo thứ tự):
  1. Trực tiếp trong file config YAML (ví dụ `querying.working_dir` hoặc `building.working_dir`).
  2. Bị override bởi `override_config` khi gọi `create_temporal_graphrag_from_config(...)` (ví dụ demo UI truyền giá trị sidebar vào `override_config`).
  3. Tham số CLI khi gọi script build (nếu script hỗ trợ tham số `--output` / `--working_dir`).

Ví dụ trong `tgrag/configs/config_eval_ollama_nomic_fast.yaml` bạn đã thấy `working_dir: "./output_ollama_eval"` — đó là nơi build sẽ ghi artifact mặc định.

### 11.2 Những file artifact chính sẽ có trong `working_dir`

Kiểm tra sau khi build xong, bạn nên thấy (tên có thể khác đôi chút tùy config/phiên bản):

- `graph_chunk_entity_relation.graphml` — đồ thị chunk/entity/relation dùng để render subgraph.
- `graph_temporal_hierarchy.graphml` — (nếu bật) cấu trúc hierarchy/communities.
- `kv_store_full_docs.json` — metadata tài liệu gốc (source docs).
- `kv_store_text_chunks.json` — các chunk văn bản đã embedding.
- `kv_store_community_reports.json` — bản tóm tắt cộng đồng/cluster (nếu có).
- `vdb_entities.json` — danh sách entity đã extract và thuộc tính của chúng.
- `vdb_relations.json` — quan hệ giữa entities (temporal relations, edges).
- `index_*` / `embed_*` files — các chỉ mục embedding/kv store tùy backend (llama/turboquant/onnx...).

Lưu ý: tên file có thể có tiền tố/suffix tùy config; mục tiêu là kiểm tra file graph `*.graphml` và các `kv_store_*.json` / `vdb_*.json` tồn tại.

### 11.3 Kiểm tra nhanh `working_dir` sau khi build

Từ terminal, ở repository root:

```bash
# bật debug cho build (nếu muốn thấy log chi tiết)
export TG_RAG_DEBUG=true

# chạy build (ví dụ, từ script build_graph.py ở repo root)
python build_graph.py --config tgrag/configs/config_eval_ollama_nomic_fast.yaml

# sau khi build hoàn tất, kiểm tra folder
ls -la ./output_ollama_eval
# inspect các filenames
ls -la ./output_ollama_eval | egrep "graph|kv_store|vdb|index|embed"
```

Nếu bạn không thấy file `*.graphml` hoặc `kv_store_*.json` thì demo sẽ không render graph; quay lại bước build và kiểm tra logs trong `logs/build_graph/`.

### 11.4 Ví dụ hoàn chỉnh — build nhỏ và chạy demo

1) (Từ repo root) chuẩn bị env & server (nếu dùng local runtime):

```bash
# set runtime endpoints (thay theo backend của bạn)
export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=xxxx
export OLLAMA_BASE_URL=http://localhost:11434

# bật debug cho build nếu bạn cần verbose logs
export TG_RAG_DEBUG=true
```

2) Run build (sample):

```bash
python build_graph.py --config tgrag/configs/config_eval_ollama_nomic_fast.yaml
```

3) Confirm artifacts:

```bash
ls -la ./output_ollama_eval
```

4) Start LLM server if needed (example for local OpenAI-compatible):

```bash
# start your local LLM / turboquant-compatible server (external to this repo)
# e.g. start llama-server or your turboquant service per its docs
```

5) Run demo UI (Streamlit):

```bash
streamlit run demo.py
```

6) In the demo sidebar:

- `Config Path`: chọn `tgrag/configs/config_eval_ollama_nomic_fast.yaml` (hoặc file config bạn dùng).
- `Working Directory`: điền `./output_ollama_eval` (hoặc đường dẫn tương ứng đến folder bạn vừa build).
- `Provider/Model/Base URL`: chọn phù hợp với server đang chạy.

7) Nhấn `Run Query` và bật `Show Graph Visualization` nếu cần.

### 11.5 Nếu bạn muốn dùng Neo4j thay vì file artifacts

- Thêm `addon_params.neo4j_url` và `addon_params.neo4j_auth` vào config YAML hoặc truyền qua `override_config`.
- Khi `TemporalGraphRAG` được khởi tạo với `addon_params` chứa `neo4j` info thì storage layer sẽ dùng Neo4j thay vì load từ `working_dir`.
- Hiện `demo.py` không expose UI input cho `addon_params` — bạn có thể sửa `demo.py` để thêm 2 trường sidebar (`Neo4j URL`, `Neo4j Auth`) và truyền vào `override_config["addon_params"]`.

### 11.6 Kịch bản lỗi và cách debug nhanh

- Không thấy `graphml` trong `working_dir` → rerun build; kiểm tra `logs/build_graph/<last>.log`.
- `retrieval_detail` rỗng mặc dù artifact có mặt → kiểm tra `querying.mode` phải là `local` và `top_k` đủ lớn.
- Demo crash khi load graph → mở Python REPL và thử:

```python
from tgrag import create_temporal_graphrag_from_config
g = create_temporal_graphrag_from_config(config_path='tgrag/configs/config_eval_ollama_nomic_fast.yaml', override_config={'querying':{'working_dir':'./output_ollama_eval'}})
print(g.chunk_entity_relation_graph._graph)
```

Nếu object graph in ra ok, nguyên nhân crash có thể do rendering (pyvis / networkx) hoặc do trường dữ liệu thiếu.

### 11.7 Ghi chú kết thúc

Phần này cung cấp đủ thông tin thực hiện từ `build` → `verify artifacts` → `start demo`. Nếu bạn muốn, mình có thể:

- tạo file `md/runbooks/demo_cli_quickstart.md` với bản copy-paste ngắn gọn (1 trang) — mình thực hiện ngay nếu bạn đồng ý.
- hoặc mở rộng demo UI để expose `Neo4j` và `TG_RAG_DEBUG` toggle trong sidebar.

## 12. Gợi ý điền theo đúng hình bạn gửi

Với ảnh `LLM Settings` bạn gửi, cách hiểu thực tế như sau:

- **Provider**: chọn backend đang chạy.
  - Nếu bạn dùng TurboQuant server thì để `turboquant`.
- **Model**: điền tên model mà TurboQuant đang serve.
  - Không phải đường dẫn file model.
  - Không phải tên folder chứa model.
  - Là đúng tên model/API name mà server trả ra.
- **Base URL**: điền URL của server LLM.
  - Ví dụ: `http://localhost:8080/v1`
  - Đây là URL của API endpoint, không phải đường dẫn tới model.

Ví dụ nhanh cho TurboQuant local:

```text
Provider = turboquant
Model    = qwen3-14b (hoặc đúng model name server của bạn expose)
Base URL = http://localhost:8080/v1
```

Ví dụ nhanh cho Ollama:

```text
Provider = ollama
Model    = llama3.1
Base URL = http://localhost:11434
```

Ví dụ nhanh cho Gemini:

```text
Provider = gemini
Model    = gemini-2.5-flash-lite
Base URL = (để trống nếu không dùng proxy)
```

Nếu bạn muốn, mình có thể tiếp tục sửa `demo.py` để:

- auto-gợi ý `Base URL` theo provider,
- prefill `Model` theo provider,
- và hiển thị một dòng chú thích ngay dưới ô nhập để khỏi phải đoán nữa.

