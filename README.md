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
cd /home/guest/Projects/Research
git clone https://github.com/BinhAnndapoet/Temporal-GraphRAG-Turboquant.git
cd Temporal-GraphRAG-Turboquant

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  

# Install dependencies
pip install -r requirements.txt
```

If you only want the upstream/cloud flow, the steps above are enough. If you want the local TurboQuant `llama-server` flow used by the runbooks in this fork, also clone the sibling repos below in the same parent directory.

## Local TurboQuant Workspace

Keep the three repos as siblings:

```text
/home/guest/Projects/Research/
├── Temporal-GraphRAG-Turboquant
├── llama-cpp-turboquant
└── turboquant_plus
```

Clone the companion repos:

```bash
cd /home/guest/Projects/Research

# Required for local TurboQuant `llama-server`
git clone https://github.com/TheTom/llama-cpp-turboquant.git
git -C llama-cpp-turboquant checkout feature/turboquant-kv-cache

# Optional: docs, benchmarks, and REFRACT experiments
git clone https://github.com/TheTom/turboquant_plus.git
```

- `llama-cpp-turboquant` is the runtime repo that provides `llama-server`.
- `turboquant_plus` is an optional companion repo for TurboQuant profiles, benchmark notes, and REFRACT experiments. It is not required just to boot `llama-server`.
- The local runbooks later in this README assume the `llama-cpp-turboquant` sibling path exists exactly as shown above.

## Build `llama-server` with CMake

From `llama-cpp-turboquant`, choose one backend configure command, then build:

```bash
cd /home/guest/Projects/Research/llama-cpp-turboquant

# CPU only
cmake -B build -DCMAKE_BUILD_TYPE=Release

# NVIDIA CUDA
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release

# Apple Silicon Metal
cmake -B build -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release

# AMD ROCm/HIP
cmake -B build -DGGML_HIP=ON -DCMAKE_BUILD_TYPE=Release

cmake --build build --config Release --target llama-server -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
```

Put a GGUF model under `llama-cpp-turboquant/models/`, then smoke-test the server:

```bash
./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/model.gguf \
  --alias model-local \
  -c 2048 \
  --host 127.0.0.1 \
  --port 8080

curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/v1/models
```

If you use local `llama-server` via the OpenAI-compatible `/v1` API in this repo, set `OPENAI_API_KEY=dummy` (or any non-empty value), point `base_url` to `http://127.0.0.1:8080/v1`, and make sure the alias above matches the `--model` value you pass to `build_graph.py`, `query_graph.py`, or `demo.py`.

If you want the same TurboQuant profile used by the detailed local runbooks later in this README, start the server like this:

```bash
./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p2-np4096 \
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

For TurboQuant-specific verification later in this repo, also check:

```bash
curl http://127.0.0.1:8080/props
curl http://127.0.0.1:8080/slots
```

## Local Env for These Runbooks

Most local runbooks in this fork use a Conda env named `turboquant` rather than the lightweight `venv` shown above:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda env create -f environment.turboquant.yml
conda activate turboquant
cp .env.example .env
```

Common local values in `.env`:

```bash
OPENAI_API_KEY=dummy
OPENAI_BASE_URL=http://127.0.0.1:8080/v1
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Add `GOOGLE_API_KEY` or `GEMINI_API_KEY` only if you want the Gemini path instead of local `llama-server`.

## Local Docs Index

For the longer workflow and tuning notes, use these in-repo docs:

- `md/README_MD.md` for the broader local document index.
- `md/CLI/start_server.md` for `llama-server` startup profiles and tuning.
- `md/runbooks/demo_setup_and_db_graph_flow.md` for the canonical demo flow.
- `scripts/run_demo_stack.sh` for the quickest tmux-based demo launcher.
- `## Kiểm Tra Local TurboQuant LLM` later in this README for deeper verification, logging, and benchmark notes.

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

### Quy Ước Output Và Log

Chạy mọi lệnh dưới đây từ root repo, trừ terminal start `llama-server` phải `cd` sang repo `llama-cpp-turboquant`.

| Loại file | Vị trí khuyến nghị | Lý do |
|---|---|---|
| Graph output | `outputs/build_graph/<CASE>/` | Tách graph theo backend/model/config, không ghi đè run cũ. |
| Build log | `logs/build_graph/<CASE>_<RUN_ID>.log` | Lưu stdout/stderr của `build_graph.py` để `tail -f` và grep lỗi. |
| Server log | `logs/llama_server/<LLM_ALIAS>_<RUN_ID>.log` | Lưu log `llama-server`, dùng để grep request `/v1/chat/completions`. |
| Usage log | `logs/usage/<CASE>_<RUN_ID>.jsonl` | Dự phòng cho token/call usage; source hiện tại chưa ghi `TG_RAG_USAGE_LOG`, nên folder này có thể rỗng. |
| Cache LLM | `<OUT>/kv_store_llm_response_cache.json` | Kiểm model/alias thật sự đã được gọi. |

Không trộn nhiều backend hoặc nhiều alias trong cùng một `OUT`. Nếu muốn fresh benchmark, dùng `CASE` mới hoặc xóa folder output cũ trước khi chạy lại.

### Quy Ước Alias

Alias phải khớp với giá trị truyền vào `build_graph.py --model`. Nên đặt alias theo cấu hình thật của server để không nhầm giữa TurboQuant, baseline KV, context, parallel và output cap.

Ví dụ alias:

```text
qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p2-np4096
```

Ý nghĩa:

| Thành phần | Ý nghĩa |
|---|---|
| `qwen25-7b` | Qwen2.5 7B Instruct. |
| `q8` | GGUF weights Q8. |
| `ctkq8` | KV cache Key dùng `q8_0`. |
| `ctvturbo3` | KV cache Value dùng `turbo3`. |
| `c32k` | Server runtime context `-c 32768`. |
| `p2` | Server `--parallel 2`, build `--llm_max_async 2`. |
| `np4096` | Server `--n-predict 4096`, giới hạn output mặc định mỗi request. |

Nếu đổi alias, phải dừng và start lại `llama-server`; alias không tự đổi trong server đang chạy. Build chỉ đúng khi:

```bash
curl http://localhost:8080/v1/models
curl http://localhost:8080/props
```

trả về đúng `id/model_alias` bạn truyền vào `build_graph.py --model`.

### Vì Sao Không Để `--n-predict -1`

`llama-server` mặc định `--n-predict -1`, tức là không giới hạn số token sinh ra. Trong build graph hiện tại, bước entity extraction gọi OpenAI-compatible endpoint mà không truyền `max_tokens` riêng cho từng request. Vì vậy nếu server để `-1`, một chunk có thể sinh tới khi gặp EOS hoặc chạm context slot.

Hậu quả thực tế khi build full corpus:

- Một request có thể sinh 10k-16k token, làm terminal lâu không thấy progress.
- Progress chunk chỉ in sau khi request trả xong, nên nhìn giống bị đứng.
- Response quá dài dễ bị `truncated=1`, cache phình lớn, parse chậm, và tăng rủi ro timeout/connection error.
- Với local model, output extraction dài quá thường không tăng chất lượng tương ứng.

Khuyến nghị thực dụng:

| Mục tiêu | `--n-predict` |
|---|---:|
| Smoke/debug nhanh | `2048` |
| Build full ổn định | `4096` |
| Chỉ dùng khi thật sự cần extraction rất dài | `8192` |

README này dùng `--n-predict 4096` làm mặc định an toàn cho TurboQuant build.

Nếu `4096` thiếu, dấu hiệu thường là server log có `truncated`, response trong cache bị cụt, hoặc chất lượng extraction giảm rõ. Khi đó không nên chỉ tăng `--n-predict` một mình, vì prompt và output cùng chia sẻ context của slot. Với `-c 32768 --parallel 4`, mỗi slot chỉ còn khoảng 8k context; log thực tế đã có request chạm `n_tokens = 8191, truncated = 1`. Cách tăng an toàn hơn là tăng `-c` trước để mỗi slot có đủ context, rồi chỉ tăng `--n-predict` nếu vẫn thấy output bị cắt do giới hạn sinh.

### Chọn `-c` Theo `--parallel`

`llama-server -c` là tổng context runtime, còn context mỗi slot xấp xỉ `-c / --parallel`. Với build graph, nên giữ khoảng 16k context mỗi slot vì prompt extraction có thể vài nghìn token và output đang cap 4096 token.

| Mục tiêu | Lệnh server | Context mỗi slot | Ghi chú |
|---|---|---:|---|
| Chắc, ít song song | `-c 32768 --parallel 2` | ~16k | Mặc định ổn định cho GPU 16GB. |
| Nhanh hơn, vẫn giữ context | `-c 65536 --parallel 4` | ~16k | Khuyến nghị nếu p2 còn dư VRAM. |
| p4 smoke/throughput nhanh | `-c 32768 --parallel 4` | ~8k | Có thể truncate với chunk dài; chỉ dùng khi chấp nhận rủi ro. |
| p6 thử nghiệm | `-c 98304 --parallel 6` | ~16k | Có thể không nhanh hơn vì GPU đã gần 100%; cần smoke test. |
| p8 thử nghiệm cao | `-c 131072 --parallel 8` | ~16k | Rủi ro OOM/overhead cao trên 16GB, không khuyến nghị cho full build đầu tiên. |

Khuyến nghị thực dụng cho máy hiện tại: nếu muốn parallel cao hơn p2, chạy `p4 c64k np4096` trước; chỉ tăng `np8192` khi `c64k np4096` vẫn cho thấy output bị cắt.

### Khuyến Nghị Theo Model

| Model | Cấu hình bắt đầu | Khi nào tăng | Ghi chú |
|---|---|---|---|
| Qwen2.5 7B Q8 | `-c 65536 --parallel 4 --n-predict 4096` + build `--llm_max_async 4` | Chỉ thử p6 nếu muốn benchmark throughput riêng và GPU còn headroom. | Log thực tế `c64k-p4` chưa truncate và GPU đã gần bão hòa, nên đây là cấu hình ổn định. |
| Qwen/Qwen3 14B | `-c 32768 --parallel 2 --n-predict 4096` + build `--llm_max_async 2` | Nếu VRAM còn dư và smoke không truncate, thử `-c 65536 --parallel 4`. | 14B nặng hơn nhiều, không nên nhảy thẳng p4 full build. |
| Bất kỳ model nào | Giữ `--llm_max_async` bằng `--parallel`. | Tăng `-c` trước khi tăng `--n-predict` nếu thấy `truncated=1`. | `--parallel` tăng throughput, `-c` giữ context mỗi slot, `--n-predict` chỉ giới hạn output. |

Cách đọc log để quyết định:

```bash
# Nếu có nhiều dòng truncated = 1: tăng -c hoặc giảm parallel.
grep -n "truncated = 1" ${SERVER_LOG}

# Nếu nhiều request sinh đúng 4096 token nhưng không truncated: cân nhắc np8192 sau smoke.
grep "eval time =" ${SERVER_LOG} | tail -n 20

# Nếu GPU đã >90% util, tăng parallel thường không tăng tốc tuyến tính.
nvidia-smi
```

### Terminal 1: Start llama-server

Ví dụ ổn định cho máy 16GB VRAM: `parallel 2`, mỗi slot khoảng 16k context vì server chạy `-c 32768`, output cap 4096 token.

```bash
cd /home/guest/Projects/Research/llama-cpp-turboquant
conda activate turboquant

export RUN_ID=$(date +%Y%m%d_%H%M%S)
export LLM_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p2-np4096

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server
export SERVER_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/${LLM_ALIAS}_${RUN_ID}.log

echo "RUN_ID=${RUN_ID}"
echo "LLM_ALIAS=${LLM_ALIAS}"
echo "SERVER_LOG=${SERVER_LOG}"

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias ${LLM_ALIAS} \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 2 \
  --n-predict 4096 \
  --log-file "${SERVER_LOG}"
```

Giữ terminal này mở. Nếu tắt terminal này thì build với `--local_llm_backend turboquant` sẽ fail ở healthcheck hoặc trong lúc gọi LLM.

Nếu muốn chạy chắc hơn nhưng chậm hơn, đổi cả alias và tham số về `p1`:

```bash
export LLM_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p1-np4096
# ... giữ các tham số khác, đổi --parallel 1
```

Nếu muốn chạy `p4` ổn định hơn, đổi cả alias và tham số context:

```bash
export LLM_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096
# ... đổi -c 65536 và --parallel 4
```

Nếu chỉ muốn smoke test throughput nhanh, có thể dùng `c32k-p4`, nhưng mỗi slot chỉ khoảng 8k context và có thể `truncated=1` với chunk dài.

### Terminal 2: Check Server

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

curl http://localhost:8080/v1/models
curl http://localhost:8080/props
curl http://localhost:8080/slots
```

Kỳ vọng với lệnh `p2-np4096`:

```text
model_alias: qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p2-np4096
total_slots: 2
n_ctx: 16384
```

Kỳ vọng với lệnh `c64k-p4-np4096`:

```text
model_alias: qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096
total_slots: 4
n_ctx: 16384
```

Nếu dùng `c32k-p4-np4096`, `n_ctx` chỉ khoảng `8192` mỗi slot.

### Terminal 3: Build Smoke 1 Document

Terminal build phải dùng đúng `RUN_ID` và `LLM_ALIAS` từ terminal server, vì biến môi trường không tự truyền qua terminal khác. Cách an toàn trong README là set `LLM_ALIAS` trước rồi tự lấy `RUN_ID` từ file server log mới nhất theo đúng alias. Nếu copy thủ công, dùng đúng giá trị server đã in, ví dụ `export RUN_ID=20260522_015408`; không để nguyên literal `copy_RUN_ID_from_server_terminal`.

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export LLM_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p2-np4096
export RUN_ID=$(basename "$(ls -t logs/llama_server/${LLM_ALIAS}_*.log | head -n 1)" | sed -E "s/^${LLM_ALIAS}_//; s/\.log$//")
echo "Using RUN_ID=${RUN_ID}"
export CASE=turboquant_1doc_${LLM_ALIAS}
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log
export TG_RAG_USAGE_LOG=logs/usage/${CASE}_${RUN_ID}.jsonl

mkdir -p outputs/build_graph logs/build_graph logs/usage

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --output_dir ${OUT} \
  --model ${LLM_ALIAS} \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --num_docs 1 \
  --llm_max_async 2 \
  --llm_timeout 600 \
  2>&1 | tee ${BUILD_LOG}
```

Theo dõi build log ở terminal khác:

```bash
tail -f ${BUILD_LOG}
```

### Terminal 4: Build Full 384 Documents

Chỉ chạy full sau khi smoke test pass. Dùng `OUT` khác để không trộn với smoke test.

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export LLM_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p2-np4096
export RUN_ID=$(basename "$(ls -t logs/llama_server/${LLM_ALIAS}_*.log | head -n 1)" | sed -E "s/^${LLM_ALIAS}_//; s/\.log$//")
echo "Using RUN_ID=${RUN_ID}"
export CASE=turboquant_384_${LLM_ALIAS}
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log
export TG_RAG_USAGE_LOG=logs/usage/${CASE}_${RUN_ID}.jsonl

mkdir -p outputs/build_graph logs/build_graph logs/usage

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --output_dir ${OUT} \
  --model ${LLM_ALIAS} \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --num_docs 384 \
  --llm_max_async 2 \
  --llm_timeout 600 \
  2>&1 | tee ${BUILD_LOG}
```

### Tùy Chọn: Build Full Với p4

Dùng p4 khi p2 còn dư VRAM và server chạy ổn. Bộ lệnh dưới đây dùng `-c 65536`, nên mỗi slot khoảng 16k context. Đây là cấu hình p4 ổn định hơn `c32k-p4`, vì log thực tế với `c32k-p4` đã có request chạm context và `truncated=1`.

Terminal server:

```bash
cd /home/guest/Projects/Research/llama-cpp-turboquant
conda activate turboquant

export RUN_ID=$(date +%Y%m%d_%H%M%S)
export LLM_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096

mkdir -p /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server
export SERVER_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/${LLM_ALIAS}_${RUN_ID}.log

echo "RUN_ID=${RUN_ID}"
echo "LLM_ALIAS=${LLM_ALIAS}"
echo "SERVER_LOG=${SERVER_LOG}"

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias ${LLM_ALIAS} \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 65536 \
  --parallel 4 \
  --n-predict 4096 \
  --log-file "${SERVER_LOG}"
```

Terminal build:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export LLM_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np4096
export RUN_ID=$(basename "$(ls -t logs/llama_server/${LLM_ALIAS}_*.log | head -n 1)" | sed -E "s/^${LLM_ALIAS}_//; s/\.log$//")
echo "Using RUN_ID=${RUN_ID}"
export CASE=turboquant_384_${LLM_ALIAS}
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log
export TG_RAG_USAGE_LOG=logs/usage/${CASE}_${RUN_ID}.jsonl

mkdir -p outputs/build_graph logs/build_graph logs/usage

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --output_dir ${OUT} \
  --model ${LLM_ALIAS} \
  --base_url http://localhost:8080/v1 \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --num_docs 384 \
  --llm_max_async 4 \
  --llm_timeout 600 \
  2>&1 | tee ${BUILD_LOG}
```

Nếu `c64k-p4-np4096` vẫn bị thiếu output do chạm giới hạn sinh, thử tăng output cap sau khi smoke test:

```bash
export LLM_ALIAS=qwen25-7b-q8-ctkq8-ctvturbo3-c64k-p4-np8192
# server: giữ -c 65536 --parallel 4, đổi --n-predict 8192
# build: đổi --model ${LLM_ALIAS}, giữ --llm_max_async 4
```

Nếu `c64k-p4` OOM, quay về `c32k-p4` để smoke hoặc `c32k-p2` để build ổn định.

### Usage Log Hiện Tại

Các lệnh build vẫn set `TG_RAG_USAGE_LOG` để giữ convention output, nhưng source hiện tại chưa đọc biến này và `openai_complete_if_cache` đang trả về text string, không trả tuple `(text, usage)`. Vì vậy `logs/usage/` có thể rỗng là bình thường, không có nghĩa build không chạy.

Hiện tại đọc token/tốc độ từ `llama-server` log:

```bash
# Đếm request LLM đã vào server.
grep -c "POST /v1/chat/completions" ${SERVER_LOG}

# Kiểm request bị cắt context.
grep -n "truncated = 1" ${SERVER_LOG}

# Xem tốc độ decode gần đây.
grep "^       eval time" ${SERVER_LOG} | tail -n 20
```

### Kiểm Tra Khi Đang Chạy

Server request và lỗi:

```bash
tail -f ${SERVER_LOG}
grep -E "POST /v1/chat/completions|truncated|error|failed|cleaning up" ${SERVER_LOG}
```

Build stage và lỗi chunk:

```bash
tail -f ${BUILD_LOG}
grep -E "\[build-stage\]|\[build-detail\]|\[timer\]|ERROR|Failed to process chunk" ${BUILD_LOG}
```

GPU và slots:

```bash
nvidia-smi
curl http://localhost:8080/slots
```

Backend thật sự đã dùng:

```bash
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

Kết quả đúng phải chứa đúng alias trong `LLM_ALIAS`, ví dụ:

```text
{'qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p2-np4096': ...}
```

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
| `OUT` | `outputs/build_graph/${CASE}` | Folder graph output. |
| `BUILD_LOG` | `logs/build_graph/${CASE}_${RUN_ID}.log` | Log build graph. |
| `QUERY_LOG` | `logs/query_graph/${CASE}_${RUN_ID}.log` | Log query graph. |
| `SERVER_LOG` | `logs/llama_server/${LLM_ALIAS}_${RUN_ID}.log` | Log `llama-server`, chỉ có ở case TurboQuant. |

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

mkdir -p outputs/build_graph logs/build_graph logs/query_graph logs/usage logs/llama_server
export OLLAMA_BASE_URL=http://localhost:11434
```

#### Case 1: Baseline Theo Config Mặc Định

Lệnh này không bật TurboQuant. Nó đọc `building.provider` và `building.model` trong `tgrag/configs/config.yaml`.

```bash
export CASE=compare_config_default_1doc
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log

python -u build_graph.py \
  --output_dir ${OUT} \
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
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log

python -u build_graph.py \
  --provider gemini \
  --model gemini-2.5-flash-lite \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --output_dir ${OUT} \
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
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log

python -u build_graph.py \
  --local_llm_backend ollama \
  --model qwen3:14b \
  --base_url http://localhost:11434 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --output_dir ${OUT} \
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
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p1-np4096 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --output_dir ${OUT} \
  --corpus_path ect-qa/corpus/base.jsonl.gz \
  --num_docs 1 \
  2>&1 | tee ${BUILD_LOG}
```

Kiểm nhanh thời gian, lỗi chunk, và backend thật:

```bash
grep -E "\[build-detail\] chunk LLM extraction|\[build-stage\] community report generation|\[timer\] insert documents" logs/build_graph/*_1doc_${RUN_ID}.log
grep -c "Failed to process chunk" logs/build_graph/*_1doc_${RUN_ID}.log

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
grep -E "POST /v1/chat/completions" logs/llama_server/qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p1-np4096_${RUN_ID}.log
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

mkdir -p outputs/build_graph logs/build_graph logs/query_graph logs/usage logs/llama_server
export OLLAMA_BASE_URL=http://localhost:11434

ollama list
ollama pull nomic-embed-text
```

#### Case 1: Qwen2.5 7B Q8 Có TurboQuant KV

Terminal server:

```bash
conda activate turboquant

export RUN_ID=$(date +%Y%m%d_%H%M%S)
export SERVER_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p1-np4096_${RUN_ID}.log

cd /home/guest/Projects/Research/llama-cpp-turboquant

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p1-np4096 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 1 \
  --n-predict 4096 \
  --log-file ${SERVER_LOG}
```

Terminal build:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
conda activate turboquant

export RUN_ID=$(basename "$(ls -t logs/llama_server/qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p1-np4096_*.log | head -n 1)" | sed -E "s/^qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p1-np4096_//; s/\.log$//")
echo "Using RUN_ID=${RUN_ID}"
export CASE=test_qwen25_7b_q8_ctkq8_ctvturbo3_c32k_p1_np4096_1doc
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log
export TG_RAG_USAGE_LOG=logs/usage/${CASE}_${RUN_ID}.jsonl

mkdir -p outputs/build_graph logs/build_graph logs/query_graph logs/usage logs/llama_server

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p1-np4096 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --output_dir ${OUT} \
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

export RUN_ID=$(date +%Y%m%d_%H%M%S)
export SERVER_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/qwen25-7b-q8-ctkq8-ctvq8-c32k-p1-np4096_${RUN_ID}.log

cd /home/guest/Projects/Research/llama-cpp-turboquant

./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvq8-c32k-p1-np4096 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv q8_0 \
  -fa on \
  -ngl 99 \
  -c 32768 \
  --parallel 1 \
  --n-predict 4096 \
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

export RUN_ID=$(basename "$(ls -t logs/llama_server/qwen25-7b-q8-ctkq8-ctvq8-c32k-p1-np4096_*.log | head -n 1)" | sed -E "s/^qwen25-7b-q8-ctkq8-ctvq8-c32k-p1-np4096_//; s/\.log$//")
echo "Using RUN_ID=${RUN_ID}"
export CASE=test_qwen25_7b_q8_ctkq8_ctvq8_c32k_p1_np4096_1doc
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log
export TG_RAG_USAGE_LOG=logs/usage/${CASE}_${RUN_ID}.jsonl

mkdir -p outputs/build_graph logs/build_graph logs/query_graph logs/usage logs/llama_server

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --provider openai \
  --model qwen25-7b-q8-ctkq8-ctvq8-c32k-p1-np4096 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --output_dir ${OUT} \
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
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log
export TG_RAG_USAGE_LOG=logs/usage/${CASE}_${RUN_ID}.jsonl

mkdir -p outputs/build_graph logs/build_graph logs/query_graph logs/usage logs/llama_server

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
  --output_dir ${OUT} \
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
export OUT=outputs/build_graph/${CASE}
export BUILD_LOG=logs/build_graph/${CASE}_${RUN_ID}.log
export TG_RAG_USAGE_LOG=logs/usage/${CASE}_${RUN_ID}.jsonl

mkdir -p outputs/build_graph logs/build_graph logs/query_graph logs/usage logs/llama_server

ollama list
ollama pull nomic-embed-text

export OLLAMA_BASE_URL=http://localhost:11434

python -u build_graph.py \
  --provider gemini \
  --model gemini-2.5-flash-lite \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --output_dir ${OUT} \
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
| TurboQuant Qwen2.5 | `qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p1-np4096` |
| Baseline Qwen2.5 không TurboQuant | `qwen25-7b-q8-ctkq8-ctvq8-c32k-p1-np4096` |
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
export OUT=outputs/build_graph/${CASE}
export QUERY_LOG=logs/query_graph/${CASE}_${RUN_ID}.log

python -u query_graph.py \
  --working_dir ${OUT} \
  --mode local \
  --question "$QUESTION" \
  2>&1 | tee ${QUERY_LOG}
```

#### Query Case 2: Graph Gemini Explicit

```bash
export CASE=compare_gemini_ollama_embed_1doc
export OUT=outputs/build_graph/${CASE}
export QUERY_LOG=logs/query_graph/${CASE}_${RUN_ID}.log

python -u query_graph.py \
  --provider gemini \
  --model gemini-2.5-flash \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --working_dir ${OUT} \
  --mode local \
  --question "$QUESTION" \
  2>&1 | tee ${QUERY_LOG}
```

#### Query Case 3: Graph Ollama Native

```bash
export CASE=compare_ollama_qwen3_14b_1doc
export OUT=outputs/build_graph/${CASE}
export QUERY_LOG=logs/query_graph/${CASE}_${RUN_ID}.log

python -u query_graph.py \
  --local_llm_backend ollama \
  --model qwen3:14b \
  --base_url http://localhost:11434 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --working_dir ${OUT} \
  --mode local \
  --question "$QUESTION" \
  2>&1 | tee ${QUERY_LOG}
```

#### Query Case 4: Graph TurboQuant

```bash
export CASE=compare_turboquant_qwen25_7b_1doc
export OUT=outputs/build_graph/${CASE}
export QUERY_LOG=logs/query_graph/${CASE}_${RUN_ID}.log

export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=sk-local
export OLLAMA_BASE_URL=http://localhost:11434

python -u query_graph.py \
  --local_llm_backend turboquant \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p1-np4096 \
  --base_url http://localhost:8080/v1 \
  --embedding_provider ollama \
  --embedding_base_url http://localhost:11434 \
  --llm_max_async 1 \
  --llm_timeout 600 \
  --working_dir ${OUT} \
  --mode local \
  --question "$QUESTION" \
  2>&1 | tee ${QUERY_LOG}
```

Kiểm query logs:

```bash
grep -E "\[query-detail\]|\[timer\]|ERROR|Exception" logs/query_graph/compare_*_1doc_${RUN_ID}.log
```

### Bảng Tham Số CLI Cho Build Và Query

| Tham số | Dùng ở đâu | Ý nghĩa | Khi nào dùng | Mặc định nếu không truyền |
|---|---|---|---|---|
| `--local_llm_backend turboquant` | Build/query | Ép LLM đi qua local `llama-server` OpenAI-compatible `/v1`. | Benchmark TurboQuant. | Không tự bật. |
| `--local_llm_backend ollama` | Build/query | Ép LLM đi qua Ollama native API. | Benchmark local LLM không TurboQuant. | Không tự bật. |
| `--provider` | Build/query | Override provider trực tiếp, ví dụ `gemini`, `openai`, `ollama`. | Khi muốn chạy explicit theo provider thay vì local backend shortcut. | Đọc từ config. |
| `--model` | Build/query | Tên model hoặc alias. Với TurboQuant phải khớp `llama-server --alias`. | Khi đổi model/alias. | Ví dụ TurboQuant: `qwen25-7b-q8-ctkq8-ctvturbo3-c32k-p2-np4096`; Ollama: `qwen3:14b`; không backend: đọc config. |
| `--base_url` | Build/query | Endpoint chat LLM. | Khi dùng local endpoint hoặc endpoint custom. | TurboQuant: `http://localhost:8080/v1`; Ollama: `http://localhost:11434`; không backend: đọc env/config. |
| `--embedding_provider` | Build/query | Provider embedding. | Thường dùng `ollama` để giữ baseline embedding. | Đọc config. |
| `--embedding_base_url` | Build/query | Endpoint embedding. | Nên truyền khi dùng local embedding để tránh nhầm endpoint LLM. | Thường là `http://localhost:11434`. |
| `--llm_max_async` | Build/query | Số request LLM đồng thời từ client GraphRAG. | Phải khớp `llama-server --parallel`; ví dụ `p2` dùng `--llm_max_async 2`. | TurboQuant shortcut trong code là `1` nếu không truyền. |
| `--llm_timeout` | Build/query | Timeout mỗi request LLM. | Local model sinh lâu nên dùng `600`. | TurboQuant shortcut: `600`; OpenAI-compatible fallback cũ: `120`. |
| `--output_dir` | Build | Folder lưu graph build. | Mỗi backend/model nên có output riêng, ví dụ `outputs/build_graph/turboquant_384_${LLM_ALIAS}`. | Theo config hoặc argument cũ. |
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
| `-c N` | Tổng context runtime của server. | Context mỗi slot xấp xỉ `N / --parallel`; p4 ổn định nên dùng `-c 65536` để giữ khoảng 16k/slot. |
| `--parallel N` | Số slot request song song. | Phải khớp với `build_graph.py --llm_max_async`; tăng parallel mà không tăng `-c` sẽ giảm context mỗi slot. |
| `--n-predict N` | Giới hạn token sinh tối đa mặc định mỗi request. | Không nên để `-1` khi build full; README dùng `4096`. |
| `--log-file PATH` | Ghi log server ra file. | Nên trỏ về `logs/llama_server/${LLM_ALIAS}_${RUN_ID}.log` để dễ tail/grep. |

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
