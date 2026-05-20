# Temporal-GraphRAG (TG-RAG)

[![arXiv](https://img.shields.io/badge/arXiv-2510.13590-b31b1b.svg)](https://arxiv.org/abs/2510.13590)
[![Hugging Face Dataset](https://img.shields.io/badge/🤗%20Hugging%20Face-Dataset-yellow)](https://huggingface.co/datasets/austinmyc/ECT-QA)

Official implementation of **"RAG Meets Temporal Graphs: Time-Sensitive Modeling and Retrieval for Evolving Knowledge"**.

## Overview

Temporal-GraphRAG (TG-RAG) addresses the temporal blindness in conventional RAG systems by modeling knowledge as a bi-level temporal graph. This enables precise time-aware retrieval and efficient incremental updates as corpora evolve.

**Key Advantages:**
- 🕐 Explicit temporal fact representation
- 📊 Multi-granularity temporal summaries
- 🔄 Efficient incremental updates
- 🎯 Dynamic time-aware retrieval

## Installation

```bash
git clone https://github.com/hanjiale/Temporal-GraphRAG.git
cd Temporal-GraphRAG

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

**1. Set up API keys** (required for LLM and embedding providers):

```bash
# Create .env file or set environment variables
export OPENAI_API_KEY="your-openai-key-here"      # For OpenAI provider
export GOOGLE_API_KEY="your-google-key-here"      # For Gemini provider (or use GEMINI_API_KEY)
```

**2. Build and query:**

```bash
# Build a graph from documents
python build_graph.py --output_dir ./graph_output --corpus_path ./my_documents/

# Query the graph
python query_graph.py --question "Your question here" --working_dir ./graph_output --mode global
```



## Configurations

<details>
<summary><b>Entity Types</b></summary>

Customize which entity types are extracted by editing `tgrag/configs/prompts.yaml`:

```yaml
defaults:
  entity_types:
    - "financial concept"
    - "business segment"
    - "event"
    - "company"
    - "person"      
    - "product"
    - "location"
```

The system will only extract entities matching these configured types.

</details>

<details>
<summary><b>LLM and Embedding Providers</b></summary>

Configure in `tgrag/configs/config.yaml`:

```yaml
building:
  provider: "gemini"  # Options: openai, azure, bedrock, gemini, ollama
  model: "gemini-2.5-flash-lite"
  embedding_provider: "openai"
```

**Supported Providers:**
- **OpenAI** - Requires `OPENAI_API_KEY`
- **Azure OpenAI** - Requires Azure credentials (set via Azure SDK)
- **Amazon Bedrock** - Requires AWS credentials and `aioboto3`
- **Google Gemini** - Requires `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- **Ollama** - Requires local Ollama server (default: `http://localhost:11434`)

Set API keys via environment variables or `.env` file:
```bash
export OPENAI_API_KEY="your-key-here"
export GOOGLE_API_KEY="your-key-here"  # or GEMINI_API_KEY
```

</details>

## Usage Examples

<details>
<summary><b>Building the Graph</b></summary>

The `build_graph.py` script automatically detects input type:

**ECT-QA corpus (JSONL.gz):**
```bash
python build_graph.py --output_dir ./graph_output --corpus_path ./ect-qa/corpus/base.jsonl.gz --num_docs 10
```

**Single text file:**
```bash
python build_graph.py --output_dir ./graph_output --corpus_path ./my_document.txt
```

**Directory of text files (recursive):**
```bash
python build_graph.py --output_dir ./graph_output --corpus_path ./my_documents/
```

Supported text formats: `.txt`, `.md`, `.rst`, `.text`, `.log`, and files without extensions.

</details>

<details>
<summary><b>Query Modes</b></summary>

```bash
# Local mode - for specific facts
python query_graph.py --question "What was Company X's revenue in Q3 2023?" --mode local

# Global mode - for trends and summarization
python query_graph.py --question "How did tech companies navigate 2023 challenges?" --mode global

# Naive mode - simple RAG
python query_graph.py --question "What is artificial intelligence?" --mode naive
```

</details>

<details>
<summary><b>Python API Examples</b></summary>

```python
from tgrag import create_temporal_graphrag_from_config

# Build the graph
graph_rag = create_temporal_graphrag_from_config(
    config_path="tgrag/configs/config.yaml",
    config_type="building"
)

# Insert documents
graph_rag.insert([{"title": "Doc 1", "doc": "content..."}])

# Query the graph
graph_rag = create_temporal_graphrag_from_config(
    config_path="tgrag/configs/config.yaml",
    config_type="querying"
)
answer = graph_rag.query("Your question here", mode="global")
```

</details>


## ECT-QA Dataset

High-quality benchmark for time-sensitive question answering:

- **Corpus:** 480 earnings call transcripts (24 companies, 2020-2024)
- **Questions:** 1,005 specific + 100 abstract temporal queries

The dataset is also available on Hugging Face: [austinmyc/ECT-QA](https://huggingface.co/datasets/austinmyc/ECT-QA)

You can load it using:
```python
from datasets import load_dataset

# Load questions dataset
questions = load_dataset("austinmyc/ECT-QA", "questions")

# Load corpus dataset
corpus = load_dataset("austinmyc/ECT-QA", "corpus")
```


## Repository Structure
```
Temporal-GraphRAG/
├── tgrag/                          
│   ├── configs/                        
│   │   ├── config.yaml             # Main configuration
│   │   └── prompts.yaml            # prompts for indexing and querying
│   └── src/               
│       ├── temporal_graphrag.py    
│       └── ...  
├── ect-qa/                         # ECT-QA dataset               
│   ├── corpus/                     
│   │   ├── base.jsonl.gz           # 2020 - 2023
│   │   └── new.jsonl.gz            # 2024
│   └── questions/           
│       ├── local_base.jsonl 
│       ├── local_new.jsonl 
│       ├── global_base.jsonl 
│       └── global_new.jsonl    
├── graph_storage/
│   └── ...                         # Output graphs         
├── build_graph.py                  # Script to build knowledge graph
├── query_graph.py                  # Script to query the graph
├── requirements.txt                                      
├── README.md                       
├── LICENSE                         
└── .gitignore                      
```
## Citation

```bibtex
@article{han2025rag,
  title={RAG Meets Temporal Graphs: Time-Sensitive Modeling and Retrieval for Evolving Knowledge},
  author={Han, Jiale and Cheung, Austin and Wei, Yubai and Yu, Zheng and Wang, Xusheng and Zhu, Bing and Yang, Yi},
  journal={arXiv preprint arXiv:2510.13590},
  year={2025}
}
```

## Acknowledgments

Paper available at: [arXiv:2510.13590](https://arxiv.org/abs/2510.13590)

---

## Local Runbook: Gemini API + Ollama Embedding Baseline

Phần này là hướng dẫn chạy baseline local trên Ubuntu với:

- **LLM provider:** Gemini API
- **Embedding provider:** Ollama
- **Embedding model hiện tại:** `nomic-embed-text`
- **Graph output chính:** `./output_ollama`
- **Evaluation/result output:** `./results/output_ollama`

> Lưu ý: các lệnh dưới đây chạy từ thư mục root của repo.

### 1. Kích hoạt môi trường

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG
source venv/bin/activate
python --version
```

Kỳ vọng:

```text
Python 3.12.x
```

Nếu chưa cài dependencies:

```bash
python -m pip install -r requirements.txt
```

### 2. Kiểm tra `.env`

Repo tự load `.env` qua `python-dotenv`, nên chỉ cần bảo đảm file `.env` có key cần thiết:

```bash
GEMINI_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434
```

Có thể dùng `GOOGLE_API_KEY` thay cho `GEMINI_API_KEY`.

Không nên in API key ra terminal. Chỉ kiểm tra tên biến:

```bash
awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/ {print $1"=<set>"}' .env
```

### 3. Kiểm tra Ollama

Kiểm tra Ollama binary và server:

```bash
ollama --version
ollama list
curl http://localhost:11434/api/tags
```

Nếu Ollama chưa chạy:

```bash
ollama serve
```

Nếu thiếu embedding model:

```bash
ollama pull nomic-embed-text
```

Kiểm tra model có đúng embedding dimension `768`:

```bash
ollama show nomic-embed-text

curl -s http://localhost:11434/api/embed \
  -d '{"model":"nomic-embed-text","input":"smoke test"}' \
  | python -c 'import sys,json; d=json.load(sys.stdin); print(len(d["embeddings"][0]))'
```

Kỳ vọng:

```text
768
```

Không dùng `qwen3:14b` làm embedding model. Model này là completion model, không hỗ trợ embedding endpoint. Nếu muốn thử Qwen embedding, cần dùng dòng model embedding riêng như `qwen3-embedding`, đồng thời phải chỉnh code/config để truyền đúng `embedding_model` và `embedding_dim`, rồi build lại graph từ đầu.

### 4. Kiểm tra config hiện tại

File chính:

```bash
tgrag/configs/config.yaml
```

Các setting quan trọng:

```yaml
building:
  working_dir: "./output_ollama"
  provider: "gemini"
  model: "gemini-2.5-flash-lite"
  embedding_provider: "ollama"
  chunk_size: 1200
  chunk_overlap: 100
  enable_community_summary: true

querying:
  working_dir: "./output_ollama"
  provider: "gemini"
  model: "gemini-2.5-flash"
  embedding_provider: "ollama"
  mode: "local"
```

Command-line `--output_dir` và `--working_dir` sẽ override `working_dir` trong config, nên bạn có thể giữ graph cũ và build graph mới sang thư mục khác.

### 5. Corpus và questions nằm ở đâu

Corpus:

```text
ect-qa/corpus/base.jsonl.gz   # corpus base 2020-2023
ect-qa/corpus/new.jsonl.gz    # corpus update 2024
```

Đếm số document:

```bash
gzip -cd ect-qa/corpus/base.jsonl.gz | wc -l
gzip -cd ect-qa/corpus/new.jsonl.gz | wc -l
```

Questions:

```text
ect-qa/questions/local_base.jsonl    # Specific QA trên base corpus
ect-qa/questions/local_new.jsonl     # Specific QA cho new/update corpus
ect-qa/questions/global_base.jsonl   # Abstract QA trên base corpus
ect-qa/questions/global_new.jsonl    # Abstract QA cho new/update corpus
```

Đọc thử câu hỏi:

```bash
sed -n '1p' ect-qa/questions/local_base.jsonl | python -m json.tool
sed -n '1p' ect-qa/questions/global_base.jsonl | python -m json.tool
```

### 6. Build smoke test trước

Không nên build full ngay. Chạy 3 documents trước để kiểm tra Gemini + Ollama + graph pipeline:

```bash
mkdir -p results/output_ollama_smoke
export TG_RAG_USAGE_LOG=results/output_ollama_smoke/build_usage.jsonl

python build_graph.py \
  --output_dir ./output_ollama_smoke \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 3
```

Trong lúc chạy, terminal sẽ hiển thị timing theo stage, ví dụ:

```text
[timer] initialize TemporalGraphRAG: ...
[build-stage] new documents: ...
[build-stage] new chunks: ...
[build-stage] document hashing + chunking: ...
[build-stage] entity extraction started
... Processed X(Y%) chunks ...
[build-stage] entity extraction + graph/vector upserts: ...
[build-stage] temporal hierarchy build: ...
[build-stage] community report generation: ...
[build-stage] persist all storages: ...
```

Ý nghĩa stage:

- `document hashing + chunking`: hash document và chia chunk.
- `entity extraction + graph/vector upserts`: gọi LLM để extract entity/relation, build graph, tạo embedding entity/relation.
- `temporal hierarchy build`: dựng hierarchy thời gian.
- `community report generation`: tạo temporal/community summaries bằng LLM.
- `persist all storages`: ghi JSON/GraphML/vector DB xuống disk.

Tóm tắt token usage nếu đã set `TG_RAG_USAGE_LOG`:

```bash
python scripts/eval/summarize_usage.py \
  --usage_log results/output_ollama_smoke/build_usage.jsonl
```

### 7. Inspect graph output

Sau smoke build:

```bash
python scripts/eval/inspect_graph_output.py \
  --working_dir ./output_ollama_smoke
```

Hoặc xem raw files:

```bash
find output_ollama_smoke -maxdepth 1 -type f | sort
du -sh output_ollama_smoke
```

Các file kết quả quan trọng:

```text
kv_store_full_docs.json
```

Document gốc đã ingest. Mỗi record thường có `doc` và `title`.

```text
kv_store_text_chunks.json
```

Các chunk sau khi chia nhỏ. Đây là text unit dùng để retrieval và evidence.

```text
kv_store_llm_response_cache.json
```

Cache response LLM. Nếu query/build lại với cùng prompt, cache có thể giảm API call.

```text
kv_store_community_reports.json
```

Community/temporal summaries dùng cho global/local context.

```text
graph_chunk_entity_relation.graphml
```

Graph entity-relation chính. Có thể đọc bằng NetworkX.

```text
graph_temporal_hierarchy.graphml
```

Graph hierarchy theo thời gian.

```text
vdb_entities.json
vdb_entities_new.json
vdb_relations.json
vdb_chunks.json
```

Vector DB dạng JSON. Mỗi file có `data` và `embeddings`. Với `nomic-embed-text`, embedding dimension phải là `768`.

Đọc nhanh vector DB:

```bash
python - <<'PY'
import json
from pathlib import Path

p = Path("output_ollama_smoke/vdb_entities.json")
data = json.loads(p.read_text())
print("rows:", len(data.get("data", {})))
print("embeddings:", len(data.get("embeddings", {})))
first_id = next(iter(data["embeddings"]))
print("embedding dim:", len(data["embeddings"][first_id]))
print("first metadata:", data["data"].get(first_id))
PY
```

Đọc graph:

```bash
python - <<'PY'
import networkx as nx

g = nx.read_graphml("output_ollama_smoke/graph_chunk_entity_relation.graphml")
print("nodes:", g.number_of_nodes())
print("edges:", g.number_of_edges())

for node, attrs in list(g.nodes(data=True))[:5]:
    print("NODE:", node, attrs)

for src, dst, attrs in list(g.edges(data=True))[:5]:
    print("EDGE:", src, "->", dst, attrs)
PY
```

### 8. Query smoke graph

Chạy một câu local query:

```bash
mkdir -p results/output_ollama_smoke
export TG_RAG_USAGE_LOG=results/output_ollama_smoke/query_usage.jsonl

python query_graph.py \
  --working_dir ./output_ollama_smoke \
  --mode local \
  --show_retrieval \
  --question "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?"
```

Nếu muốn lưu output terminal:

```bash
python query_graph.py \
  --working_dir ./output_ollama_smoke \
  --mode local \
  --question "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?" \
  | tee results/output_ollama_smoke/query_single.txt
```

Query timing sẽ hiển thị:

```text
[query-stage] load temporal hierarchy: ...
[query-stage] local retrieval + answer generation: ...
[query-stage] persist query cache: ...
[timer] run query: ...
```

Tóm tắt query token usage:

```bash
python scripts/eval/summarize_usage.py \
  --usage_log results/output_ollama_smoke/query_usage.jsonl
```

### 9. Build full base graph

Sau khi smoke pass, build full base corpus vào `output_ollama`.

```bash
mkdir -p results/output_ollama
export TG_RAG_USAGE_LOG=results/output_ollama/build_usage.jsonl

python build_graph.py \
  --output_dir ./output_ollama \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 384
```

Quan trọng: `build_graph.py` mặc định `--num_docs 3`, nên phải truyền `--num_docs 384` nếu muốn build toàn bộ base corpus.

Inspect full graph:

```bash
python scripts/eval/inspect_graph_output.py \
  --working_dir ./output_ollama

python scripts/eval/summarize_usage.py \
  --usage_log results/output_ollama/build_usage.jsonl
```

### 10. Query full graph

Local/specific query:

```bash
python query_graph.py \
  --working_dir ./output_ollama \
  --mode local \
  --question "In which quarter did EPAM Systems Inc. have the lowest GAAP gross margin from 2021 to mid-2022?"
```

Global/abstract query:

```bash
python query_graph.py \
  --working_dir ./output_ollama \
  --mode global \
  --question "How did major companies describe revenue growth and margin pressure across 2022?"
```

### 11. Batch query để tạo prediction files

Specific QA trên base questions:

```bash
mkdir -p results/output_ollama

python scripts/eval/run_batch_queries.py \
  --working_dir ./output_ollama \
  --questions ect-qa/questions/local_base.jsonl \
  --mode local \
  --output results/output_ollama/local_base_predictions.jsonl
```

Test trước 10 câu:

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir ./output_ollama \
  --questions ect-qa/questions/local_base.jsonl \
  --mode local \
  --output results/output_ollama/local_base_predictions_test.jsonl \
  --limit 10
```

Resume nếu bị ngắt:

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir ./output_ollama \
  --questions ect-qa/questions/local_base.jsonl \
  --mode local \
  --output results/output_ollama/local_base_predictions.jsonl \
  --resume
```

Abstract/global QA:

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir ./output_ollama \
  --questions ect-qa/questions/global_base.jsonl \
  --mode global \
  --output results/output_ollama/global_base_predictions.jsonl
```

Mỗi dòng trong prediction JSONL gồm:

```json
{
  "question": "...",
  "answer": "...",
  "evidence_list": [],
  "prediction": "...",
  "elapsed_seconds": 12.345,
  "mode": "local",
  "status": "ok"
}
```

### 12. Evaluate Specific QA

Specific QA dùng:

- `local_base.jsonl`
- `local_new.jsonl`

Non-LLM metrics: ROUGE-L và token F1.

```bash
python scripts/eval/metrics_nonllm.py \
  --predictions results/output_ollama/local_base_predictions.jsonl \
  --output results/output_ollama/local_base_nonllm_metrics.json
```

LLM judge metrics: Correct / Refusal / Incorrect.

Dùng Gemini judge:

```bash
python scripts/eval/judge_specific.py \
  --predictions results/output_ollama/local_base_predictions.jsonl \
  --output results/output_ollama/local_base_judge_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

Dùng OpenAI judge nếu muốn gần setting paper hơn:

```bash
python scripts/eval/judge_specific.py \
  --predictions results/output_ollama/local_base_predictions.jsonl \
  --output results/output_ollama/local_base_judge_gpt4omini.jsonl \
  --judge_provider openai \
  --judge_model gpt-4o-mini
```

Correct / Refusal / Incorrect được tính theo factual elements:

- `CORRECT`: đúng fact/value và đúng temporal scope.
- `REFUSAL`: model nói rõ không đủ evidence để trả lời element đó.
- `INCORRECT`: sai, unsupported, hallucinated, hoặc sai mốc thời gian.

Với mỗi query:

```text
Correct + Refusal + Incorrect = 1.0
```

### 13. Evaluate Abstract QA

Abstract QA dùng:

- `global_base.jsonl`
- `global_new.jsonl`

Abstract QA không có ground-truth answer cố định, nên dùng pairwise judge. Bạn cần 2 prediction files từ 2 hệ thống hoặc 2 embedding model khác nhau.

Ví dụ so sánh `nomic` với một graph khác tên `bge`:

```bash
python scripts/eval/judge_pairwise_abstract.py \
  --predictions_a results/output_ollama/global_base_predictions.jsonl \
  --predictions_b results/output_bge/global_base_predictions.jsonl \
  --name_a nomic \
  --name_b bge \
  --output results/pairwise/nomic_vs_bge_global_base.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

Judge trả winner theo:

- `comprehensiveness`
- `diversity`
- `temporal_coverage`
- `overall_winner`

Win rate:

```text
WinRate(A) = số lần A thắng / tổng số pairwise comparisons
```

### 14. Update corpus 2024

Base corpus:

```bash
python build_graph.py \
  --output_dir ./output_ollama_base \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 384
```

New corpus 2024:

```bash
python build_graph.py \
  --output_dir ./output_ollama_new_only \
  --corpus_path ect-qa/corpus/new.jsonl.gz \
  --num_docs 96
```

Nếu muốn nghiên cứu incremental update thật sự, cần kiểm tra và cấu hình thêm:

```yaml
enable_incremental: true
preserve_communities: true
```

Sau khi đổi corpus hoặc đổi embedding model, nên dùng `output_dir` mới để tránh trộn artifacts.

### 15. So sánh khi đổi embedding model

Quy tắc quan trọng:

1. Mỗi embedding model phải có graph output riêng.
2. Không reuse graph cũ nếu đổi embedding model.
3. Phải kiểm tra embedding dimension trước.
4. Phải chạy lại batch query và metrics trên cùng question files.

Ví dụ layout:

```text
output_ollama_nomic/
output_ollama_bge/
output_ollama_qwen3_embedding/

results/output_ollama_nomic/
results/output_ollama_bge/
results/output_ollama_qwen3_embedding/
```

Kiểm tra model trước khi dùng:

```bash
ollama pull bge-m3
ollama show bge-m3

curl -s http://localhost:11434/api/embed \
  -d '{"model":"bge-m3","input":"embedding dimension test"}' \
  | python -c 'import sys,json; d=json.load(sys.stdin); print(len(d["embeddings"][0]))'
```

Nếu dimension khác `768`, code/config phải được chỉnh tương ứng trước khi build. Nếu không, vector DB có thể sai dimension hoặc retrieval không đúng.

### 16. Troubleshooting

Nếu thiếu Gemini key:

```text
API key not found for provider 'gemini'
```

Kiểm tra `.env`:

```bash
awk -F= '/GEMINI_API_KEY|GOOGLE_API_KEY/ {print $1"=<set>"}' .env
```

Nếu Ollama không reachable:

```text
Cannot connect to host localhost:11434
```

Chạy:

```bash
ollama serve
curl http://localhost:11434/api/tags
```

Nếu embedding model không tồn tại:

```bash
ollama pull nomic-embed-text
```

Nếu query local trả tuple và terminal in cả retrieval detail quá dài, bỏ `--show_retrieval`. Nếu muốn xem retrieval detail để debug, thêm:

```bash
--show_retrieval
```

Nếu build full quá lâu, chạy theo thứ tự:

```bash
--num_docs 3
--num_docs 10
--num_docs 50
--num_docs 384
```

Nếu muốn giảm chi phí Gemini trong lúc test, có thể tạm tắt community summary trong config:

```yaml
enable_community_summary: false
```

Sau đó bật lại khi chạy experiment chính thức.

### 17. Copy-Paste Checklist Chạy Từ Đầu Đến Evaluation

Phần này gom lại các lệnh theo đúng thứ tự thực chiến. Nếu bạn chỉ muốn chạy nhanh mà không đọc giải thích dài phía trên, copy theo checklist này.

#### 17.1. Environment check

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG
source venv/bin/activate

python --version
python -m pip list | rg "google-genai|aiohttp|networkx|numpy|openai|python-dotenv|PyYAML|hnswlib|nano-vectordb"
```

Kiểm tra `.env` không lộ secret:

```bash
awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/ {print $1"=<set>"}' .env
```

Kiểm tra Ollama:

```bash
ollama --version
ollama list
curl http://localhost:11434/api/tags
```

Kiểm tra embedding:

```bash
curl -s http://localhost:11434/api/embed \
  -d '{"model":"nomic-embed-text","input":"smoke test"}' \
  | python -c 'import sys,json; d=json.load(sys.stdin); print("embedding_dim =", len(d["embeddings"][0]))'
```

Kỳ vọng:

```text
embedding_dim = 768
```

#### 17.2. Smoke build 3 docs

```bash
mkdir -p results/output_ollama_smoke
export TG_RAG_USAGE_LOG=results/output_ollama_smoke/build_usage.jsonl

python build_graph.py \
  --output_dir ./output_ollama_smoke \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 3
```

Kết quả sẽ lưu ở:

```text
output_ollama_smoke/
results/output_ollama_smoke/build_usage.jsonl
```

Kiểm tra output:

```bash
python scripts/eval/inspect_graph_output.py \
  --working_dir ./output_ollama_smoke

python scripts/eval/summarize_usage.py \
  --usage_log results/output_ollama_smoke/build_usage.jsonl
```

#### 17.3. Smoke query

```bash
mkdir -p results/output_ollama_smoke
export TG_RAG_USAGE_LOG=results/output_ollama_smoke/query_usage.jsonl

python query_graph.py \
  --working_dir ./output_ollama_smoke \
  --mode local \
  --show_retrieval \
  --question "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?" \
  | tee results/output_ollama_smoke/query_single.txt

python scripts/eval/summarize_usage.py \
  --usage_log results/output_ollama_smoke/query_usage.jsonl
```

Kết quả sẽ lưu ở:

```text
results/output_ollama_smoke/query_single.txt
results/output_ollama_smoke/query_usage.jsonl
```

#### 17.4. Build full base graph

Chỉ chạy sau khi smoke build và smoke query đã ổn.

```bash
mkdir -p results/output_ollama
export TG_RAG_USAGE_LOG=results/output_ollama/build_usage.jsonl

python build_graph.py \
  --output_dir ./output_ollama \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 384
```

Kết quả graph full nằm ở:

```text
output_ollama/
```

Kết quả usage build nằm ở:

```text
results/output_ollama/build_usage.jsonl
```

Kiểm tra:

```bash
python scripts/eval/inspect_graph_output.py \
  --working_dir ./output_ollama

python scripts/eval/summarize_usage.py \
  --usage_log results/output_ollama/build_usage.jsonl
```

#### 17.5. Query full graph một câu

```bash
mkdir -p results/output_ollama
export TG_RAG_USAGE_LOG=results/output_ollama/query_usage.jsonl

python query_graph.py \
  --working_dir ./output_ollama \
  --mode local \
  --question "In which quarter did EPAM Systems Inc. have the lowest GAAP gross margin from 2021 to mid-2022?" \
  | tee results/output_ollama/query_epam_local.txt

python query_graph.py \
  --working_dir ./output_ollama \
  --mode global \
  --question "How did major companies describe revenue growth and margin pressure across 2022?" \
  | tee results/output_ollama/query_global_example.txt
```

Kết quả sẽ lưu ở:

```text
results/output_ollama/query_epam_local.txt
results/output_ollama/query_global_example.txt
results/output_ollama/query_usage.jsonl
```

#### 17.6. Batch query local/specific questions

Test 10 câu trước:

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir ./output_ollama \
  --questions ect-qa/questions/local_base.jsonl \
  --mode local \
  --output results/output_ollama/local_base_predictions_test.jsonl \
  --limit 10
```

Chạy toàn bộ local base:

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir ./output_ollama \
  --questions ect-qa/questions/local_base.jsonl \
  --mode local \
  --output results/output_ollama/local_base_predictions.jsonl
```

Nếu bị ngắt giữa chừng:

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir ./output_ollama \
  --questions ect-qa/questions/local_base.jsonl \
  --mode local \
  --output results/output_ollama/local_base_predictions.jsonl \
  --resume
```

Kết quả prediction nằm ở:

```text
results/output_ollama/local_base_predictions.jsonl
```

Xem 1 dòng prediction:

```bash
sed -n '1p' results/output_ollama/local_base_predictions.jsonl | python -m json.tool
```

#### 17.7. Batch query global/abstract questions

```bash
python scripts/eval/run_batch_queries.py \
  --working_dir ./output_ollama \
  --questions ect-qa/questions/global_base.jsonl \
  --mode global \
  --output results/output_ollama/global_base_predictions.jsonl
```

Kết quả prediction nằm ở:

```text
results/output_ollama/global_base_predictions.jsonl
```

#### 17.8. Evaluate local/specific predictions

ROUGE-L và F1:

```bash
python scripts/eval/metrics_nonllm.py \
  --predictions results/output_ollama/local_base_predictions.jsonl \
  --output results/output_ollama/local_base_nonllm_metrics.json
```

LLM judge bằng Gemini:

```bash
python scripts/eval/judge_specific.py \
  --predictions results/output_ollama/local_base_predictions.jsonl \
  --output results/output_ollama/local_base_judge_gemini.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

LLM judge bằng OpenAI, nếu muốn gần setup paper hơn:

```bash
python scripts/eval/judge_specific.py \
  --predictions results/output_ollama/local_base_predictions.jsonl \
  --output results/output_ollama/local_base_judge_gpt4omini.jsonl \
  --judge_provider openai \
  --judge_model gpt-4o-mini
```

Kết quả metric nằm ở:

```text
results/output_ollama/local_base_nonllm_metrics.json
results/output_ollama/local_base_judge_gemini.jsonl
results/output_ollama/local_base_judge_gpt4omini.jsonl
```

#### 17.9. Evaluate global/abstract predictions

Pairwise abstract evaluation cần 2 prediction files. Ví dụ sau khi bạn build một graph khác tên `output_bge` và có predictions ở `results/output_bge/global_base_predictions.jsonl`, chạy:

```bash
mkdir -p results/pairwise

python scripts/eval/judge_pairwise_abstract.py \
  --predictions_a results/output_ollama/global_base_predictions.jsonl \
  --predictions_b results/output_bge/global_base_predictions.jsonl \
  --name_a nomic \
  --name_b bge \
  --output results/pairwise/nomic_vs_bge_global_base.jsonl \
  --judge_provider gemini \
  --judge_model gemini-2.5-flash-lite
```

Kết quả nằm ở:

```text
results/pairwise/nomic_vs_bge_global_base.jsonl
```

#### 17.10. Nơi lưu toàn bộ kết quả

Sau khi chạy theo checklist, layout kết quả chính là:

```text
output_ollama_smoke/
  kv_store_full_docs.json
  kv_store_text_chunks.json
  kv_store_llm_response_cache.json
  kv_store_community_reports.json
  graph_chunk_entity_relation.graphml
  graph_temporal_hierarchy.graphml
  vdb_entities.json
  vdb_entities_new.json
  vdb_relations.json

output_ollama/
  kv_store_full_docs.json
  kv_store_text_chunks.json
  kv_store_llm_response_cache.json
  kv_store_community_reports.json
  graph_chunk_entity_relation.graphml
  graph_temporal_hierarchy.graphml
  vdb_entities.json
  vdb_entities_new.json
  vdb_relations.json

results/output_ollama_smoke/
  build_usage.jsonl
  query_usage.jsonl
  query_single.txt

results/output_ollama/
  build_usage.jsonl
  query_usage.jsonl
  query_epam_local.txt
  query_global_example.txt
  local_base_predictions.jsonl
  global_base_predictions.jsonl
  local_base_nonllm_metrics.json
  local_base_judge_gemini.jsonl
```

Nếu đổi embedding model, đổi cả output graph và result folder, ví dụ:

```bash
python build_graph.py \
  --output_dir ./output_ollama_bge \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 384

python scripts/eval/run_batch_queries.py \
  --working_dir ./output_ollama_bge \
  --questions ect-qa/questions/local_base.jsonl \
  --mode local \
  --output results/output_ollama_bge/local_base_predictions.jsonl
```

Không trộn output của hai embedding model trong cùng một folder.

## Kiểm Tra Local TurboQuant LLM

Repo này vẫn có thể dùng Gemini theo cấu hình mặc định trong `tgrag/configs/config.yaml`. Tuy nhiên, nếu mục tiêu là benchmark TurboQuant thì phải ép rõ chat LLM đi qua `llama-server` local. Dòng healthcheck TurboQuant chỉ chứng minh endpoint `/props` đang sống; nó không chứng minh build graph thật sự gọi local model. Bằng chứng đúng phải kiểm bằng hai nơi: cache `kv_store_llm_response_cache.json` và log request của `llama-server`.

Trong chế độ TurboQuant, source dùng `provider=openai` vì `llama-server` expose API theo chuẩn OpenAI-compatible `/v1`. Đây là giao thức local, không phải OpenAI cloud, miễn là `base_url` trỏ về `http://localhost:8080/v1`.

Quy ước thư mục trong phần này:

| Loại file | Vị trí | Lý do |
|---|---|---|
| Graph output | `outputs/<case_name>` | Tên cố định theo case, dễ so sánh và không làm rối root repo. |
| Log chạy | `logs/<case_name>_${RUN_ID}.txt` | Giữ lịch sử từng lần chạy, không ghi đè log cũ. |
| Cache LLM | `outputs/<case_name>/kv_store_llm_response_cache.json` | Dùng để xác nhận model LLM thật sự đã được gọi. |

Lưu ý benchmark: nếu muốn đo fresh run, hãy dùng output folder mới hoặc xóa output folder của case đó trước khi chạy lại. Nếu chạy lại trên cùng `outputs/<case_name>`, GraphRAG có thể reuse cache/skip document đã có, làm thời gian không còn đại diện cho build mới.

### Terminal 1: Start llama-server với alias cố định

Alias phải khớp với giá trị truyền vào `--model` khi build graph. Ví dụ dưới đây load model GGUF Qwen2.5 7B Q8 và đặt alias là `qwen2.5-7b-instruct-q8-turbo3`.

```bash
conda activate turboquant

export RUN_ID=$(date +%Y%m%d_%H%M%S)
echo "RUN_ID=${RUN_ID}"

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs
export SERVER_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server_qwen25_7b_q8_turbo3_${RUN_ID}.txt
echo "SERVER_LOG=${SERVER_LOG}"

cd /home/guest/Projects/Research/llama-cpp-turboquant

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen2.5-7b-instruct-q8-turbo3 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --log-file ${SERVER_LOG}
```

Giữ terminal này mở. Nếu tắt terminal này thì build với `--local_llm_backend turboquant` sẽ fail sớm ở bước healthcheck.

Ghi lại giá trị `RUN_ID` được in ra, ví dụ `RUN_ID=20260520_151152`. Biến môi trường không tự truyền qua terminal khác, nên Terminal 2 phải set lại đúng giá trị này nếu muốn tên log server và log build khớp nhau.

### Terminal 2: Build 1 document qua local TurboQuant

Lệnh này ép build graph dùng local `llama-server` cho phần LLM extract/summarize, còn embedding vẫn dùng Ollama ở `http://localhost:11434`.

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

# Copy đúng RUN_ID đã được in ở Terminal 1.
export RUN_ID=copy_RUN_ID_from_terminal_1_here

mkdir -p outputs logs
export CASE=verify_qwen25_7b_turboquant_1doc
export OUT=outputs/${CASE}
export BUILD_LOG=logs/build_${CASE}_${RUN_ID}.txt
export SERVER_LOG=logs/llama_server_qwen25_7b_q8_turbo3_${RUN_ID}.txt

echo "OUT=${OUT}"
echo "BUILD_LOG=${BUILD_LOG}"
echo "SERVER_LOG=${SERVER_LOG}"

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --local_llm_backend turboquant \
  --model qwen2.5-7b-instruct-q8-turbo3 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --output_dir ./${OUT} \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 1 \
  2>&1 | tee ${BUILD_LOG}
```

Ý nghĩa các tham số quan trọng:

| Tham số | Ý nghĩa |
|---|---|
| `--local_llm_backend turboquant` | Bật chế độ local LLM qua `llama-server`. |
| `--model qwen2.5-7b-instruct-q8-turbo3` | Tên alias model đang được `llama-server` expose. |
| `--base_url http://localhost:8080/v1` | Endpoint OpenAI-compatible local của `llama-server`. |
| `--embedding_provider ollama` | Embedding vẫn dùng Ollama, không dùng Gemini. |
| `--embedding_base_url http://localhost:11434` | Endpoint Ollama embedding. |
| `--llm_max_async 1` | Giới hạn client chỉ gửi 1 request LLM đồng thời để ổn định khi build. |
| `--llm_timeout 600` | Timeout mỗi request LLM là 600 giây, tránh bị cắt sớm khi local model sinh lâu. |
| `--output_dir ./outputs/verify_qwen25_7b_turboquant_1doc` | Lưu graph vào folder cố định theo case. |

### Kiểm Tra Backend Thật Sự Đã Dùng

Sau khi build xong, kiểm cache LLM:

```bash
python - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ['OUT']) / "kv_store_llm_response_cache.json"
data = json.loads(p.read_text())
models = {}
for v in data.values():
    if isinstance(v, dict):
        models[v.get("model")] = models.get(v.get("model"), 0) + 1
print(models)
PY
```

Kết quả đúng phải có dạng:

```text
{'qwen2.5-7b-instruct-q8-turbo3': ...}
```

Nếu cache hiện `gemini-2.5-flash-lite`, nghĩa là build đã dùng Gemini và chưa benchmark đúng local TurboQuant LLM.

Kiểm thêm log server và timer build:

```bash
grep -E "POST /v1/chat/completions" ${SERVER_LOG}
grep -E "\[build-stage\]|\[build-detail\]|\[timer\] insert documents" ${BUILD_LOG}
```

Dòng `POST /v1/chat/completions` trong log server chứng minh request LLM đã đi vào `llama-server`. Các dòng `[build-stage]` và `[build-detail]` dùng để xác định thời gian tốn ở bước nào: chunk extraction, vector embedding, community report, hoặc persist storage.

### Nếu Không Bật TurboQuant Thì Chạy Như Thế Nào?

Nếu không truyền `--local_llm_backend`, script không tự dùng TurboQuant. Khi đó build/query đọc `provider` và `model` từ `tgrag/configs/config.yaml`. Với cấu hình hiện tại của repo cũ, build mặc định là Gemini cho LLM extract/summarize và Ollama cho embedding.

Nói ngắn gọn:

| Cách chạy | LLM extract/summarize | Embedding | Có dùng `llama-server` không? | Terminal cần mở | Dùng khi nào |
|---|---|---|---|---|---|
| Không truyền backend | Theo `tgrag/configs/config.yaml`, hiện là Gemini | Theo config, hiện là Ollama | Không, trừ khi config trỏ OpenAI-compatible local | Terminal build/query + Ollama nếu embedding local | Baseline theo config cũ. |
| `--provider gemini --model ...` | Gemini explicit | Ollama nếu truyền `--embedding_provider ollama` | Không | Terminal build/query + Ollama nếu embedding local | Baseline cloud/API rõ ràng. |
| `--local_llm_backend ollama` | Ollama native, ví dụ `qwen3:14b` | Ollama | Không | Terminal Ollama + Terminal build/query | So sánh local LLM không TurboQuant. |
| `--local_llm_backend turboquant` | `llama-server` local qua OpenAI-compatible `/v1` | Ollama | Có | Terminal `llama-server` + Terminal Ollama + Terminal build/query | Benchmark TurboQuant local LLM. |

Điểm quan trọng: `llama-server` có đang chạy cũng không làm build tự dùng TurboQuant. Muốn dùng TurboQuant thật phải truyền `--local_llm_backend turboquant` hoặc cấu hình provider/base URL tương đương.

### Quy Ước Log Cho Các Case So Sánh

Mỗi case nên có:

| Biến | Ví dụ | Ý nghĩa |
|---|---|---|
| `CASE` | `compare_turboquant_qwen25_7b_1doc` | Tên case cố định, dùng cho output và log. |
| `OUT` | `outputs/${CASE}` | Folder graph output. |
| `BUILD_LOG` | `logs/build_${CASE}_${RUN_ID}.txt` | Log build graph. |
| `QUERY_LOG` | `logs/query_${CASE}_${RUN_ID}.txt` | Log query graph. |
| `SERVER_LOG` | `logs/llama_server_qwen25_7b_q8_turbo3_${RUN_ID}.txt` | Log `llama-server`, chỉ có ở case TurboQuant. |

`RUN_ID` dùng để log không bị ghi đè. `OUT` cố định theo case để dễ tìm graph. Nếu cần fresh benchmark, hãy xóa `OUT` trước khi build lại hoặc đổi `CASE` mới.

### Terminal Ollama: Dùng Cho Embedding Và Case Ollama Native

Các case trong repo này thường dùng Ollama embedding ở `http://localhost:11434`. Nếu Ollama chưa chạy, mở terminal riêng:

```bash
ollama serve
```

Kiểm model embedding và model chat local:

```bash
ollama list
ollama pull nomic-embed-text
ollama pull qwen3:14b
```

### Kịch Bản Build 1 Document Để So Sánh

Chạy các lệnh dưới đây ở terminal repo chính:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export RUN_ID=$(date +%Y%m%d_%H%M%S)
echo "RUN_ID=${RUN_ID}"

mkdir -p outputs logs
export OLLAMA_BASE_URL=http://localhost:11434
```

#### Case 1: Baseline Theo Config Mặc Định

Lệnh này không bật TurboQuant. Nó đọc `building.provider` và `building.model` trong `tgrag/configs/config.yaml`.

```bash
export CASE=compare_config_default_1doc
export OUT=outputs/${CASE}
export BUILD_LOG=logs/build_${CASE}_${RUN_ID}.txt

python -u build_graph.py \
  --output_dir ./${OUT} \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 1 \
  2>&1 | tee ${BUILD_LOG}
```

Kiểm model thật sự được dùng trong cache:

```bash
python - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ['OUT']) / "kv_store_llm_response_cache.json"
data = json.loads(p.read_text())
models = {}
for v in data.values():
    if isinstance(v, dict):
        models[v.get("model")] = models.get(v.get("model"), 0) + 1
print(models)
PY
```

#### Case 2: Gemini Explicit + Ollama Embedding

Dùng khi cần baseline cloud/API rõ ràng, không phụ thuộc config mặc định. Case này không cần `llama-server`, nhưng cần Gemini key hợp lệ trong `.env` hoặc môi trường.

```bash
export CASE=compare_gemini_ollama_embed_1doc
export OUT=outputs/${CASE}
export BUILD_LOG=logs/build_${CASE}_${RUN_ID}.txt

python -u build_graph.py \
  --provider gemini \
  --model gemini-2.5-flash-lite \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --output_dir ./${OUT} \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 1 \
  2>&1 | tee ${BUILD_LOG}
```

#### Case 3: Local Ollama LLM Không TurboQuant + Ollama Embedding

Dùng để so sánh local LLM native trước khi bật TurboQuant. Case này cần `ollama serve`, không cần `llama-server`.

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export CASE=compare_ollama_qwen3_14b_1doc
export OUT=outputs/${CASE}
export BUILD_LOG=logs/build_${CASE}_${RUN_ID}.txt

python -u build_graph.py \
  --local_llm_backend ollama \
  --model qwen3:14b \
  --base_url http://localhost:11434 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --output_dir ./${OUT} \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 1 \
  2>&1 | tee ${BUILD_LOG}
```

Nếu local Ollama bị chậm hoặc fail chunk, đó là kết quả benchmark của backend Ollama native, không phải lỗi TurboQuant.

#### Case 4: Local TurboQuant LLM + Ollama Embedding

Case này cần `llama-server` ở Terminal 1 và Ollama ở `http://localhost:11434`. Alias trong `--model` phải khớp với `--alias` của server.

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export CASE=compare_turboquant_qwen25_7b_1doc
export OUT=outputs/${CASE}
export BUILD_LOG=logs/build_${CASE}_${RUN_ID}.txt

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --local_llm_backend turboquant \
  --model qwen2.5-7b-instruct-q8-turbo3 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --output_dir ./${OUT} \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 1 \
  2>&1 | tee ${BUILD_LOG}
```

Kiểm nhanh thời gian, lỗi chunk, và backend thật:

```bash
grep -E "\[build-detail\] chunk LLM extraction|\[build-stage\] community report generation|\[timer\] insert documents" logs/build_*_1doc_${RUN_ID}.txt
grep -c "Failed to process chunk" logs/build_*_1doc_${RUN_ID}.txt

python - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ['OUT']) / "kv_store_llm_response_cache.json"
data = json.loads(p.read_text())
models = {}
for v in data.values():
    if isinstance(v, dict):
        models[v.get("model")] = models.get(v.get("model"), 0) + 1
print(models)
PY
```

Với case TurboQuant, kiểm thêm server log:

```bash
grep -E "POST /v1/chat/completions" logs/llama_server_qwen25_7b_q8_turbo3_${RUN_ID}.txt
```


### Bộ 4 Case Benchmark 1-doc Đầy Đủ

Bộ này dùng để tách hai loại so sánh:

| Nhóm so sánh | Case | Ý nghĩa |
|---|---|---|
| Công bằng về TurboQuant | Case 1 và Case 2 | Cùng GGUF Qwen2.5 7B Q8, cùng `llama-server`, chỉ đổi KV cache `ctv=turbo3` vs `ctv=q8_0`. |
| Thực dụng theo backend | Case 3 và Case 4 | So sánh local Ollama Qwen3 14B và Gemini baseline. Không dùng để kết luận riêng tác động TurboQuant vì model/runtime khác nhau. |

Tất cả case dưới đây dùng cùng embedding Ollama ở `http://localhost:11434`, mặc định là `nomic-embed-text` trong source/config hiện tại.

#### Setup Chung

Terminal Ollama:

```bash
ollama serve
```

Terminal repo:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export RUN_ID=$(date +%Y%m%d_%H%M%S)
echo "RUN_ID=${RUN_ID}"

mkdir -p outputs logs
export OLLAMA_BASE_URL=http://localhost:11434

ollama list
ollama pull nomic-embed-text
```

#### Case 1: Qwen2.5 7B Q8 Có TurboQuant KV

Terminal server:

```bash
conda activate turboquant

export RUN_ID=copy_or_create_RUN_ID_here
export SERVER_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server_qwen25_7b_q8_turbo3_${RUN_ID}.txt

cd /home/guest/Projects/Research/llama-cpp-turboquant

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen2.5-7b-instruct-q8-turbo3 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 1 \
  --log-file ${SERVER_LOG}
```

Terminal build:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export RUN_ID=copy_RUN_ID_from_server_terminal
export CASE=test_turboquant_qwen25_7b_turbo3_1doc
export OUT=outputs/${CASE}
export BUILD_LOG=logs/build_${CASE}_${RUN_ID}.txt
export TG_RAG_USAGE_LOG=logs/usage_${CASE}_${RUN_ID}.jsonl

mkdir -p outputs logs

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --local_llm_backend turboquant \
  --model qwen2.5-7b-instruct-q8-turbo3 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --output_dir ./${OUT} \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 1 \
  2>&1 | tee ${BUILD_LOG}
```

Sau khi xong, dừng server bằng `Ctrl+C` trước khi chạy Case 2 để giải phóng VRAM.

#### Case 2: Qwen2.5 7B Q8 Không TurboQuant KV

Case này dùng cùng GGUF Qwen2.5 7B Q8 nhưng KV cache baseline `K=q8_0`, `V=q8_0`. Đây là baseline công bằng để đo tác động của TurboQuant.

Terminal server:

```bash
conda activate turboquant

export RUN_ID=copy_or_create_RUN_ID_here
export SERVER_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server_qwen25_7b_q8_baseline_${RUN_ID}.txt

cd /home/guest/Projects/Research/llama-cpp-turboquant

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen2.5-7b-instruct-q8-baseline \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv q8_0 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 1 \
  --log-file ${SERVER_LOG}
```

Nếu OOM với `-c 32768`, giảm context runtime xuống:

```bash
-c 8192
```

Terminal build:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export RUN_ID=copy_RUN_ID_from_server_terminal
export CASE=test_baseline_qwen25_7b_q8_1doc
export OUT=outputs/${CASE}
export BUILD_LOG=logs/build_${CASE}_${RUN_ID}.txt
export TG_RAG_USAGE_LOG=logs/usage_${CASE}_${RUN_ID}.jsonl

mkdir -p outputs logs

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --provider openai \
  --model qwen2.5-7b-instruct-q8-baseline \
  --base_url http://localhost:8080/v1 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --output_dir ./${OUT} \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 1 \
  2>&1 | tee ${BUILD_LOG}
```

Ghi chú: case này vẫn dùng `--provider openai` vì `llama-server` expose OpenAI-compatible `/v1`. Nó không phải OpenAI cloud vì `--base_url` trỏ localhost.

#### Case 3: Ollama Qwen3 14B Native Không TurboQuant

Case này dùng local Ollama Qwen3 14B. Đây là baseline thực dụng, không cùng model weights với Qwen2.5 GGUF.

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export RUN_ID=$(date +%Y%m%d_%H%M%S)
export CASE=test_ollama_qwen3_14b_native_1doc
export OUT=outputs/${CASE}
export BUILD_LOG=logs/build_${CASE}_${RUN_ID}.txt
export TG_RAG_USAGE_LOG=logs/usage_${CASE}_${RUN_ID}.jsonl

mkdir -p outputs logs

ollama list
ollama pull nomic-embed-text
ollama pull qwen3:14b

export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --local_llm_backend ollama \
  --model qwen3:14b \
  --base_url http://localhost:11434 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --output_dir ./${OUT} \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 1 \
  2>&1 | tee ${BUILD_LOG}
```

#### Case 4: Gemini Baseline + Ollama Embedding

Case này không cần `llama-server`. TurboQuant không giúp gì cho Gemini vì LLM extract/summarize đi qua Gemini API.

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export RUN_ID=$(date +%Y%m%d_%H%M%S)
export CASE=test_gemini_flash_lite_ollama_embed_1doc
export OUT=outputs/${CASE}
export BUILD_LOG=logs/build_${CASE}_${RUN_ID}.txt
export TG_RAG_USAGE_LOG=logs/usage_${CASE}_${RUN_ID}.jsonl

mkdir -p outputs logs

ollama list
ollama pull nomic-embed-text

export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --provider gemini \
  --model gemini-2.5-flash-lite \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --output_dir ./${OUT} \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 1 \
  2>&1 | tee ${BUILD_LOG}
```

#### Kiểm Kết Quả Chung Cho Mỗi Case

Sau mỗi build, chạy:

```bash
grep -c "Failed to process chunk" ${BUILD_LOG}
grep -E "\[build-detail\] chunk LLM extraction|\[build-stage\] community report generation|\[timer\] insert documents" ${BUILD_LOG}

python - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ["OUT"]) / "kv_store_llm_response_cache.json"
data = json.loads(p.read_text())
models = {}
for v in data.values():
    if isinstance(v, dict):
        models[v.get("model")] = models.get(v.get("model"), 0) + 1
print(models)
PY
```

Kỳ vọng cache theo case:

| Case | Cache model kỳ vọng |
|---|---|
| TurboQuant Qwen2.5 | `qwen2.5-7b-instruct-q8-turbo3` |
| Baseline Qwen2.5 không TurboQuant | `qwen2.5-7b-instruct-q8-baseline` |
| Ollama Qwen3 14B | `qwen3:14b` |
| Gemini baseline | `gemini-2.5-flash-lite` |

Với các case `llama-server`, kiểm thêm server log:

```bash
grep -E "POST /v1/chat/completions" ${SERVER_LOG}
```

### Kịch Bản Query Sau Khi Build

Query phải dùng cùng backend LLM với graph build nếu muốn benchmark nhất quán. Query cũng cần log riêng để đọc lại output, retrieval detail, lỗi request, và timer.

Chạy setup chung trước:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

# Dùng RUN_ID hiện tại hoặc tạo mới cho lượt query.
export RUN_ID=${RUN_ID:-$(date +%Y%m%d_%H%M%S)}
mkdir -p logs

export QUESTION="In which quarter did EPAM Systems Inc. have the lowest GAAP gross margin from 2021 to mid-2022?"
export OLLAMA_BASE_URL=http://localhost:11434
```

#### Query Case 1: Graph Config Default

```bash
export CASE=compare_config_default_1doc
export OUT=outputs/${CASE}
export QUERY_LOG=logs/query_${CASE}_${RUN_ID}.txt

python -u query_graph.py \
  --working_dir ./${OUT} \
  --mode local \
  --question "$QUESTION" \
  2>&1 | tee ${QUERY_LOG}
```

#### Query Case 2: Graph Gemini Explicit

```bash
export CASE=compare_gemini_ollama_embed_1doc
export OUT=outputs/${CASE}
export QUERY_LOG=logs/query_${CASE}_${RUN_ID}.txt

python -u query_graph.py \
  --provider gemini \
  --model gemini-2.5-flash \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --working_dir ./${OUT} \
  --mode local \
  --question "$QUESTION" \
  2>&1 | tee ${QUERY_LOG}
```

#### Query Case 3: Graph Ollama Native

```bash
export CASE=compare_ollama_qwen3_14b_1doc
export OUT=outputs/${CASE}
export QUERY_LOG=logs/query_${CASE}_${RUN_ID}.txt

python -u query_graph.py \
  --local_llm_backend ollama \
  --model qwen3:14b \
  --base_url http://localhost:11434 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --working_dir ./${OUT} \
  --mode local \
  --question "$QUESTION" \
  2>&1 | tee ${QUERY_LOG}
```

#### Query Case 4: Graph TurboQuant

```bash
export CASE=compare_turboquant_qwen25_7b_1doc
export OUT=outputs/${CASE}
export QUERY_LOG=logs/query_${CASE}_${RUN_ID}.txt

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u query_graph.py \
  --local_llm_backend turboquant \
  --model qwen2.5-7b-instruct-q8-turbo3 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --working_dir ./${OUT} \
  --mode local \
  --question "$QUESTION" \
  2>&1 | tee ${QUERY_LOG}
```

Kiểm query logs:

```bash
grep -E "\[query-detail\]|\[timer\]|ERROR|Exception" logs/query_compare_*_1doc_${RUN_ID}.txt
```

### Bảng Tham Số CLI Cho Build Và Query

| Tham số | Dùng ở đâu | Ý nghĩa | Khi nào dùng | Mặc định nếu không truyền |
|---|---|---|---|---|
| `--local_llm_backend turboquant` | Build/query | Ép LLM đi qua local `llama-server` OpenAI-compatible `/v1`. | Benchmark TurboQuant. | Không tự bật. |
| `--local_llm_backend ollama` | Build/query | Ép LLM đi qua Ollama native API. | Benchmark local LLM không TurboQuant. | Không tự bật. |
| `--provider` | Build/query | Override provider trực tiếp, ví dụ `gemini`, `openai`, `ollama`. | Khi muốn chạy explicit theo provider thay vì local backend shortcut. | Đọc từ config. |
| `--model` | Build/query | Tên model hoặc alias. Với TurboQuant phải khớp `llama-server --alias`. | Khi đổi model/alias. | TurboQuant: `qwen2.5-7b-instruct-q8-turbo3`; Ollama: `qwen3:14b`; không backend: đọc config. |
| `--base_url` | Build/query | Endpoint chat LLM. | Khi dùng local endpoint hoặc endpoint custom. | TurboQuant: `http://localhost:8080/v1`; Ollama: `http://localhost:11434`; không backend: đọc env/config. |
| `--embedding_provider` | Build/query | Provider embedding. | Thường dùng `ollama` để giữ baseline embedding. | Đọc config. |
| `--embedding_base_url` | Build/query | Endpoint embedding. | Nên truyền khi dùng local embedding để tránh nhầm endpoint LLM. | Thường là `http://localhost:11434`. |
| `--llm_max_async` | Build/query | Số request LLM đồng thời từ client GraphRAG. | Giảm xuống `1` để local LLM ổn định; tăng để test throughput. | TurboQuant shortcut: `1`; không backend: default GraphRAG/config. |
| `--llm_timeout` | Build/query | Timeout mỗi request LLM. | Local model sinh lâu nên dùng `600`. | TurboQuant shortcut: `600`; OpenAI-compatible fallback cũ: `120`. |
| `--output_dir` | Build | Folder lưu graph build. | Mỗi backend/model nên có output riêng, ví dụ `outputs/compare_turboquant_qwen25_7b_1doc`. | Theo config hoặc argument cũ. |
| `--working_dir` | Query | Folder graph đã build. | Query graph tương ứng với backend/model đã build. | Theo config hoặc argument cũ. |
| `--mode` | Query | Chế độ query, ví dụ `local` hoặc `global`. | Chọn workflow retrieval. | Theo CLI/config query. |
| `--question` | Query | Câu hỏi cần chạy. | Query single question. | Bắt buộc cho query single. |

### Bảng Tham Số llama-server Quan Trọng

| Tham số | Ý nghĩa | Ghi chú benchmark |
|---|---|---|
| `-m PATH` | Đường dẫn model GGUF được load. | Đây là model LLM thật sự server chạy. |
| `--alias NAME` | Tên model expose qua `/v1/models`. | `build_graph.py --model` phải khớp alias này. |
| `--host 127.0.0.1` | Bind server local-only. | Dùng local benchmark an toàn. |
| `--port 8080` | Port server. | `--base_url` phải là `http://localhost:8080/v1`. |
| `-ctk q8_0` | Kiểu KV cache cho Key. | `q8_0` là mốc an toàn/chất lượng hơn. |
| `-ctv turbo3` | Kiểu KV cache cho Value. | Đây là phần TurboQuant nén V cache để tiết kiệm VRAM/context. |
| `-ctk q8_0 -ctv q8_0` | KV cache baseline không TurboQuant V. | Dùng làm mốc so sánh chất lượng/tốc độ. |
| `-ctk turbo3 -ctv turbo3` | Nén cả K và V. | Nén mạnh hơn, cần kiểm chất lượng bằng PPL/NIAH. |
| `-fa on` hoặc `-fa 1` | Bật flash attention. | Thường cần cho context dài và hiệu năng GPU. |
| `-ngl 99` | Số layer offload lên GPU. | `99` thường có nghĩa offload tối đa nếu VRAM đủ. |
| `-c 32768` | Context runtime của server. | Không được vượt quá khả năng model/VRAM; context lớn tốn KV cache. |
| `--parallel N` | Số slot request song song. | Nếu set `--parallel 1`, nên dùng `--llm_max_async 1` phía client. |
| `--log-file PATH` | Ghi log server ra file. | Cần để grep `POST /v1/chat/completions`. |

Ghi chú context theo các model bạn đang dùng:

| Model GGUF | Context train/khả năng đã ghi nhận | Ghi chú |
|---|---:|---|
| Qwen2.5 7B Instruct Q8 | 131k | Phù hợp test context dài hơn trong giới hạn VRAM. |
| Qwen3 14B Q5_0 | Khoảng 64k theo ghi chú benchmark của bạn | Nặng hơn, decode lâu hơn 7B. |
| Qwen3 14B Q8_0 | Khoảng 10k theo ghi chú benchmark của bạn | Q8 tốn VRAM hơn, context thực tế thấp hơn. |

### Lệnh Kiểm Tra Riêng Cho llama-server/TurboQuant

Các lệnh này kiểm riêng backend `llama-cpp-turboquant`; chúng không build graph. Dùng trước để hiểu tốc độ, chất lượng và khả năng context của model/KV cache.

#### Speed & Throughput bằng llama-bench

Prefill là tốc độ nạp prompt/context. Decode là tốc độ sinh token. GraphRAG build thường tốn nhiều decode vì LLM phải sinh JSON extraction và summary.

```bash
cd /home/guest/Projects/Research/llama-cpp-turboquant
conda activate turboquant

./build/bin/llama-bench \
  -m models/qwen3.5-27b-config-i.gguf \
  -fa 1 \
  -ngl 99 \
  -p 512 \
  -n 128
```

So sánh KV cache baseline `q8_0/q8_0` với TurboQuant `turbo3/turbo3` ở context dài:

```bash
# Baseline KV q8_0 ở 8K và 32K
./build/bin/llama-bench -m model.gguf -ctk q8_0 -ctv q8_0 -fa 1 -p 8192 -r 1
./build/bin/llama-bench -m model.gguf -ctk q8_0 -ctv q8_0 -fa 1 -p 32768 -r 1

# TurboQuant KV turbo3 ở 8K và 32K
./build/bin/llama-bench -m model.gguf -ctk turbo3 -ctv turbo3 -fa 1 -p 8192 -r 1
./build/bin/llama-bench -m model.gguf -ctk turbo3 -ctv turbo3 -fa 1 -p 32768 -r 1
```

#### Quality/PPL bằng llama-perplexity

PPL dùng để kiểm mức lệch chất lượng khi đổi kiểu nén KV cache.

```bash
# Không đối xứng, thường an toàn hơn: K q8_0, V turbo3
./build/bin/llama-perplexity \
  -m model.gguf \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -f wiki.test.raw \
  -c 1024 \
  --chunks 20

# Đối xứng, nén mạnh hơn: K turbo3, V turbo3
./build/bin/llama-perplexity \
  -m model.gguf \
  -ctk turbo3 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -f wiki.test.raw \
  -c 512 \
  --chunks 20
```

#### Needle-In-A-Haystack và Skip Rate

NIAH kiểm khả năng truy xuất thông tin trong ngữ cảnh dài. Skip rate giúp đánh giá hành vi sparse/nén V cache.

```bash
python3 scripts/niah_test.py --model models/your-model.gguf --ctx 32768
python3 scripts/measure_skip_rate.py --model models/your-model.gguf
```

#### REFRACT Acid-test

REFRACT dùng để kiểm sâu độ lệch giữa cấu hình nén và baseline.

```bash
python3 -m refract.cli selftest --backend auto --model path/to/model.gguf

python3 -m refract.cli score \
  --model model.gguf \
  --candidate "ctk=q8_0,ctv=turbo4" \
  --corpus wiki.test.raw \
  --html-out report.html

python3 -m refract.cli score \
  --model model.gguf \
  --candidate "ctk=q8_0,ctv=turbo3" \
  --full
```
