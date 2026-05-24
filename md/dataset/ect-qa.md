# ECT-QA Benchmark Dataset

## Dataset Overview & Structure

ECT-QA (**Earnings Call Transcript Question Answering**) là benchmark chính được dùng để đánh giá hệ thống Temporal-GraphRAG. Dataset được thiết kế đặc biệt cho bài toán **time-sensitive QA** trên dữ liệu tài chính thực tế có sự tiến hóa theo thời gian. 

### Thống kê tổng quan

| Thành phần | Giá trị |
|---|---|
| Tổng số transcript | 480 |
| Số công ty | 24 |
| Khoảng thời gian | 2020–2024 (5 năm) |
| Tổng số câu hỏi | 1,105 |
| Local questions | 1,005 (specific facts) |
| Global questions | 100 (trends/summaries) |
| Domain | Financial earnings calls |
| Format | JSONL (gzipped corpus) |

### Cấu trúc thư mục

```
ect-qa/
├── corpus/
│   ├── base.jsonl.gz      # 2020–2023 (~80% data)
│   └── new.jsonl.gz       # 2024 (~20% data)
└── questions/
    ├── local_base.jsonl   # Câu hỏi specific facts cho base corpus
    ├── local_new.jsonl    # Câu hỏi specific facts cho new corpus
    ├── global_base.jsonl  # Câu hỏi trend cho base corpus
    └── global_new.jsonl   # Câu hỏi trend cho new corpus
``` 

> **Lưu ý thực tế:** Khi kiểm tra thư mục `ect-qa/questions/` trong repo, chỉ có 3 file: `global_base.jsonl`, `local_base.jsonl`, `local_new.jsonl`. File `global_new.jsonl` được tham chiếu trong README nhưng không có trong repo.

### Mục tiêu thiết kế — 3 khả năng cần test

```
ECT-QA Design Goals
├── Temporal Fact Retrieval  → Local questions (specific time points)
├── Temporal Trend Analysis  → Global questions (multi-period synthesis)
└── Incremental Update       → Base/New split (2020-2023 vs 2024)
```

---

## Corpus Files (base & new)

### Format file

Cả hai file đều dùng **JSONL.GZ** (gzip-compressed JSON Lines):
- Mỗi dòng = 1 JSON object = 1 transcript
- UTF-8 encoded, streaming-friendly

### Schema của mỗi document trong corpus

Dựa trên cách `build_graph.py` xử lý, mỗi document có các field:

```json
{
  "company_name": "EOG Resources, Inc.",
  "stock_code": "EOG",
  "sector": "energy",
  "year": "2022",
  "quarter": "q1",
  "cleaned_content": "Full transcript text...",
  "raw_content": "Raw transcript text..."
}
```

Khi load vào hệ thống, `prepare_documents_for_insertion()` tự động tạo title theo format `"{company_name} {year} Q{quarter}"`: 

### Cách load corpus trong source code

Hàm `load_documents_from_corpus()` trong `build_graph.py` dùng `gzip.open()` để đọc streaming từng dòng: 

Hệ thống tự detect format `.jsonl.gz` để chọn đúng loader: 

### base.jsonl.gz vs new.jsonl.gz

| File | Thời gian | Mục đích |
|---|---|---|
| `base.jsonl.gz` | 2020–2023 (~384 docs, 80%) | Build đồ thị ban đầu |
| `new.jsonl.gz` | 2024 (~96 docs, 20%) | Test incremental update |

**Tại sao cần split này?** Đây là thiết kế để test khả năng **incremental graph update** — hệ thống phải tích hợp dữ liệu mới (2024) vào đồ thị đã có (2020-2023) mà không cần rebuild toàn bộ.

```bash
# Build từ base corpus
python build_graph.py --corpus_path ./ect-qa/corpus/base.jsonl.gz --output_dir ./graph_storage/base

# Incremental update với new corpus
python build_graph.py --corpus_path ./ect-qa/corpus/new.jsonl.gz --output_dir ./graph_storage/base
```

### 5 sectors trong corpus

1. **Financials**: Aon, Cincinnati Financial, Markel Group, Prudential Financial
2. **Energy**: EOG Resources, Enterprise Products Partners, Marathon Petroleum, Occidental Petroleum, ONEOK
3. **Consumer Discretionary**: Home Depot, JD.com, Skechers, Yum China
4. **Real Estate**: Iron Mountain, Macerich, Realty Income, Simon Property Group, VICI Properties
5. **Information Technology**: Autodesk, Baidu, EPAM Systems, Western Digital

---

## Local Question Dataset

### Mục đích

Local questions test khả năng **truy xuất fact cụ thể có ràng buộc thời gian** — ví dụ: "EOG's free cash flow in Q3 2023 là bao nhiêu?". Đây là loại câu hỏi được evaluate bằng `--mode local`.

### Schema của mỗi câu hỏi

```json
{
  "question": "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?",
  "answer": "$2 billion, $2.3 billion, and nearly $1.3 billion.",
  "reasoning_type": "enumeration",
  "question_type": "multi-time query",
  "num_hops": 3,
  "evidence_list": [
    {
      "company_name": "EOG Resources, Inc.",
      "stock_code": "EOG",
      "sector": "energy",
      "year": "2021",
      "quarter": "q4",
      "evidence": "EOG generated record financial results in the fourth quarter with adjusted earnings of $1.8 billion and free cash flow of $2 billion.",
      "ect_filename": "energy-EOG-2021-q4.json"
    }
  ]
}
```

### Taxonomy câu hỏi — 2 chiều phân loại

**Chiều 1: Temporal scope** (`question_type`)

| Type | Mô tả | Ví dụ thực tế |
|---|---|---|
| `single-time query` | 1 thời điểm cụ thể | "What was X's revenue in 2022-Q2?" |
| `multi-time query` | Nhiều thời điểm cụ thể | "What was X's revenue in Q1, Q2, Q3 of 2022?" |
| `relative-time query` | Biểu thức thời gian tương đối | "How much did X invest in each year before 2023?" |

**Chiều 2: Entity scope** (modifier trong `question_type`)

| Modifier | Mô tả | Ví dụ thực tế |
|---|---|---|
| `multi-companies` | So sánh nhiều công ty | "What were operating margins of HD, Crocs, Skechers in 2021-Q1?" |
| `multi-keywords` | Nhiều metrics cho 1 công ty | "What were Western Digital's 8 metrics in 2020-Q4?" | [7](#0-6) 

### Reasoning types

| Type | Mô tả | `num_hops` |
|---|---|---|
| `enumeration` | Liệt kê nhiều giá trị từ nhiều nguồn | 1–8 |
| `comparison` | So sánh để tìm max/min/best | 2–8 |
| `unanswerable\|out-of-scope` | Ngoài phạm vi thời gian corpus | 0 |
| `unanswerable\|nonfact` | Câu hỏi chủ quan/không có fact | 0 | [8](#0-7) 

### Field `num_hops` — độ phức tạp multi-hop

`num_hops` = số lượng evidence pieces cần để trả lời câu hỏi. Đây là chỉ số đo độ phức tạp retrieval:

```
num_hops = 0  → Unanswerable (không cần retrieve)
num_hops = 1  → Single-hop (1 transcript)
num_hops = 3  → Multi-hop (3 transcripts khác nhau)
num_hops = 8  → High complexity (8 facts từ 1 transcript)
``` 

### Evidence linking mechanism

Mỗi câu hỏi có `evidence_list` liên kết trực tiếp đến đoạn text trong transcript gốc. Field `ect_filename` theo format `{sector}-{stock_code}-{year}-{quarter}.json`. Điều này cho phép:
1. **Ground truth verification**: Trace answer về source document
2. **Retrieval evaluation**: Đánh giá xem system có retrieve đúng evidence không
3. **Answer evaluation**: So sánh generated answer với quoted evidence  

### Ví dụ thực tế từ `local_base.jsonl`

**Comparison question (num_hops=6):**
```
Q: "In which quarter did EPAM Systems Inc. have the lowest GAAP gross margin from 2021 to mid-2022?"
A: "Q2 2022"
reasoning_type: "comparison", num_hops: 6
```

**Relative-time enumeration (num_hops=3):**
```
Q: "How much did Cincinnati Financial Corporation invest in fixed maturity securities in each year before 2023?"
A: "$291 million in 2020, $927 million in 2021, and $788 million in 2022."
reasoning_type: "enumeration", num_hops: 3
```

**Multi-keyword single-time (num_hops=8):**
```
Q: "What were Western Digital Corporation's operating expenses guidance, product launch, enterprise and client SSD revenue growth, year-over-year revenue growth, non-GAAP EPS, gaming revenue growth, debt repayment, and cash position in 2020-Q4?"
reasoning_type: "enumeration", num_hops: 8
``` 

### Thống kê local questions

| File | Số câu hỏi | Mục đích |
|---|---|---|
| `local_base.jsonl` | ~1,005 | Evaluate base corpus (2020-2023) |
| `local_new.jsonl` | 96 | Test incremental update (2024) |

---

## Global Question Dataset

### Mục đích

Global questions test khả năng **tổng hợp xu hướng và phân tích cross-temporal** — ví dụ: "How did tech companies navigate 2022 challenges?". Evaluate bằng `--mode global` (map-reduce pipeline qua community reports).

### Schema — đơn giản hơn local

```json
{
  "question": "How did Yum China leverage digital transformation and operational flexibility to mitigate the impact of COVID-19 disruptions on revenue and margins from 2020 Q1 to 2022 Q4?",
  "role": "Economic Forecaster",
  "type": "company_level_multi_time"
}
```

**Khác biệt quan trọng so với local**: Global questions **không có** `answer`, `evidence_list`, hay `num_hops` — vì câu trả lời là open-ended synthesis, không có ground truth cứng.

### Taxonomy 5 loại câu hỏi

| Type | Entity scope | Temporal scope | Ví dụ |
|---|---|---|---|
| `company_level_multi_time` | 1 công ty | Nhiều quý/năm | "How did Yum China leverage digital transformation...from 2020 Q1 to 2022 Q4?" |
| `sector_level_single_time` | 1 sector, nhiều công ty | 1 thời điểm | "How did real estate companies navigate Q4 2022?" |
| `sector_level_multi_time` | 1 sector, nhiều công ty | Nhiều thời điểm | "How did IT sector adjust cost structures across 2022?" |
| `multi_sector_single_time` | Nhiều sectors | 1 thời điểm | "How did macroeconomic conditions impact margins across 5 sectors in 2023 Q1?" |
| `multi_sector_multi_time` | Nhiều sectors | Nhiều thời điểm | "How did financials, real estate, consumer discretionary adapt during 2023?" | 

### Role-based categorization

Mỗi câu hỏi được gán một `role` đại diện cho góc nhìn phân tích chuyên nghiệp:

| Role | Focus |
|---|---|
| Economic Forecaster | Macroeconomic trends, revenue trajectories |
| Corporate Strategy Consultant | Strategic pivots, operational resilience |
| Equity Research Analyst | Earnings performance, margin analysis |
| Fund Manager | Investment decisions, portfolio management |
| Business Journalist | Industry narratives, company comparisons |
| Monetary Policy Strategist | Interest rates, inflation, capital allocation |
| Risk Management Specialist | Risk mitigation, operational challenges |
| Supply Chain Analyst | Supply chain disruptions |
| ESG Analyst | Sustainability, digital transformation |
| Regulatory Compliance Officer | Compliance, governance |

### Thống kê global questions

| File | Số câu hỏi | Thời gian |
|---|---|---|
| `global_base.jsonl` | 73 | 2020 Q1 – 2023 Q4 |
| `global_new.jsonl` | 29 | 2024 Q1 – 2024 Q4 |
| **Tổng** | **102** | **2020–2024** |

---

## So sánh Local vs Global — Mapping vào Query Modes

```
Local Questions ──→ --mode local  ──→ Entity retrieval + subgraph expansion
                                       Temporal extraction → entity lookup → fact synthesis

Global Questions ──→ --mode global ──→ Map-Reduce over community reports
                                        Temporal filter → community reports → map → reduce
```

| Aspect | Local | Global |
|---|---|---|
| Focus | Specific facts | Trends & summaries |
| Evidence | Explicit `evidence_list` | Không có (open-ended) |
| Answer | Concise (numbers, values) | Narrative synthesis |
| Evaluation | Objective (vs ground truth) | Subjective quality |
| `num_hops` | 0–8 | N/A |
| Temporal scope | Specific time points | Multi-quarter/multi-year |

---

## Flow xử lý ECT-QA trong hệ thống

```
CORPUS (base.jsonl.gz / new.jsonl.gz)
    │
    ▼ build_graph.py → load_documents_from_corpus()
    │   gzip.open() → json.loads() per line
    │   prepare_documents_for_insertion() → {title, doc}
    │
    ▼ TemporalGraphRAG.insert()
    │   Chunking → Entity Extraction → Graph Building
    │
    ▼ graph_storage/ (persisted temporal graph)
    │
    ▼ query_graph.py
    │
    ├── local_*.jsonl → --mode local
    │   extract_timestamp_in_query → entity retrieval → subgraph expansion
    │   → local_rag_response prompt → answer
    │
    └── global_*.jsonl → --mode global
        extract_timestamp_in_query → community reports
        → global_map_rag_points → global_reduce_rag_response → answer
```

### Citations

**File:** README.md (L172-179)
```markdown
## ECT-QA Dataset

High-quality benchmark for time-sensitive question answering:

- **Corpus:** 480 earnings call transcripts (24 companies, 2020-2024)
- **Questions:** 1,005 specific + 100 abstract temporal queries

The dataset is also available on Hugging Face: [austinmyc/ECT-QA](https://huggingface.co/datasets/austinmyc/ECT-QA)
```

**File:** README.md (L203-211)
```markdown
├── ect-qa/                         # ECT-QA dataset               
│   ├── corpus/                     
│   │   ├── base.jsonl.gz           # 2020 - 2023
│   │   └── new.jsonl.gz            # 2024
│   └── questions/           
│       ├── local_base.jsonl 
│       ├── local_new.jsonl 
│       ├── global_base.jsonl 
│       └── global_new.jsonl    
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

**File:** ect-qa/questions/local_base.jsonl (L1-6)
```json
{"question": "In which quarter did Nomura Holdings, Inc. achieve the highest refining and marketing margin capture between 2022 Q4 and 2023 Q3?", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope", "question_type": "multi-time query", "num_hops": 0, "evidence_list": []}

{"question": "What was Home Depot Inc.'s gross margin in each quarter before 2018 Q3?", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope", "question_type": "relative-time query", "num_hops": 0, "evidence_list": []}

{"question": "What was Fifth Third Bancorp's net income in each quarter from Q4 2021 to Q2 2023?", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope", "question_type": "multi-time query", "num_hops": 0, "evidence_list": []}

{"question": "Which company reported the highest free cash flow among Molson Coors Beverage Co, Gruma, Equitable Holdings, Inc., and Aflac Incorporated in 2023-q2?", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope", "question_type": "single-time query|multi-companies", "num_hops": 0, "evidence_list": []}

{"question": "What was Aspirasi Hidup Indonesia's operating cash flow in each quarter from 2021 Q1 to 2022 Q3?", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope", "question_type": "multi-time query", "num_hops": 0, "evidence_list": []}

{"question": "What were Applied Materials, Inc.'s operational performance, capital expenditures guidance, well connections and growth, and ethane recovery expectations in 2022?", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope", "question_type": "single-time query|multi-keywords", "num_hops": 0, "evidence_list": []}
```

**File:** ect-qa/questions/local_base.jsonl (L7-7)
```json
{"question": "What was EOG Resources, Inc.'s free cash flow in each quarter for 2021-Q4, 2022-Q1, and 2022-Q2?", "answer": "$2 billion, $2.3 billion, and nearly $1.3 billion.", "reasoning_type": "enumeration", "question_type": "multi-time query", "num_hops": 3, "evidence_list": [{"company_name": "EOG Resources, Inc.", "stock_code": "EOG", "sector": "energy", "year": "2021", "quarter": "q4", "evidence": "EOG generated record financial results in the fourth quarter with adjusted earnings of $1.8 billion and free cash flow of $2 billion.", "ect_filename": "energy-EOG-2021-q4.json"}, {"company_name": "EOG Resources, Inc.", "stock_code": "EOG", "sector": "energy", "year": "2022", "quarter": "q1", "evidence": "We generated $2.3 billion of free cash flow.", "ect_filename": "energy-EOG-2022-q1.jso ... (truncated)
```

**File:** ect-qa/questions/local_base.jsonl (L8-19)
```json
{"question": "In which quarter did EPAM Systems Inc. have the lowest GAAP gross margin from 2021 to mid-2022?", "answer": "Q2 2022", "reasoning_type": "comparison", "question_type": "multi-time query", "num_hops": 6, "evidence_list": [{"company_name": "EPAM Systems Inc", "stock_code": "EPAM US", "sector": "information_technology", "year": "2021", "quarter": "q1", "evidence": "Moving on to income statement, our GAAP gross margin for the quarter was 33.5%, compared to 34.9% in Q1 of last year.", "ect_filename": "information_technology-EPAM_US-2021-q1.json"}, {"company_name": "EPAM Systems Inc", "stock_code": "EPAM US", "sector": "information_technology", "year": "2021", "quarter": "q2", "evidence": "Our GAAP gross margin for the quarter was 33.8%, compared to 33.7% in Q2 of last year.", "ect ... (truncated)

{"question": "How much did Cincinnati Financial Corporation invest in fixed maturity securities in each year before 2023?", "answer": "$291 million in 2020, $927 million in 2021, and $788 million in 2022.", "reasoning_type": "enumeration", "question_type": "relative-time query", "num_hops": 3, "evidence_list": [{"company_name": "Cincinnati Financial Corporation", "stock_code": "CINF", "sector": "financials", "year": "2020", "quarter": "q4", "evidence": "We continue to invest in the fixed maturity portfolio with net purchases during the year totaling $291 million.", "ect_filename": "financials-CINF-2020-q4.json"}, {"company_name": "Cincinnati Financial Corporation", "stock_code": "CINF", "sector": "financials", "year": "2021", "quarter": "q4", "evidence": "Investing in fixed maturity securi ... (truncated)

{"question": "What were Skechers U.S.A., Inc.'s quarterly sales in each quarter from Q4 2021 to Q3 2022?", "answer": "$1.65 billion, over $1.8 billion, $1.87 billion, and $1.88 billion.", "reasoning_type": "enumeration", "question_type": "multi-time query", "num_hops": 4, "evidence_list": [{"company_name": "Skechers U.S.A., Inc.", "stock_code": "SKX", "sector": "consumer_discretionary", "year": "2021", "quarter": "q4", "evidence": "Skechers achieved a new fourth quarter sales record of $1.65 billion, the second highest quarterly sales in the company's history, and gross margins of 48.6%.", "ect_filename": "consumer_discretionary-SKX-2021-q4.json"}, {"company_name": "Skechers U.S.A., Inc.", "stock_code": "SKX", "sector": "consumer_discretionary", "year": "2022", "quarter": "q1", "evidence": ... (truncated)

{"question": "How much cash, cash equivalents, and investments did Skechers U.S.A., Inc. have at the end of each quarter between 2022 Q2 and 2022 Q4?", "answer": "$946.4 million in 2022 Q2, $681.5 million in 2022 Q3, and $788.4 million in 2022 Q4.", "reasoning_type": "enumeration", "question_type": "multi-time query", "num_hops": 3, "evidence_list": [{"company_name": "Skechers U.S.A., Inc.", "stock_code": "SKX", "sector": "consumer_discretionary", "year": "2022", "quarter": "q2", "evidence": "We ended the quarter with $946.4 million in cash, cash equivalents and investments.", "ect_filename": "consumer_discretionary-SKX-2022-q2.json"}, {"company_name": "Skechers U.S.A., Inc.", "stock_code": "SKX", "sector": "consumer_discretionary", "year": "2022", "quarter": "q3", "evidence": "We ended th ... (truncated)

{"question": "In which quarter in 2023 did jd.com record the highest non-GAAP net income attributable to ordinary shareholders?", "answer": "Q3 2023", "reasoning_type": "comparison", "question_type": "multi-time query", "num_hops": 4, "evidence_list": [{"company_name": "JD.com", "stock_code": "JD US", "sector": "consumer_discretionary", "year": "2023", "quarter": "q1", "evidence": "As we continue to focus on our core businesses to drive high-quality growth and further optimize operating efficiency, we recorded RMB 7.6 billion non-GAAP net income attributable to ordinary shareholders in Q1, and non-GAAP net margin rise at 3.1%, up 144 basis points compared to a year ago.", "ect_filename": "consumer_discretionary-JD_US-2023-q1.json"}, {"company_name": "JD.com", "stock_code": "JD US", "sector ... (truncated)

{"question": "In which quarter before 2021-Q1 did State Bank of India report the highest cash flow from operations?", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope", "question_type": "relative-time query", "num_hops": 0, "evidence_list": []}

{"question": "What were Western Digital Corporation's operating expenses guidance, product launch, enterprise and client SSD revenue growth, year-over-year revenue growth, non-GAAP EPS, gaming revenue growth, debt repayment, and cash position in 2020-Q4?", "answer": "$740 million to $760 million, BiCS5 112-layer flash product launch, nearly 70% sequential growth and revenue share in the low double digits, 18% year-over-year revenue growth, $1.23 non-GAAP EPS, flash solutions shipment for new game consoles, $63 million debt repayment, and $3 billion in cash and cash equivalents with $9.7 billion gross debt outstanding.", "reasoning_type": "enumeration", "question_type": "single-time query|multi-keywords", "num_hops": 8, "evidence_list": [{"company_name": "Western Digital Corporation", "stoc ... (truncated)

{"question": "What were Iron Mountain Incorporated’s EBITDA, adjusted EBITDA, constant currency revenue growth, adjusted EBITDA margin, and AFFO growth in 2022-Q1?", "answer": "$431 million, $431 million, 10%, up 100 basis points, and $284 million or $0.97 per share.", "reasoning_type": "enumeration", "question_type": "single-time query|multi-keywords", "num_hops": 5, "evidence_list": [{"company_name": "Iron Mountain Incorporated", "stock_code": "IRM", "sector": "real_estate", "year": "2022", "quarter": "q1", "evidence": "We achieved our highest ever quarterly revenue of $1.25 billion, exceeding our expectations of $1.2 billion, yielding 10% of total organic revenue growth, and an all-time record EBITDA of $431 million.", "ect_filename": "real_estate-IRM-2022-q1.json"}, {"company_name": "I ... (truncated)
{"question": "In which quarter before 2021-Q1 did EPAM Systems Inc. record the highest Non-GAAP income from operations as a percentage of revenue?", "answer": "Q3 2020", "reasoning_type": "comparison", "question_type": "relative-time query", "num_hops": 4, "evidence_list": [{"company_name": "EPAM Systems Inc", "stock_code": "EPAM US", "sector": "information_technology", "year": "2021", "quarter": "q1", "evidence": "Non-GAAP income from operations was $136.9 million or 17.5% of revenue in the quarter, compared to $105.3 million, 16.2% of revenue in Q1 of last year.", "ect_filename": "information_technology-EPAM_US-2021-q1.json"}, {"company_name": "EPAM Systems Inc", "stock_code": "EPAM US", "sector": "information_technology", "year": "2020", "quarter": "q2", "evidence": "Non-GAAP income fro ... (truncated)
{"question": "During the period from 2020-q3 to 2021-q2, in which quarter did Cincinnati Financial Corporation report the largest improvement in its property casualty combined ratio compared to the same quarter of the previous year?", "answer": "2021-q2", "reasoning_type": "comparison", "question_type": "multi-time query", "num_hops": 4, "evidence_list": [{"company_name": "Cincinnati Financial Corporation", "stock_code": "CINF", "sector": "financials", "year": "2020", "quarter": "q3", "evidence": "The combined ratio for personal lines was 1.1 percentage points higher than the third quarter a year ago, with underlying improved performance masked by catastrophe losses that were 15.8 points higher.", "ect_filename": "financials-CINF-2020-q3.json"}, {"company_name": "Cincinnati Financial Corpo ... (truncated)

{"question": "What were the operating margins of Home Depot Inc, Crocs, Inc., and Skechers U.S.A., Inc. in 2021-q1?", "answer": "15.4%, 27.3%, and 11%.", "reasoning_type": "enumeration", "question_type": "single-time query|multi-companies", "num_hops": 3, "evidence_list": [{"company_name": "Home Depot Inc", "stock_code": "HD US", "sector": "consumer_discretionary", "year": "2021", "quarter": "q1", "evidence": "Our operating margin for the first quarter was 15.4%, compared to 11.6% in the first quarter of 2020.", "ect_filename": "consumer_discretionary-HD_US-2021-q1.json"}, {"company_name": "Crocs, Inc.", "stock_code": "CROX", "sector": "consumer_discretionary", "year": "2021", "quarter": "q1", "evidence": "Adjusted operating margin rose from 9.4% to 27.3%, benefiting from gross margin expa ... (truncated)

{"question": "What was Enterprise Products Partners L.P.'s cash flow from operations in each quarter from Q1 2020 to Q1 2021?", "answer": "$2 billion, $1.2 billion, $1.1 billion, $1.6 billion, and $2 billion.", "reasoning_type": "enumeration", "question_type": "multi-time query", "num_hops": 5, "evidence_list": [{"company_name": "Enterprise Products Partners L.P.", "stock_code": "EPD", "sector": "energy", "year": "2020", "quarter": "q1", "evidence": "Cash flow from operations was $2 billion for the first quarter of 2020 compared to $1.2 billion for the first quarter 2019.", "ect_filename": "energy-EPD-2020-q1.json"}, {"company_name": "Enterprise Products Partners L.P.", "stock_code": "EPD", "sector": "energy", "year": "2020", "quarter": "q2", "evidence": "Cash flow from operations was $1.2 ... (truncated)
```

**File:** ect-qa/questions/global_base.jsonl (L1-10)
```json
{"question": "How did Yum China leverage digital transformation and operational flexibility to mitigate the impact of COVID-19 disruptions on revenue and margins from 2020 Q1 to 2022 Q4?", "role": "Economic Forecaster", "type": "company_level_multi_time"}

{"question": "How did EPAM Systems Inc's financial performance and operational resilience evolve 
during the 2020 Q1 to 2022 Q4 period amidst challenges such as the COVID-19 pandemic?", "role": "Corporate Strategy Consultant", "type": "company_level_multi_time"}

{"question": "Why did Iron Mountain Incorporated maintain consistent EBITDA margin growth from 2020 Q1 to 2022 Q4?", "role": "Regulatory Compliance Officer", "type": "company_level_multi_time"}

{"question": "Why did Skechers U.S.A., Inc. achieve record revenue achievements between Q1 2020 and Q4 2022?", "role": "Business Journalist", "type": "company_level_multi_time"}

{"question": "How did macroeconomic conditions impact operating margins and cash flow priorities  across the financials, energy, consumer discretionary, real estate, and information technology sectors in 2023 Q1?", "role": "Business Journalist", "type": "multi_sector_single_time"}

{"question": "How did Home Depot Inc.'s strategic investments and operational adjustments enable it to achieve record-breaking revenue growth and profitability despite external challenges over the period from 2020 Q1 to 2022 Q4?", "role": "Economic Forecaster", "type": "company_level_multi_time"}

{"question": "How did diversification strategies across business segments and geographic regions contribute to the varying resilience of major real estate companies during Q4 2022 amidst macroeconomic challenges like inflation and rising interest rates?", "role": "Risk Management Specialist", "type": "sector_level_single_time"}

{"question": "How did the cost optimization strategies employed by energy companies in Q2 2020 differ in mitigating the impacts of COVID-19 and volatile commodity prices?", "role": "Monetary Policy Strategist", "type": "sector_level_single_time"}

{"question": "How did inflationary pressures and rising interest rates in 2022 Q3 shape the differing approaches to cost management, capital allocation, and margin resilience across the energy, real estate, information technology, consumer discretionary, and financials sectors?", "role": "Equity Research Analyst", "type": "multi_sector_single_time"}

{"question": "How did Cincinnati Financial Corporation's resilience in underwriting and premium growth across commercial lines, personal lines, and reinsurance segments mitigate the financial impacts of external factors from 2020 Q1 to 2022 Q4?", "role": "Business Journalist", "type": "company_level_multi_time"}
```
