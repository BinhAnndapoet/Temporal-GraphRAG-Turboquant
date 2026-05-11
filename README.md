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
