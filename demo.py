import streamlit as st
import networkx as nx
from pathlib import Path
from pyvis.network import Network
import streamlit.components.v1 as components
import json
import time
import sys
import os
import urllib.request
import urllib.error

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Auto-load .env in project root so users don't need to export keys manually
if load_dotenv is not None:
    load_dotenv(Path(__file__).parent / ".env", override=False)

from tgrag import create_temporal_graphrag_from_config
from tgrag.src.core.types import QueryParam
from tgrag.src.config.config_loader import ConfigLoader


# Copy utility functions from query_graph.py
def apply_runtime_overrides(args, override_config):
    """Apply runtime overrides from CLI args to config."""
    if args.provider:
        override_config["provider"] = args.provider
    if args.model:
        override_config["model"] = args.model
    if args.base_url:
        override_config["llm_base_url"] = args.base_url
    if args.embedding_base_url:
        override_config["embedding_base_url"] = args.embedding_base_url
    if args.local_llm_backend:
        override_config["local_llm_backend"] = args.local_llm_backend

    # Build runtime config
    runtime_config = override_config.copy()

    # Set defaults
    if "provider" not in runtime_config:
        runtime_config["provider"] = "openai"
    if "model" not in runtime_config:
        runtime_config["model"] = "gpt-4o-mini"
    if "local_llm_backend" not in runtime_config:
        runtime_config["local_llm_backend"] = None
    if "llm_base_url" not in runtime_config:
        runtime_config["llm_base_url"] = None
    if "embedding_base_url" not in runtime_config:
        runtime_config["embedding_base_url"] = None
    if "wire_protocol" not in runtime_config:
        runtime_config["wire_protocol"] = "openai"

    # Set wire protocol based on backend
    if runtime_config["local_llm_backend"] == "turboquant":
        runtime_config["wire_protocol"] = "openai-compatible-local"
        if "llm_base_url" not in runtime_config or not runtime_config["llm_base_url"]:
            runtime_config["llm_base_url"] = "http://localhost:8080/v1"
    elif runtime_config["local_llm_backend"] == "ollama":
        runtime_config["wire_protocol"] = "ollama"
        if "llm_base_url" not in runtime_config or not runtime_config["llm_base_url"]:
            runtime_config["llm_base_url"] = "http://localhost:11434"

    return runtime_config


def render_graph(nx_graph, retrieval_detail, output_path="graph.html"):
    """
    Render graph with PyVis, highlighting nodes based on their role in traversal.
    """
    net = Network(height="600px", width="100%", notebook=False, directed=False)

    # Extract data from retrieval_detail
    seed_nodes = set(retrieval_detail.get("seed_nodes", []))
    ppr_scores = retrieval_detail.get("ppr_scores", {})
    top_entities = {
        e.get("entity_name", "") for e in retrieval_detail.get("entities", [])
    }

    # Determine relevant nodes (subgraph around traversal)
    relevant_nodes = seed_nodes | top_entities | set(ppr_scores.keys())

    # Create subgraph for visualization
    if relevant_nodes:
        subgraph = nx_graph.subgraph(relevant_nodes)
    else:
        subgraph = nx_graph

    # Add nodes with colors based on role
    for node in subgraph.nodes():
        if node in seed_nodes:
            color = "#ff4444"  # Red for seed nodes
            size = 25
        elif node in top_entities:
            color = "#ff8800"  # Orange for selected entities
            size = 20
        elif ppr_scores.get(node, 0) > 0.001:  # Threshold for high PPR
            color = "#ffcc00"  # Yellow for high PPR nodes
            size = 15
        else:
            color = "#cccccc"  # Gray for background nodes
            size = 10

        title = f"Node: {node}\nPPR Score: {ppr_scores.get(node, 0):.6f}"
        net.add_node(node, color=color, size=size, title=title)

    # Add edges
    for src, tgt in subgraph.edges():
        net.add_edge(src, tgt)

    # Configure physics
    net.set_options("""  
    {  
      "physics": {  
        "enabled": true,  
        "barnesHut": {  
          "gravitationalConstant": -2000,  
          "centralGravity": 0.3,  
          "springLength": 95,  
          "springConstant": 0.04,  
          "damping": 0.09,  
          "avoidOverlap": 0  
        }  
      }  
    }  
    """)

    net.save_graph(output_path)
    return output_path


def fetch_openai_compatible_models(base_url: str, timeout: float = 3.0):
    """Fetch model ids from OpenAI-compatible /v1/models endpoint."""
    if not base_url:
        return []
    models_url = base_url.rstrip("/") + "/models"
    try:
        req = urllib.request.Request(models_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        items = payload.get("data", [])
        return [m.get("id") for m in items if isinstance(m, dict) and m.get("id")]
    except Exception:
        return []


def main():
    st.set_page_config(
        page_title="Temporal GraphRAG - Query Visualization", layout="wide"
    )

    st.title("🔍 Temporal GraphRAG - Query Visualization")
    st.markdown("Visualize node traversal during local query mode")

    # Khởi tạo các biến Session State để tránh mất dữ liệu đồ thị khi Streamlit Re-run
    if "query_response" not in st.session_state:
        st.session_state.query_response = None
    if "retrieval_detail" not in st.session_state:
        st.session_state.retrieval_detail = None
    if "html_content" not in st.session_state:
        st.session_state.html_content = None
    if "query_time_s" not in st.session_state:
        st.session_state.query_time_s = None
    if "model_input" not in st.session_state:
        st.session_state.model_input = "gpt-4o-mini"
    if "base_url_input" not in st.session_state:
        st.session_state.base_url_input = ""
    if "provider_select" not in st.session_state:
        st.session_state.provider_select = "openai"
    if "query_mode_select" not in st.session_state:
        st.session_state.query_mode_select = "local"
    if "enable_entity_retrieval_toggle" not in st.session_state:
        st.session_state.enable_entity_retrieval_toggle = True
    if "seed_node_method_select" not in st.session_state:
        st.session_state.seed_node_method_select = "entities"

    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")

        with st.expander("Quick Start (Recommended)", expanded=False):
            st.markdown(
                """
                - For local `llama-server` use: **Provider = openai**
                - Base URL: `http://localhost:8080/v1`
                - Model: must match server `--alias`
                - Working Directory: absolute path to a valid `outputs/build_graph/BUILD_*` folder
                - In local mode: enable retrieval and choose seed method
                """
            )

        config_path = st.text_input("Config Path", value="tgrag/configs/config.yaml")
        working_dir = st.text_input("Working Directory", value="")
        question = st.text_input("Question", value="What happened in Q1 2020?")

        st.subheader("Quick Preset")
        preset = st.selectbox(
            "Preset",
            [
                "Manual",
                "Local Turboquant (recommended)",
                "Local Turboquant provider (advanced)",
                "Gemini API",
                "Ollama local",
            ],
            index=0,
            help="Apply a preset to avoid Provider/Base URL/Mode mismatches.",
        )
        if st.button("Apply Preset", use_container_width=True):
            if preset == "Local Turboquant (recommended)":
                st.session_state.provider_select = "openai"
                st.session_state.base_url_input = "http://localhost:8080/v1"
                st.session_state.query_mode_select = "local"
                st.session_state.enable_entity_retrieval_toggle = True
                st.session_state.seed_node_method_select = "entities"
                if st.session_state.model_input in ["", "gpt-4o-mini"]:
                    st.session_state.model_input = "qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072"
            elif preset == "Local Turboquant provider (advanced)":
                st.session_state.provider_select = "turboquant"
                st.session_state.base_url_input = "http://localhost:8080/v1"
                st.session_state.query_mode_select = "local"
                st.session_state.enable_entity_retrieval_toggle = True
                st.session_state.seed_node_method_select = "entities"
                if st.session_state.model_input in ["", "gpt-4o-mini"]:
                    st.session_state.model_input = "qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072"
            elif preset == "Gemini API":
                st.session_state.provider_select = "gemini"
                st.session_state.base_url_input = ""
                st.session_state.query_mode_select = "local"
                st.session_state.enable_entity_retrieval_toggle = True
                st.session_state.seed_node_method_select = "entities"
                if st.session_state.model_input in ["", "gpt-4o-mini"]:
                    st.session_state.model_input = "gemini-2.5-flash"
            elif preset == "Ollama local":
                st.session_state.provider_select = "ollama"
                st.session_state.base_url_input = os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
                st.session_state.query_mode_select = "local"
                st.session_state.enable_entity_retrieval_toggle = True
                st.session_state.seed_node_method_select = "entities"
                if st.session_state.model_input in ["", "gpt-4o-mini"]:
                    st.session_state.model_input = "llama3.1"
            st.rerun()

        mode = st.selectbox(
            "Query Mode", ["local", "global", "naive"], key="query_mode_select"
        )

        st.subheader("LLM Settings")
        provider_profiles = {
            "openai": "Use for BOTH local llama-server (OpenAI-compatible) and OpenAI cloud",
            "turboquant": "Use only when testing turboquant-specific provider path (advanced)",
            "gemini": "Google Gemini API path",
            "ollama": "Native Ollama API path",
        }
        provider = st.selectbox(
            "Provider (API path)",
            ["openai", "gemini", "ollama", "turboquant"],
            key="provider_select",
            help="Choose backend provider path. For local llama-server, use openai unless you specifically test turboquant path.",
        )
        st.caption(f"{provider_profiles.get(provider, '')}")

        # Explicit provider guide (always visible, less confusing than captions only)
        if provider == "openai":
            st.info(
                "**Recommended for your local Turboquant setup.**\\n"
                "Use this when runtime server is `llama-server` at `/home/guest/Projects/Research/llama-cpp-turboquant`.\\n"
                "Set Base URL to `http://localhost:8080/v1` and Model = server `--alias`."
            )
        elif provider == "turboquant":
            st.warning(
                "**Advanced path.** Runtime server is still the same local `llama-server`; only app-side provider logic changes.\\n"
                "Use this only when you intentionally test turboquant-specific behavior."
            )
        elif provider == "gemini":
            st.info(
                "Use Gemini cloud path. This does **not** use your local `llama-server` runtime."
            )
        elif provider == "ollama":
            st.info(
                "Use Ollama runtime at `http://localhost:11434` (or `OLLAMA_BASE_URL`)."
            )

        # Provider-aware defaults for safer UX
        default_base_url_by_provider = {
            "openai": os.getenv("OPENAI_BASE_URL") or "http://localhost:8080/v1",
            "turboquant": "http://localhost:8080/v1",
            "ollama": os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434",
            "gemini": "",
        }

        suggested_base_url = default_base_url_by_provider.get(provider, "")
        if not st.session_state.base_url_input and suggested_base_url:
            st.session_state.base_url_input = suggested_base_url

        model = st.text_input("Model", key="model_input")
        base_url = st.text_input("Base URL", key="base_url_input")

        # Quick compatibility summary (always visible)
        st.markdown(
            "**Compatibility quick rule:** local Turboquant server (`llama-server`) => choose `openai` for stable path."
        )

        # Validate model alias for OpenAI-compatible local servers
        if provider in ["openai", "turboquant"] and base_url:
            with st.expander("Check server model aliases", expanded=False):
                model_ids = fetch_openai_compatible_models(base_url)
                if model_ids:
                    st.write("Server models:")
                    st.code("\n".join(model_ids))
                    if model and model not in model_ids:
                        st.warning(
                            "Model does not match server alias. Use one ID from the list above."
                        )
                    elif model:
                        st.success("Model matches a server alias.")
                else:
                    st.info(
                        "Could not read /v1/models from Base URL. Check server status or URL."
                    )

        # Show provider-specific API key guidance/field
        # UI requirement: only show API key input when user selects openai or gemini.
        provider_requires_key_input = provider in ["openai", "gemini"]

        default_api_key_from_env = None
        if provider == "openai":
            default_api_key_from_env = os.getenv("OPENAI_API_KEY")
        elif provider == "gemini":
            default_api_key_from_env = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        elif provider == "turboquant":
            # keep env fallback for turboquant path without showing API key input in UI
            default_api_key_from_env = os.getenv("OPENAI_API_KEY_TEMPORALRAG") or os.getenv("OPENAI_API_KEY")

        if provider_requires_key_input:
            env_key_hint = {
                "openai": "OPENAI_API_KEY",
                "gemini": "GOOGLE_API_KEY or GEMINI_API_KEY",
            }
            st.caption(f"Env fallback: `{env_key_hint.get(provider, 'API key')}`")
            api_key_input = st.text_input(
                "API Key (optional if already in env)", value="", type="password"
            )
        elif provider == "turboquant":
            api_key_input = ""
            st.caption(
                "No API key field shown for turboquant. Use env: `OPENAI_API_KEY_TEMPORALRAG` or `OPENAI_API_KEY` (dummy value is acceptable for local server)."
            )
        else:
            api_key_input = ""
            st.caption("Provider `ollama` does not require an API key.")

        # Keep retrieval settings compact and show only when relevant
        if mode == "local":
            with st.expander("Retrieval Settings", expanded=False):
                st.markdown(
                    """
                    **How these settings affect local retrieval:**

                    - **Enable Entity Retrieval**
                      - `ON`: allow entity-vector retrieval path (recommended)
                      - `OFF`: rely more on relation/PPR path only, may reduce recall

                    - **Seed Node Method**
                      - `entities`: start from entity search first (usually stable for fact questions)
                      - `relations`: start from relation search first (useful when query emphasizes relationships)

                    If you get `Seed Nodes = 0`, try: `Enable Entity Retrieval = ON` and `Seed Node Method = entities`.
                    """
                )
                enable_entity_retrieval = st.checkbox(
                    "Enable Entity Retrieval", key="enable_entity_retrieval_toggle"
                )
                seed_node_method = st.selectbox(
                    "Seed Node Method", ["entities", "relations"], key="seed_node_method_select"
                )
        else:
            # Defaults for non-local modes
            enable_entity_retrieval = True
            seed_node_method = "entities"

        show_graph = st.checkbox("Show Graph Visualization", value=True)

        st.markdown("---")
        if st.button("Run Query", type="primary", use_container_width=True):
            with st.spinner("Processing query..."):
                try:
                    # Prepare override config
                    override_config = {}
                    if working_dir:
                        override_config["working_dir"] = working_dir
                    if provider:
                        override_config["provider"] = provider
                    if model:
                        override_config["model"] = model
                    if base_url:
                        override_config["llm_base_url"] = base_url
                    override_config["enable_entity_retrieval"] = enable_entity_retrieval
                    override_config["seed_node_method"] = seed_node_method

                    # Create a simple args object for apply_runtime_overrides
                    class Args:
                        def __init__(self):
                            self.provider = provider
                            self.model = model
                            self.base_url = base_url
                            self.embedding_base_url = None
                            self.local_llm_backend = (
                                provider
                                if provider in ["turboquant", "ollama"]
                                else None
                            )

                    args = Args()
                    runtime_config = apply_runtime_overrides(args, override_config)

                    # Load TemporalGraphRAG
                    # If user provided API key in UI, prefer it
                    provided_api_key = None
                    if api_key_input:
                        provided_api_key = api_key_input
                    elif default_api_key_from_env:
                        provided_api_key = default_api_key_from_env
                    elif runtime_config:
                        provided_api_key = runtime_config.get("api_key")

                    # Safety fallback for local llama-server OpenAI-compatible endpoint
                    # to avoid provider key-validation failures during local runs.
                    if (
                        not provided_api_key
                        and provider in ["openai", "turboquant"]
                        and base_url
                        and base_url.startswith("http://localhost:8080")
                    ):
                        provided_api_key = "dummy"

                    graph_rag = create_temporal_graphrag_from_config(
                        config_path=config_path,
                        config_type="querying",
                        override_config=override_config if override_config else None,
                        api_key=provided_api_key,
                        base_url=(
                            runtime_config.get("llm_base_url")
                            if runtime_config
                            else None
                        ),
                        embedding_base_url=(
                            runtime_config.get("embedding_base_url")
                            if runtime_config
                            else None
                        ),
                    )

                    # Load query parameters
                    config_loader = ConfigLoader(config_path=config_path)
                    raw_config = config_loader.get_config(
                        config_type="querying",
                        override_args=override_config if override_config else None,
                    )

                    # Create QueryParam
                    query_param = QueryParam(
                        mode=mode,
                        top_k=raw_config.get("top_k", 20),
                        seed_node_method=raw_config.get("seed_node_method", "entities"),
                        local_max_token_for_text_unit=raw_config.get(
                            "local_max_token_for_text_unit", 4000
                        ),
                        local_max_token_for_local_context=raw_config.get(
                            "local_max_token_for_local_context", 6000
                        ),
                        local_max_token_for_community_report=raw_config.get(
                            "local_max_token_for_community_report", 2000
                        ),
                        global_max_token_for_community_report=raw_config.get(
                            "global_max_token_for_community_report", 16384
                        ),
                        naive_max_token_for_text_unit=raw_config.get(
                            "naive_max_token_for_text_unit", 12000
                        ),
                        sub_graph=raw_config.get("enable_subgraph", False),
                        mix_relation=raw_config.get("enable_mixed_relationship", False),
                    )

                    # Run query
                    start_ts = time.time()
                    response = graph_rag.query(question, param=query_param)
                    elapsed = time.time() - start_ts

                    # store timing
                    st.session_state.query_time_s = elapsed

                    # Extract retrieval_detail
                    retrieval_detail = None
                    if isinstance(response, tuple) and len(response) == 2:
                        response, retrieval_detail = response

                    # Lưu kết quả vào Session State
                    st.session_state.query_response = response
                    st.session_state.retrieval_detail = retrieval_detail
                    st.session_state.html_content = None  # Reset đồ thị cũ

                    # Render đồ thị nếu ở chế độ local_query và lấy được dữ liệu đồ thị nền
                    if show_graph and mode == "local" and retrieval_detail:
                        try:
                            # Tránh crash nếu cấu trúc lưu trữ nội bộ thay đổi
                            if hasattr(
                                graph_rag, "chunk_entity_relation_graph"
                            ) and hasattr(
                                graph_rag.chunk_entity_relation_graph, "_graph"
                            ):
                                nx_graph = graph_rag.chunk_entity_relation_graph._graph
                                html_path = render_graph(nx_graph, retrieval_detail)
                                with open(html_path, "r", encoding="utf-8") as f:
                                    st.session_state.html_content = f.read()
                            else:
                                st.warning(
                                    "Could not find underlying NetworkX graph structure."
                                )
                        except Exception as graph_err:
                            st.sidebar.error(f"Graph rendering failed: {graph_err}")

                except Exception as e:
                    st.error(f"Error: {e}")
                    import traceback

                    st.text(traceback.format_exc())

    # Chia bố cục chính rõ ràng: Cột 1 (Văn bản câu hỏi/Trả lời) | Cột 2 (Đồ thị trực quan)
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Query Info")
        st.write(f"**Question:** {question}")
        st.write(f"**Mode:** {mode}")

        if st.session_state.query_response:
            st.subheader("Response")
            st.write(st.session_state.query_response)

            if st.session_state.retrieval_detail:
                st.subheader("Traversal Statistics")
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.metric(
                        "Seed Nodes",
                        len(st.session_state.retrieval_detail.get("seed_nodes", [])),
                    )
                with col_b:
                    st.metric(
                        "PPR Nodes",
                        len(st.session_state.retrieval_detail.get("ppr_scores", {})),
                    )
                with col_c:
                    st.metric(
                        "Timestamps",
                        len(st.session_state.retrieval_detail.get("timestamps", [])),
                    )

                # Show query elapsed time if available
                if st.session_state.query_time_s is not None:
                    st.metric("Query Time (s)", f"{st.session_state.query_time_s:.2f}")

                with st.expander("Raw Retrieval Detail"):
                    st.json(st.session_state.retrieval_detail)

                if len(st.session_state.retrieval_detail.get("seed_nodes", [])) == 0:
                    st.warning(
                        "No seed nodes were retrieved. This is usually a configuration issue (not necessarily bad build output)."
                    )
                    st.markdown(
                        """
                        **Checklist:**
                        1. `Working Directory` points to correct `BUILD_*` folder
                        2. Provider/backend match:
                           - `llama-server` => `openai` + `http://localhost:8080/v1`
                           - `gemini` => valid `GOOGLE_API_KEY`/`GEMINI_API_KEY`
                        3. In `local` mode, ensure retrieval settings are enabled
                        4. Model name matches server alias exactly
                        """
                    )
        else:
            st.info("Please configure settings in the sidebar and click 'Run Query'.")

    with col2:
        if show_graph and mode == "local":
            if st.session_state.html_content:
                st.subheader("Graph Visualization")
                # Dùng alias components.html gọn hơn
                components.html(
                    st.session_state.html_content, height=600, scrolling=True
                )

                st.info("""  
                **Legend:** - 🔴 Red: Seed nodes (from vector search)  
                - 🟠 Orange: Selected entities  
                - 🟡 Yellow: High PPR score nodes  
                - ⚪ Gray: Background nodes  
                """)
            elif st.session_state.query_response:
                st.warning(
                    "No retrieval detail available for graph visualization. Verify your `querying.py` modifications."
                )
        else:
            st.subheader("Instructions")
            st.markdown("""  
            ### How to use:  
            1. Configure settings in the sidebar  
            2. Enter your question  
            3. Click "Run Query"  
              
            ### Required modifications to `tgrag/src/core/querying.py`:  
            Trong hàm `_retrieve_chunks_with_ppr_algorithm`, đảm bảo đã gán các dòng sau vào `retrieval_detail`:  
            ```python  
            retrieval_detail["seed_nodes"] = list(seed_nodes)  
            retrieval_detail["ppr_scores"] = dict(ppr_results)  
            retrieval_detail["timestamps"] = aligned_timestamp_in_query  
            retrieval_detail["relation_metadata"] = relation_metadata  
            ```  
            """)


if __name__ == "__main__":
    main()
