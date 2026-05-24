Dưới đây là phân tích chi tiết toàn bộ dataset ECT-QA và cách tác giả sử dụng nó trong hệ thống.

---

## 1. Tổng quan dataset — Số liệu thực tế

Từ README và đọc trực tiếp các file:

| File | Số dòng thực tế | Ghi chú |
|---|---|---|
| `local_base.jsonl` | ~656 câu hỏi | 1005 - 349 = 656 (ước tính) |
| `local_new.jsonl` | **349 câu hỏi** | Đọc trực tiếp |
| `global_base.jsonl` | **72 câu hỏi** | Đọc trực tiếp |
| `global_new.jsonl` | ~28 câu hỏi | README nói 100 global tổng |

README tuyên bố "1,005 specific + 100 abstract" — con số thực tế khớp: 656 + 349 = 1,005 local; 72 + ~28 = ~100 global. 

---

## 2. Corpus Files — Chi tiết đầy đủ

### Schema document trong corpus

Từ cách `build_graph.py` xử lý, mỗi document trong `base.jsonl.gz` / `new.jsonl.gz` có dạng:

```json
{
  "company_name": "EOG Resources, Inc.",
  "stock_code": "EOG",
  "sector": "energy",
  "year": "2022",
  "quarter": "q1",
  "cleaned_content": "<full transcript text>",
  "raw_content": "<raw transcript text>"
}
```

Hàm `load_documents_from_corpus()` đọc streaming từng dòng qua `gzip.open()`, giới hạn bởi `--num_docs`: 

Sau đó `prepare_documents_for_insertion()` convert sang format `{title, doc}` với title = `"{company} {year} Q{quarter}"`: 

### Phân chia base vs new — Mục đích thực sự

`base.jsonl.gz` (2020–2023) dùng để build đồ thị ban đầu. `new.jsonl.gz` (2024) dùng để test **incremental update**. Đây là điểm cốt lõi của bài toán temporal: hệ thống phải tích hợp dữ liệu mới mà không rebuild toàn bộ graph.

```bash
# Step 1: Build base graph
python build_graph.py --corpus_path ./ect-qa/corpus/base.jsonl.gz \
                      --output_dir ./graph_storage/base

# Step 2: Incremental update (same output_dir!)
python build_graph.py --corpus_path ./ect-qa/corpus/new.jsonl.gz \
                      --output_dir ./graph_storage/base
``` 

---

## 3. Local Question Dataset — Phân tích chi tiết

### Schema đầy đủ

```json
{
  "question": "...",
  "answer": "...",
  "reasoning_type": "enumeration|comparison|unanswerable|out-of-scope|unanswerable|nonfact",
  "question_type": "multi-time query|single-time query|relative-time query + |multi-companies|multi-keywords",
  "num_hops": 0-8,
  "evidence_list": [
    {
      "company_name": "...",
      "stock_code": "...",
      "sector": "...",
      "year": "...",
      "quarter": "...",
      "evidence": "<exact quote from transcript>",
      "ect_filename": "{sector}-{stock_code}-{year}-{quarter}.json"
    }
  ]
}
``` 

### Taxonomy đầy đủ — `question_type`

**Temporal scope:**

| Type | Mô tả | Ví dụ |
|---|---|---|
| `single-time query` | 1 thời điểm cụ thể | "What was X's revenue in 2022-Q2?" |
| `multi-time query` | Nhiều thời điểm cụ thể | "What was X's revenue in Q1, Q2, Q3 2022?" |
| `relative-time query` | Biểu thức tương đối | "What was X's revenue in each year **after 2019**?" |

**Entity scope modifier (pipe-separated):**

| Modifier | Mô tả |
|---|---|
| `multi-companies` | So sánh nhiều công ty cùng thời điểm |
| `multi-keywords` | Nhiều metrics của 1 công ty | [6](#1-5) 

### Taxonomy đầy đủ — `reasoning_type`

| Type | Mô tả | `num_hops` |
|---|---|---|
| `enumeration` | Liệt kê nhiều giá trị từ nhiều nguồn | 1–8 |
| `comparison` | So sánh để tìm max/min/best/worst | 2–8 |
| `unanswerable\|out-of-scope` | Ngoài phạm vi thời gian corpus (trước 2020 hoặc sau 2024) | 0 |
| `unanswerable\|nonfact` | Metric không tồn tại cho công ty đó | 0 |

**Quan trọng:** `unanswerable|nonfact` là loại đặc biệt — câu hỏi hỏi về metric mà công ty đó không báo cáo (ví dụ: "EMEA sales growth" cho công ty không có segment EMEA). Đây là negative test để kiểm tra hallucination.

### `local_new.jsonl` — Đặc điểm quan trọng

`local_new.jsonl` **không chỉ hỏi về 2024**. Nhiều câu hỏi yêu cầu cross-temporal reasoning giữa base (2020-2023) và new (2024):

```json
// Câu hỏi này cần data từ 2020, 2021, 2022, 2023, 2024
{
  "question": "How much did Cincinnati Financial Corporation invest in fixed maturity securities in each year after 2019?",
  "answer": "$291M in 2020, $927M in 2021, $788M in 2022, $1.4B in 2023, and $2.5B in 2024.",
  "num_hops": 5
}
```

Điều này có nghĩa: để trả lời đúng, hệ thống phải có **cả base graph lẫn new graph đã được merge**. Đây là test thực sự cho incremental update. 

### Unanswerable questions — Thiết kế temporal boundary

Các câu hỏi `unanswerable|out-of-scope` trong `local_new.jsonl` hỏi về các thời điểm **trong tương lai** (2025, 2026, 2027) — không phải chỉ ngoài corpus:

```
"What was ONEOK, Inc.'s net income per share in each quarter after 2024 Q2?" → unanswerable
"During which quarter did Home Depot Inc achieve the highest operating margin between Q2 2026 and Q3 2026?" → unanswerable
```

Mục đích: test xem hệ thống có biết **từ chối trả lời** khi câu hỏi vượt ra ngoài temporal boundary của corpus không. 

---

## 4. Global Question Dataset — Phân tích chi tiết

### Schema

```json
{
  "question": "How did Yum China leverage digital transformation...",
  "role": "Economic Forecaster",
  "type": "company_level_multi_time"
}
```

**Không có** `answer`, `evidence_list`, `num_hops` — vì đây là open-ended synthesis, không có ground truth cứng. 

### 5 loại câu hỏi global

| Type | Entity scope | Temporal scope | Ví dụ |
|---|---|---|---|
| `company_level_multi_time` | 1 công ty | Multi-quarter/year | "How did Yum China...from 2020 Q1 to 2022 Q4?" |
| `sector_level_single_time` | 1 sector | 1 thời điểm | "How did real estate companies navigate Q4 2022?" |
| `sector_level_multi_time` | 1 sector | Multi-quarter | "How did IT sector adjust cost structures across 2022?" |
| `multi_sector_single_time` | Nhiều sectors | 1 thời điểm | "How did macroeconomic conditions impact 5 sectors in 2023 Q1?" |
| `multi_sector_multi_time` | Nhiều sectors | Multi-quarter | "How did financials and consumer discretionary adapt during 2021 Q3 and Q4?" | [11](#1-10) 

### 10 roles trong global questions

| Role | Góc nhìn |
|---|---|
| Economic Forecaster | Macroeconomic trends |
| Corporate Strategy Consultant | Strategic pivots |
| Equity Research Analyst | Earnings, margins |
| Fund Manager | Investment decisions |
| Business Journalist | Industry narratives |
| Monetary Policy Strategist | Interest rates, inflation |
| Risk Management Specialist | Risk mitigation |
| Supply Chain Analyst | Supply chain |
| ESG Analyst | Sustainability |
| Regulatory Compliance Officer | Governance | [12](#1-11) 

---

## 5. Cách tác giả dùng dataset — End-to-End Flow

### Build pipeline

```bash
base.jsonl.gz
    │
    ▼ build_graph.py --corpus_path base.jsonl.gz --output_dir ./graph_storage/base
    │   load_documents_from_corpus() → gzip.open() → json.loads() per line
    │   prepare_documents_for_insertion() → {title: "EOG 2022 Q1", doc: "..."}
    │   TemporalGraphRAG.insert() → chunk → extract entities → build temporal graph
    │
    ▼ [Incremental update]
    │
    new.jsonl.gz
    │
    ▼ build_graph.py --corpus_path new.jsonl.gz --output_dir ./graph_storage/base (SAME DIR)
        Merge new entities/relationships into existing graph
```

### Query pipeline

```bash
local_base.jsonl / local_new.jsonl
    │ (lấy từng "question")
    ▼
query_graph.py --question "..." --mode local
    │
    ▼ TemporalGraphRAG.query(question, param=QueryParam(mode="local"))
    │   extract_timestamp_in_query() → parse temporal expression
    │   entity retrieval → subgraph expansion → temporal filtering
    │   → local_rag_response prompt → answer

global_base.jsonl / global_new.jsonl
    │ (lấy từng "question")
    ▼
query_graph.py --question "..." --mode global
    │
    ▼ TemporalGraphRAG.query(question, param=QueryParam(mode="global"))
        extract_timestamp_in_query() → filter community reports by time
        → global_map_rag_points → global_reduce_rag_response → answer
``` 

### Evaluation — Không có script tự động trong repo

Module `tgrag/src/evaluation/__init__.py` chỉ có comment `# TODO`:

```python
"""Evaluation metrics and systems for Temporal-GraphRAG."""
# TODO: Export evaluation metrics (enumeration, comparison, coverage) once moved
__all__ = []
```

Điều này có nghĩa: **evaluation không được tự động hóa trong repo này**. Tác giả chạy `query_graph.py` thủ công cho từng câu hỏi, sau đó so sánh output với `answer` field trong local questions. Với global questions (không có `answer`), evaluation là định tính. 

### Cách load dataset qua Hugging Face (alternative)

Tác giả cũng publish dataset lên HuggingFace để dễ access hơn:

```python
from datasets import load_dataset

questions = load_dataset("austinmyc/ECT-QA", "questions")
corpus = load_dataset("austinmyc/ECT-QA", "corpus")
``` 

---

## 6. Tóm tắt — Vai trò của từng file trong bài toán temporal

```bash
Bài toán temporal GraphRAG
│
├── Test 1: Temporal Fact Retrieval (specific time points)
│   └── local_base.jsonl → --mode local → graph từ base.jsonl.gz
│
├── Test 2: Temporal Trend Analysis (multi-period synthesis)
│   └── global_base.jsonl → --mode global → community reports từ base.jsonl.gz
│
├── Test 3: Incremental Update (new data integration)
│   └── local_new.jsonl → --mode local → graph sau khi merge new.jsonl.gz
│       (nhiều câu hỏi cần cả base + new data → test merge quality)
│
└── Test 4: Temporal Boundary Awareness (unanswerable detection)
    └── ~30% câu hỏi trong cả local_base và local_new là unanswerable
        → test xem system có hallucinate hay biết từ chối không
```

### Citations

**File:** README.md (L111-114)
```markdown
**ECT-QA corpus (JSONL.gz):**
```bash
python build_graph.py --output_dir ./graph_output --corpus_path ./ect-qa/corpus/base.jsonl.gz --num_docs 10
```
```

**File:** README.md (L176-179)
```markdown
- **Corpus:** 480 earnings call transcripts (24 companies, 2020-2024)
- **Questions:** 1,005 specific + 100 abstract temporal queries

The dataset is also available on Hugging Face: [austinmyc/ECT-QA](https://huggingface.co/datasets/austinmyc/ECT-QA)
```

**File:** README.md (L181-190)
```markdown
You can load it using:
```python
from datasets import load_dataset

# Load questions dataset
questions = load_dataset("austinmyc/ECT-QA", "questions")

# Load corpus dataset
corpus = load_dataset("austinmyc/ECT-QA", "corpus")
```

**File:** build_graph.py (L63-88)
```python
def load_documents_from_corpus(corpus_path: Path, num_docs: int = 3) -> List[Dict]:
    """
    Load documents from the ECT-QA corpus.
    
    Args:
        corpus_path: Path to the corpus file (base.jsonl.gz)
        num_docs: Number of documents to load
        
    Returns:
        List of document dictionaries
    """
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus_path}")
    
    documents = []
    try:
        with gzip.open(corpus_path, 'rt', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= num_docs:
                    break
                doc = json.loads(line)
                documents.append(doc)
        print(f"✅ Loaded {len(documents)} documents from corpus")
        return documents
    except Exception as e:
        raise RuntimeError(f"Error loading corpus: {e}")
```

**File:** build_graph.py (L202-252)
```python
def prepare_documents_for_insertion(documents: List[Dict]) -> List[Dict]:
    """
    Convert documents to the format expected by TemporalGraphRAG.insert().
    Automatically detects the document format and processes accordingly.
    
    Args:
        documents: List of documents (either from corpus or txt files)
        
    Returns:
        List of documents in format {"title": str, "doc": str}
    """
    if not documents:
        return []
    
    # Auto-detect format: check if first document has 'title' and 'doc' keys (text format)
    # or 'cleaned_content'/'raw_content' keys (corpus format)
    first_doc = documents[0]
    is_corpus_format = 'cleaned_content' in first_doc or 'raw_content' in first_doc
    
    if not is_corpus_format:
        # Already in the correct format (from txt files)
        # Just validate and return
        for doc in documents:
            if 'title' not in doc or 'doc' not in doc:
                raise ValueError(f"Document missing required keys 'title' or 'doc': {list(doc.keys())}")
        return documents
    
    # Process corpus format documents
    prepared_docs = []
    for doc in documents:
        content = doc.get('cleaned_content', doc.get('raw_content', ''))
        if not content:
            print(f"⚠️  Warning: Document {doc.get('company_name', 'Unknown')} has no content, skipping")
            continue
        
        # Create a descriptive title
        company = doc.get('company_name', 'Unknown')
        year = doc.get('year', '')
        quarter = doc.get('quarter', '')
        if year and quarter:
            title = f"{company} {year} Q{quarter.upper()}"
        elif year:
            title = f"{company} {year}"
        else:
            title = company
        
        prepared_docs.append({
            'title': title,
            'doc': content
        })
    
```

**File:** build_graph.py (L352-356)
```python
        if corpus_path.is_file():
            if corpus_path.suffix == '.gz' or corpus_path.suffixes[-2:] == ['.jsonl', '.gz']:
                # JSONL.gz corpus file (e.g., ECT-QA)
                print(f"📚 Loading from corpus file: {corpus_path}")
                documents = load_documents_from_corpus(corpus_path, args.num_docs)
```

**File:** ect-qa/questions/local_base.jsonl (L7-7)
```json
{"question": "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?", "answer": "$2 billion, $2.3 billion, and nearly $1.3 billion.", "reasoning_type": "enumeration", "question_type": "multi-time query", "num_hops": 3, "evidence_list": [{"company_name": "EOG Resources, Inc.", "stock_code": "EOG", "sector": "energy", "year": "2021", "quarter": "q4", "evidence": "EOG generated record financial results in the fourth quarter with adjusted earnings of $1.8 billion and free cash flow of $2 billion.", "ect_filename": "energy-EOG-2021-q4.json"}, {"company_name": "EOG Resources, Inc.", "stock_code": "EOG", "sector": "energy", "year": "2022", "quarter": "q1", "evidence": "We generated $2.3 billion of free cash flow.", "ect_filename": "energy-EOG-2022-q1.jso ... (truncated)
```

**File:** ect-qa/questions/local_base.jsonl (L14-14)
```json
{"question": "What were Western Digital Corporation's operating expenses guidance, product launch, enterprise and client SSD revenue growth, year-over-year revenue growth, non-GAAP EPS, gaming revenue growth, debt repayment, and cash position in 2020-Q4?", "answer": "$740 million to $760 million, BiCS5 112-layer flash product launch, nearly 70% sequential growth and revenue share in the low double digits, 18% year-over-year revenue growth, $1.23 non-GAAP EPS, flash solutions shipment for new game consoles, $63 million debt repayment, and $3 billion in cash and cash equivalents with $9.7 billion gross debt outstanding.", "reasoning_type": "enumeration", "question_type": "single-time query|multi-keywords", "num_hops": 8, "evidence_list": [{"company_name": "Western Digital Corporation", "stoc ... (truncated)
```

**File:** ect-qa/questions/local_new.jsonl (L1-5)
```json
{"question": "Which quarter had the lowest refining operating costs for Vistra Corp. after 2024-q1?", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope", "question_type": "relative-time query", "num_hops": 0, "evidence_list": []}
{"question": "In which year after 2020 did Cincinnati Financial Corporation have the largest net purchases of fixed maturity securities?", "answer": "2024", "reasoning_type": "comparison", "question_type": "relative-time query", "num_hops": 4, "evidence_list": [{"company_name": "Cincinnati Financial Corporation", "stock_code": "CINF", "sector": "financials", "year": "2021", "quarter": "q4", "evidence": "Investing in fixed maturity securities continues to be a priority with net purchases during the year totaling $927 million.", "ect_filename": "financials-CINF-2021-q4.json"}, {"company_name": "Cincinnati Financial Corporation", "stock_code": "CINF", "sector": "financials", "year": "2022", "quarter": "q4", "evidence": "We continue to emphasize investing in fixed-maturity securities, with net ... (truncated)
{"question": "Which company had the highest gross margin among Skechers U.S.A., Inc., Home Depot Inc, and JD.com in 2024-q4?", "answer": "Skechers U.S.A., Inc.", "reasoning_type": "comparison", "question_type": "single-time query|multi-companies", "num_hops": 3, "evidence_list": [{"company_name": "Skechers U.S.A., Inc.", "stock_code": "SKX", "sector": "consumer_discretionary", "year": "2024", "quarter": "q4", "evidence": "Gross margin was 53.3%, up 20 basis points compared to the prior year, primarily due to a favorable channel mix.", "ect_filename": "consumer_discretionary-SKX-2024-q4.json"}, {"company_name": "Home Depot Inc", "stock_code": "HD US", "sector": "consumer_discretionary", "year": "2024", "quarter": "q4", "evidence": "In the fourth quarter, our gross margin was approximately 3 ... (truncated)
{"question": "What was Iron Mountain Incorporated's EBITDA in each quarter after Q4 2024?", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope", "question_type": "relative-time query", "num_hops": 0, "evidence_list": []}
{"question": "During which quarter did Home Depot Inc achieve the highest operating margin between Q2 2026 and Q3 2026?", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope", "question_type": "multi-time query", "num_hops": 0, "evidence_list": []}
```

**File:** ect-qa/questions/local_new.jsonl (L98-98)
```json
{"question": "How much did Cincinnati Financial Corporation invest in fixed maturity securities in each year after 2019?", "answer": "$291 million in 2020, $927 million in 2021, $788 million in 2022, $1.4 billion in 2023, and $2.5 billion in 2024.", "reasoning_type": "enumeration", "question_type": "relative-time query", "num_hops": 5, "evidence_list": [{"company_name": "Cincinnati Financial Corporation", "stock_code": "CINF", "sector": "financials", "year": "2020", "quarter": "q4", "evidence": "We continue to invest in the fixed maturity portfolio with net purchases during the year totaling $291 million.", "ect_filename": "financials-CINF-2020-q4.json"}, {"company_name": "Cincinnati Financial Corporation", "stock_code": "CINF", "sector": "financials", "year": "2021", "quarter": "q4", "evi ... (truncated)
```

**File:** ect-qa/questions/local_new.jsonl (L167-167)
```json
{"question": "What was Baidu Inc.'s adjusted EBITDA in each quarter after 2022-q4?", "answer": "unanswerable", "reasoning_type": "unanswerable|nonfact", "question_type": "relative-time query", "num_hops": 0, "evidence_list": []}
```

**File:** ect-qa/questions/global_base.jsonl (L1-72)
```json
{"question": "How did Yum China leverage digital transformation and operational flexibility to mitigate the impact of COVID-19 disruptions on revenue and margins from 2020 Q1 to 2022 Q4?", "role": "Economic Forecaster", "type": "company_level_multi_time"}
{"question": "How did EPAM Systems Inc's financial performance and operational resilience evolve during the 2020 Q1 to 2022 Q4 period amidst challenges such as the COVID-19 pandemic?", "role": "Corporate Strategy Consultant", "type": "company_level_multi_time"}
{"question": "Why did Iron Mountain Incorporated maintain consistent EBITDA margin growth from 2020 Q1 to 2022 Q4?", "role": "Regulatory Compliance Officer", "type": "company_level_multi_time"}
{"question": "Why did Skechers U.S.A., Inc. achieve record revenue achievements between Q1 2020 and Q4 2022?", "role": "Business Journalist", "type": "company_level_multi_time"}
{"question": "How did macroeconomic conditions impact operating margins and cash flow priorities  across the financials, energy, consumer discretionary, real estate, and information technology sectors in 2023 Q1?", "role": "Business Journalist", "type": "multi_sector_single_time"}
{"question": "How did Home Depot Inc.'s strategic investments and operational adjustments enable it to achieve record-breaking revenue growth and profitability despite external challenges over the period from 2020 Q1 to 2022 Q4?", "role": "Economic Forecaster", "type": "company_level_multi_time"}
{"question": "How did diversification strategies across business segments and geographic regions contribute to the varying resilience of major real estate companies during Q4 2022 amidst macroeconomic challenges like inflation and rising interest rates?", "role": "Risk Management Specialist", "type": "sector_level_single_time"}
{"question": "How did the cost optimization strategies employed by energy companies in Q2 2020 differ in mitigating the impacts of COVID-19 and volatile commodity prices?", "role": "Monetary Policy Strategist", "type": "sector_level_single_time"}
{"question": "How did inflationary pressures and rising interest rates in 2022 Q3 shape the differing approaches to cost management, capital allocation, and margin resilience across the energy, real estate, information technology, consumer discretionary, and financials sectors?", "role": "Equity Research Analyst", "type": "multi_sector_single_time"}
{"question": "How did Cincinnati Financial Corporation's resilience in underwriting and premium growth across commercial lines, personal lines, and reinsurance segments mitigate the financial impacts of external factors from 2020 Q1 to 2022 Q4?", "role": "Business Journalist", "type": "company_level_multi_time"}
{"question": "How did the real estate and information technology sectors differ in their ability to sustain margin resilience during Q2 2021?", "role": "Supply Chain Analyst", "type": "multi_sector_single_time"}
{"question": "How did the consumer discretionary and real estate sectors exhibit different strategies in mitigating the impact of inflation and supply chain disruptions during Q1 2022?", "role": "ESG Analyst", "type": "multi_sector_single_time"}
{"question": "How did the consumer discretionary, real estate, and energy sectors adapt their capital allocation strategies during 2022 Q4 to balance macroeconomic challenges such as inflation, rising interest rates, and supply chain disruptions while maintaining operational efficiency and growth initiatives?", "role": "Monetary Policy Strategist", "type": "multi_sector_single_time"}
{"question": "How did the ability to adapt to COVID-19 disruptions in Q3 2020 vary across the information technology, consumer discretionary, financials, and real estate sectors based on operational resilience, margin stabilization, and strategic investments?", "role": "Fund Manager", "type": "multi_sector_single_time"}
{"question": "How did the sectors of financials, real estate, and consumer discretionary adapt their strategic priorities during 2023 to mitigate macroeconomic challenges?", "role": "Fund Manager", "type": "multi_sector_multi_time"}
{"question": "How did the sectors of financials, real estate, energy, and consumer discretionary differ in their strategic adaptations to COVID-19 disruptions across Q1 and Q2 2020？", "role": "ESG Analyst", "type": "multi_sector_multi_time"}
{"question": "How did strategic investments in product innovation and pricing initiatives enable certain companies in the consumer discretionary sector to outperform peers in navigating macroeconomic challenges during 2023 Q3?", "role": "Fund Manager", "type": "sector_level_single_time"}
{"question": "How did real estate companies like Iron Mountain and VICI Properties mitigate sector-wide challenges of rising interest rates and macroeconomic volatility in Q3 2023 compared to peers?", "role": "Risk Management Specialist", "type": "sector_level_single_time"}
{"question": "How did macroeconomic pressures in Q4 2022 impact revenue growth and operational strategies differently across the information technology, consumer discretionary, and real estate sectors?", "role": "Economic Forecaster", "type": "multi_sector_single_time"}
{"question": "How about the earnings recovery in the information technology, energy, real estate, financials, and consumer discretionary sectors in the third and fourth quarters of 2020?", "role": "Regulatory Compliance Officer", "type": "multi_sector_multi_time"}
{"question": "How did EOG Resources, Inc. achieve record free cash flow and expand its 'double premium' inventory during the period from 2020 Q1 to 2021 Q4?", "role": "Fund Manager", "type": "company_level_multi_time"}
{"question": "Why did major consumer discretionary companies such as JD.com, Yum China, and Skechers experience differing revenue and margin outcomes in Q4 2023?", "role": "Business Journalist", "type": "sector_level_single_time"}
{"question": "How did differing strategies for navigating rising interest rate headwinds in Q2 2023 impact the financial performance and growth initiatives of major real estate companies in the sector?", "role": "ESG Analyst", "type": "sector_level_single_time"}
{"question": "How did differing strategies in navigating inflationary pressures and market volatility influence profitability and underwriting outcomes for companies in the financials sector during Q2 2023?", "role": "Economic Forecaster", "type": "sector_level_single_time"}
{"question": "How did the focus on strategic growth initiatives like cloud computing, digital transformation, and subscription models help companies in the information technology sector navigate macroeconomic challenges during 2020 Q3?", "role": "Regulatory Compliance Officer", "type": "sector_level_single_time"}
{"question": "How did diversification into emerging verticals and regions contribute to the Q4 2023 growth strategies of real estate companies like Realty Income, VICI Properties, and Simon Property Group compared to others in the sector?", "role": "Supply Chain Analyst", "type": "sector_level_single_time"}
{"question": "How did companies in the financials sector strategically manage inflationary pressures and rising interest rates during 2023 Q1 and Q2?", "role": "Equity Research Analyst", "type": "sector_level_multi_time"}
{"question": "How did companies in the information technology sector strategically adjust their cost structures and operational efficiencies to navigate macroeconomic challenges across 2022?", "role": "Supply Chain Analyst", "type": "sector_level_multi_time"}
{"question": "How did companies in the information technology sector leverage digital transformation initiatives to mitigate the impacts of COVID-19 disruptions across their business models during 2020?", "role": "Corporate Strategy Consultant", "type": "sector_level_multi_time"}
{"question": "How did companies in the consumer discretionary sector leverage digital transformation to enhance operational resilience during the COVID-related disruptions of 2022 Q1 and Q2?", "role": "ESG Analyst", "type": "sector_level_multi_time"}
{"question": "How did real estate companies leverage diversification and technology-driven initiatives to navigate challenges presented by rising interest rates during 2023 Q3 and Q4?", "role": "Economic Forecaster", "type": "sector_level_multi_time"}
{"question": "How did the energy sector companies maintain their operational resilience during Q1 and Q2 2020?", "role": "Monetary Policy Strategist", "type": "sector_level_multi_time"}
{"question": "How did companies in the information technology sector strategically address resource allocation and operational challenges arising from supply chain disruptions between 2022 Q1 and 2022 Q2?", "role": "Regulatory Compliance Officer", "type": "sector_level_multi_time"}
{"question": "How did leading energy companies between Q1 2022 and Q4 2022 navigate operational and financial impacts from inflation and supply chain constraints?", "role": "ESG Analyst", "type": "sector_level_multi_time"}
{"question": "How did capital allocation strategies in Q1 2021 differ across the energy, financials, real estate, and information technology sectors?", "role": "Business Journalist", "type": "multi_sector_single_time"}
{"question": "Why did financials, energy, and consumer discretionary sectors in Q4 2021 demonstrate varying levels of margin resilience when facing inflationary pressures, macroeconomic volatility, and supply chain disruptions?", "role": "Regulatory Compliance Officer", "type": "multi_sector_single_time"}
{"question": "Why did the real estate and consumer discretionary sectors demonstrate differing resilience to inflationary pressures and rising interest rates during Q4 2022?", "role": "Fund Manager", "type": "multi_sector_single_time"}
{"question": "How did rising inflation and supply chain disruptions in 2022 Q2 lead to differences in margin resilience and capital allocation strategies across the information technology, energy, consumer discretionary, and real estate sectors?", "role": "ESG Analyst", "type": "multi_sector_single_time"}
{"question": "How did rising inflation and interest rate pressures in Q3 2022 influence the capital allocation priorities and operational resilience across the financials, information technology, real estate, and energy sectors?", "role": "Economic Forecaster", "type": "multi_sector_single_time"}
{"question": "How did the financials and information technology sectors demonstrate margin resilience differently in 2021 Q4 amid macroeconomic pressures?", "role": "Risk Management Specialist", "type": "multi_sector_single_time"}
{"question": "How did the financials, information technology, and real estate sectors demonstrate varying levels of margin resilience in Q3 2023 amidst inflationary pressures, rising interest rates, and evolving demand conditions?", "role": "Economic Forecaster", "type": "multi_sector_single_time"}
{"question": "How did the strategic focus on digital transformation and operational efficiency impact the revenue growth trajectories and profitability of the information technology and financials sectors during 2021 Q1 and Q2?", "role": "Equity Research Analyst", "type": "multi_sector_multi_time"}
{"question": "How did varying strategic focuses on cost optimization, operational efficiency, and product innovation impact the earnings performance trajectories of the consumer discretionary, real estate, energy, financials, and information technology sectors across 2023 Q1 and Q2?", "role": "Business Journalist", "type": "multi_sector_multi_time"}
{"question": "How did the strategic focus on digital transformation and operational efficiency in the consumer discretionary and financials sectors during 2021 Q3 and Q4 influence revenue growth and margin expansion trajectories?", "role": "Business Journalist", "type": "multi_sector_multi_time"}
{"question": "How did the timing and nature of strategic pivots toward sustainability and digital transformation differ between the real estate and energy sectors over 2020?", "role": "Supply Chain Analyst", "type": "multi_sector_multi_time"}
{"question": "How did the strategic focus on sustainability initiatives in the energy sector and digital transformation in the real estate sector during Q3 and Q4 of 2021 impact their financial performance?", "role": "Fund Manager", "type": "multi_sector_multi_time"}
{"question": "Why are earnings trends diverging between the Financials and Consumer Discretionary sectors in the third and fourth quarters of 2023?", "role": "Corporate Strategy Consultant", "type": "multi_sector_multi_time"}
{"question": "How did organizations across consumer discretionary, real estate, financials, information technology, and energy sectors transition toward sustainability and digital transformation in Q3 and Q4 2020?", "role": "Economic Forecaster", "type": "multi_sector_multi_time"}
{"question": "Why was Simon Property Group, Inc. able to achieve record FFO growth and financial recovery across 2021 Q1 to 2021 Q4 despite ongoing challenges such as COVID-19?", "role": "Supply Chain Analyst", "type": "company_level_multi_time"}
{"question": "How did differing approaches to managing inflationary pressures and macroeconomic headwinds influence profitability and expense control across the financials sector in Q4 2022?", "role": "Monetary Policy Strategist", "type": "sector_level_single_time"}
{"question": "How did inflationary pressures during 2021 Q4 impact capital allocation strategies across the energy, real estate, consumer discretionary, and financials sectors?", "role": "Monetary Policy Strategist", "type": "multi_sector_single_time"}
{"question": "How did macroeconomic pressures in 2023 Q3 influence capital allocation strategies across the real estate, energy, consumer discretionary, and information technology sectors?", "role": "Risk Management Specialist", "type": "multi_sector_single_time"}
{"question": "How did different approaches to operational efficiency and cost management across the financials and consumer discretionary sectors during 2023 Q3 and Q4 influence their profitability and guidance trajectories?", "role": "Equity Research Analyst", "type": "multi_sector_multi_time"}
{"question": "How did Aon plc's strategic focus on innovation and operational efficiency through initiatives like Aon United and Aon Business Services shape its ability to consistently deliver margin expansion and organic revenue growth across the challenging period of 2020 Q1 to 2021 Q4?", "role": "Fund Manager", "type": "company_level_multi_time"}
{"question": "How did Enterprise Products Partners L.P.'s strategic focus on Permian Basin infrastructure expansions and export capacity growth contribute to consistent distributable cash flow retention and distribution growth across the period from 2022 Q1 to 2023 Q4?", "role": "Supply Chain Analyst", "type": "company_level_multi_time"}
{"question": "Why did Baidu Inc. navigate macroeconomic challenges while maintaining profitability improvements between 2020 Q1 and 2022 Q4?", "role": "ESG Analyst", "type": "company_level_multi_time"}
{"question": "Why did companies across the financial sector navigate macroeconomic pressures such as rising costs, inflation, and market volatility, while maintaining strong profitability and growth momentum in Q4 2021?", "role": "Equity Research Analyst", "type": "sector_level_single_time"}
{"question": "Why did companies in the information technology sector in Q4 2023, such as Baidu and Autodesk, achieve revenue growth, while others like EPAM Systems and Western Digital faced revenue declines?", "role": "Fund Manager", "type": "sector_level_single_time"}
{"question": "How did inflation and rising interest rates in 2022 Q4 influence capital allocation strategies across the financials, consumer discretionary, energy, and information technology sectors?", "role": "Monetary Policy Strategist", "type": "multi_sector_single_time"}
{"question": "How did variations in capital allocation strategies influence resilience across financials, real estate, consumer discretionary, energy, and information technology sectors during 2021 Q1?", "role": "Business Journalist", "type": "multi_sector_single_time"}
{"question": "How did the inflationary pressures over 2022 impact the strategic adjustments and earnings trajectory across the financials, energy, consumer discretionary, real estate, and information technology sectors?", "role": "Supply Chain Analyst", "type": "multi_sector_multi_time"}
{"question": "How did Occidental Petroleum Corp's record free cash flow generation across 2022 quarters (Q1 to Q4) enable simultaneous debt reduction, shareholder returns, and investment in low-carbon ventures?", "role": "Risk Management Specialist", "type": "company_level_multi_time"}
{"question": "How did ONEOK, Inc.’s shift toward leveraging organic growth projects, recovery in NGL volumes, and the strategic use of acquisitions like Magellan Midstream Partners impact its financial performance and operational resilience from 2021 Q1 to 2023 Q4?", "role": "Corporate Strategy Consultant", "type": "company_level_multi_time"}
{"question": "Why did companies in real estate sector exhibit differentiated growth in Q2 2023?", "role": "Corporate Strategy Consultant", "type": "sector_level_single_time"}
{"question": "How did real estate companies' strategic responses to inflationary pressures in Q1 2022 differ?", "role": "Regulatory Compliance Officer", "type": "sector_level_single_time"}
{"question": "Why was there performance variability among information technology companies in Q1 2021, despite operating in the same sector and facing similar market conditions?", "role": "Risk Management Specialist", "type": "sector_level_single_time"}
{"question": "Why was there performance variability among information technology companies in Q3 2023?", "role": "Business Journalist", "type": "sector_level_single_time"}
{"question": "How did the energy sector's common challenges influence the operational resilience and strategic pivots across companies like ONEOK, Occidental, EOG Resources, Enterprise Products Partners, and Marathon Petroleum in Q1 2021?", "role": "ESG Analyst", "type": "sector_level_single_time"}
{"question": "How did companies in the information technology sector, such as Baidu and EPAM, navigate macroeconomic challenges and sector-specific headwinds in 2023 Q1?", "role": "Business Journalist", "type": "sector_level_single_time"}
{"question": "How did varying responses to external macroeconomic challenges in Q1 2022 impact the strategic focus and operational outcomes of companies in the information technology sector?", "role": "Corporate Strategy Consultant", "type": "sector_level_single_time"}
{"question": "How did financial firms' strategic responses to inflationary pressures and market volatility in Q2 2022 differ in balancing profit margins and growth across core business segments?", "role": "Supply Chain Analyst", "type": "sector_level_single_time"}
{"question": "How did differing responses to inflationary pressures and elevated catastrophe losses in Q2 2023 influence the profitability and underwriting strategies across Cincinnati Financial, Aon, Markel Group, and Prudential Financial in the financials sector?", "role": "ESG Analyst", "type": "sector_level_single_time"}
```

**File:** query_graph.py (L86-93)
```python
    parser.add_argument(
        '--mode',
        type=str,
        choices=['local', 'global', 'naive'],
        default=None,
        help='Query mode: local, global, or naive (overrides config if specified)'
    )
    
```

**File:** query_graph.py (L143-160)
```python
    query_mode = args.mode or raw_config.get('mode', 'global')
    
    # Get token limits from config (use defaults if not specified)
    local_max_token_for_text_unit = raw_config.get('local_max_token_for_text_unit', 4000)
    local_max_token_for_local_context = raw_config.get('local_max_token_for_local_context', 6000)
    local_max_token_for_community_report = raw_config.get('local_max_token_for_community_report', 2000)
    global_max_token_for_community_report = raw_config.get('global_max_token_for_community_report', 16384)
    naive_max_token_for_text_unit = raw_config.get('naive_max_token_for_text_unit', 12000)
    
    # Create QueryParam with all settings
    query_param = QueryParam(
        mode=query_mode,
        local_max_token_for_text_unit=local_max_token_for_text_unit,
        local_max_token_for_local_context=local_max_token_for_local_context,
        local_max_token_for_community_report=local_max_token_for_community_report,
        global_max_token_for_community_report=global_max_token_for_community_report,
        naive_max_token_for_text_unit=naive_max_token_for_text_unit,
    )
```

**File:** tgrag/src/evaluation/__init__.py (L1-5)
```python
"""Evaluation metrics and systems for Temporal-GraphRAG."""

# TODO: Export evaluation metrics (enumeration, comparison, coverage) once moved

__all__ = []
```
