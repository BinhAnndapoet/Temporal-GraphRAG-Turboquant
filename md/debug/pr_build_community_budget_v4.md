# PR Description: fix/build-community-budget-v4

## Title

```text
[codex] Fix local build community packing and runtime budget for TurboQuant
```

## Summary

This PR fixes the local build path for Temporal-GraphRAG when running against `llama-server` through the TurboQuant/OpenAI-compatible endpoint.

The main issue was not a single configuration mistake. The build failures on `fresh_v2` and `v3` came from a combination of:

1. incorrect temporal community packing logic in `tgrag/src/core/building.py`
2. runtime budget mismatch between the app's logical build budget and the real per-slot context exposed by `llama-server`
3. missing build metadata, which made later query/demo runs harder to align with the graph output that produced them

This branch fixes those issues and verifies the new behavior with a real `tmux`-driven local build test on the first `10` ECT-QA documents.

## Root cause

### 1. Temporal community packing used the wrong edge field for truncation

The temporal edge row layout is:

```python
[id, timestamp, source, target, description, rank]
```

The old code truncated by `x[3]`, which is `target`, not `description`. That caused the build to underestimate edge text length and keep far too much edge content inside temporal community prompts.

### 2. Temporal sub-community fallback matched the wrong temporal edge tuple

The old fallback logic compared only `(timestamp, source)`-like slices instead of the full temporal edge identity `(timestamp, source, target)`. That made temporal edge inclusion/exclusion unreliable when a large community was reduced through sub-community reports.

### 3. The build budget did not follow the real `llama-server` slot context

For local `llama-server`, the effective request context is:

```text
slot_context = floor(n_ctx / parallel)
```

Examples:

- `-c 131072 --parallel 4` => slot context `32768`
- `-c 131072 --parallel 2` => slot context `65536`

The previous build path did not resolve a safe budget from `/props`; it relied on the app-side logical budget. That allowed community prompts to be packed above the real slot limit.

### 4. The build output did not persist runtime metadata

Before this branch there was no `build_manifest.json`, so later query and demo runs could not reliably reconstruct how the graph had been built.

## What changed

### `build_graph.py`

- add `/props` probing helpers for local OpenAI-compatible `llama-server`
- derive `server_slot_tokens` and `server_total_slots`
- add safe budget resolution for `best_model_max_token_size`
- add CLI flags:
  - `--best_model_max_token_size`
  - `--community_token_headroom`
- write `build_manifest.json` into the build output
- print runtime lines for:
  - slot context
  - community pack budget
  - manifest path

### `tgrag/src/core/building.py`

- truncate temporal edge payloads by `description` instead of `target`
- fix temporal sub-community edge matching to use `(timestamp, source, target)`
- apply the same corrected truncation key in the fallback path
- use `llm_extra_kwargs` when generating temporal community reports
- improve final error report labels using `name/title/timestamp`

### Docs

- add a root-cause-and-fix document for `v3 -> v4`
- add a test-result document for the `10`-doc `v4` run
- update build CLI docs to reflect:
  - `build_manifest.json`
  - `/props`-aware budget logic
  - `conda run --no-capture-output ... |& tee ...`
- update the `md/` index and the fix-plan status notes

## Files changed

- `build_graph.py`
- `tgrag/src/core/building.py`
- `md/CLI/build_graph.md`
- `md/README_MD.md`
- `md/debug/fix_plan_build_query_demo_turboquant.md`
- `md/debug/build_community_v3_to_v4_root_cause_and_fix.md`
- `md/debug/v4_build_fix_test_10docs.md`

## Validation

### Static validation

```bash
python -m py_compile build_graph.py tgrag/src/core/building.py
```

### Runtime validation

Local server:

```bash
cd /home/guest/Projects/Research/llama-cpp-turboquant
./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 131072 \
  --parallel 2 \
  --n-predict 3072 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log
```

Build:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false
export OPENAI_API_KEY=dummy
export TG_RAG_USAGE_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl

conda run --no-capture-output -n turboquant python -u build_graph.py \
  --output_dir /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4 \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --base_url http://127.0.0.1:8080/v1 \
  --corpus_path /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_batch_num 16 \
  --embedding_max_async 1 \
  --embedding_prefix "search_document: " \
  --chunk_size 1200 \
  --chunk_overlap 100 \
  --num_docs 10 \
  --llm_max_async 2 \
  --llm_timeout 900 \
  --entity_extraction_timeout 43200 \
  |& tee /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log
```

## Test result

The `v4` smoke build completed successfully:

- `build_status = completed`
- `server_slot_tokens = 65536`
- `best_model_max_token_size = 61440`
- `api_error = 0`
- no `Error Report for ...`
- no `Failed to generate community report`

Artifacts:

- output: `outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4`
- build log: `logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.log`
- usage log: `results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4.jsonl`
- manifest: `outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_010docs_v4/build_manifest.json`

## How to run a full tmux build later

### tmux server

```bash
tmux new -s tq_full_srv
```

Inside:

```bash
cd /home/guest/Projects/Research/llama-cpp-turboquant
./build/bin/llama-server \
  -m /home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf \
  --alias qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --host 127.0.0.1 \
  --port 8080 \
  -ctk q8_0 \
  -ctv turbo3 \
  -fa on \
  -ngl 99 \
  -c 131072 \
  --parallel 2 \
  --n-predict 3072 \
  --log-file /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/llama_server/SERVER_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4.log
```

### tmux build

```bash
tmux new -s tq_full_build
```

Inside:

```bash
cd /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant
export HF_HOME=/home/guest/Projects/Research/.cache/huggingface
export TRANSFORMERS_CACHE=/home/guest/Projects/Research/.cache/huggingface/transformers
export TOKENIZERS_PARALLELISM=false
export OPENAI_API_KEY=dummy
export TG_RAG_USAGE_LOG=/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4.jsonl

conda run --no-capture-output -n turboquant python -u build_graph.py \
  --output_dir /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4 \
  --model qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p2-np3072 \
  --base_url http://127.0.0.1:8080/v1 \
  --corpus_path /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/ect-qa/corpus/base.jsonl.gz \
  --local_llm_backend turboquant \
  --embedding_provider huggingface \
  --embedding_model nomic-ai/nomic-embed-text-v1.5 \
  --embedding_dim 768 \
  --embedding_max_tokens 7500 \
  --embedding_max_chars 24000 \
  --embedding_device cuda \
  --embedding_batch_size 16 \
  --embedding_batch_num 16 \
  --embedding_max_async 1 \
  --embedding_prefix "search_document: " \
  --chunk_size 1200 \
  --chunk_overlap 100 \
  --num_docs 384 \
  --llm_max_async 2 \
  --llm_timeout 900 \
  --entity_extraction_timeout 43200 \
  |& tee /home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4.log
```

### What to check after the full build

```bash
rg -n 'Community pack budget|Slot context|BUILD SUMMARY|Failed to generate community report|Error Report for' \
  logs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4.log
```

```bash
rg -n 'api_error' results/usage/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4.jsonl
```

Also inspect:

```text
outputs/build_graph/BUILD_qwen25_7b_p2_c131072_hf_nomic_cuda_384docs_v4/build_manifest.json
```

## Limitations

This PR proves the fix on a real local `10`-doc build. It does not yet prove that the full `384`-doc ECT-QA graph is clean under all temporal community sizes. The next practical step is a staged run:

1. `50 docs`
2. `100 docs`
3. `384 docs`
