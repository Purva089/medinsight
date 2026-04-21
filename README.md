# MedInsight

> AI-powered medical lab report analysis platform with multi-agent architecture

MedInsight is a capstone Gen AI application that integrates **RAG**, **Text-to-SQL**, **multi-agent orchestration (LangGraph)**, **Agent-to-Agent (A2A) communication**, **MCP**, **function calling**, **PDF parsing**, **trend analysis**, and **cloud deployment** — helping patients understand their lab test results in plain language.

---

## 🎯 Features

| Feature | Description |
|---------|-------------|
| 📄 **PDF Extraction** | Upload lab report PDFs → automatic extraction of test names, values, units, status using Groq LLM + regex fallback |
| 🧠 **Medical RAG** | Vector search over MedlinePlus + WHO guidelines via pgvector; deterministic clinic context injection |
| 💬 **Text-to-SQL** | Natural language → SQL queries against patient's lab database; always uses latest report via deterministic subquery |
| 📊 **Trend Analysis** | Tracks how values change across multiple reports; detects threshold crossings and velocity concerns |
| 🤖 **Multi-Agent System** | LangGraph orchestrates RAG + SQL + Trend agents in parallel via `Send()` API |
| 🔗 **A2A Protocol** | Report generator explicitly requests data from other agents via typed A2A messages |
| 🔌 **MCP Server** | Exposes patient data as MCP-compatible tools callable by external AI systems |
| 📈 **PDF Health Reports** | ReportLab-generated PDFs with test tables, matplotlib trend charts, specialist referrals |
| 🔐 **Auth** | JWT-based authentication, bcrypt passwords, rate limiting (30 req/min) |
| ☁️ **Cloud Deployed** | Dockerized with nginx + supervisor, deployed on Azure App Service |

---

## 🏗️ Architecture

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | Groq — `llama-3.3-70b-versatile` (primary), `llama-3.1-8b-instant` (fallback) |
| **Agent Framework** | LangGraph 1.1.6 — native `Send()` parallel fan-out |
| **RAG / Vector DB** | pgvector on Neon PostgreSQL — `BAAI/bge-base-en-v1.5` embeddings (768-dim, local) |
| **Backend** | FastAPI 0.135.3 + asyncpg (full async) |
| **Frontend** | Streamlit 1.56.0 |
| **Database** | PostgreSQL 16 — Neon serverless |
| **ORM** | SQLAlchemy 2.0 async + Alembic migrations |
| **PDF** | ReportLab (generation) + PyMuPDF (parsing) |
| **Charts** | Matplotlib (embedded in PDF), Plotly (frontend trends page) |
| **Logging** | structlog (structured JSON logs) |
| **Container** | Docker |
| **Cloud** | Azure App Service + Azure Container Registry |

---

## 🤖 Multi-Agent Workflow

```
User Question
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│  orchestrator_node                                           │
│  • LLM classifies intent: rag / sql / trend / report        │
│  • Rule-based classifier categorises tests (no LLM needed)  │
│  • Sets flags: needs_rag, needs_sql, needs_trend            │
└─────────────────────────┬────────────────────────────────────┘
                          │
                          ▼
              route_to_agents()  ←  LangGraph Send()
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼         (run in parallel)
   ┌──────────┐    ┌───────────┐    ┌────────────┐
   │ rag_node │    │trend_node │    │ sql_node   │
   │          │    │           │    │            │
   │ pgvector │    │ historical│    │ generates  │
   │ search + │    │ values +  │    │ SQL for    │
   │ clinic   │    │ direction │    │ latest     │
   │ context  │    │ % change  │    │ report     │
   └────┬─────┘    └─────┬─────┘    └──────┬─────┘
        │                │                 │
        └────────────────┼─────────────────┘
                         │  (state reducers merge all outputs)
                         ▼
             ┌───────────────────────┐
             │   synthesis_node      │
             │  Merges all contexts  │
             │  Final LLM call       │
             │  Saves to DB          │
             └──────────┬────────────┘
                        │
                        ▼
                       END

─── Report Generation (separate path) ─────────────────────────

route_to_agents()
        │
        ▼
┌──────────────────────────────┐
│  report_generator_node       │
│  Uses A2A protocol to call:  │
│   → rag_agent (explanations) │
│   → sql_agent (test values)  │
│   → trend_agent (charts)     │
│  Builds PDF with ReportLab   │
└──────────────────────────────┘
```

### State Flow (Shared TypedDict)

All agents read and write a single `MedInsightState`. When agents run in parallel, LangGraph merges their writes using **reducer functions**:

| Field | Set by | Reducer |
|-------|--------|---------|
| `needs_rag/sql/trend` | Orchestrator | `keep_first` (immutable) |
| `rag_context` | RAG agent | `merge_str` (concatenate) |
| `sql_results` | SQL agent | `merge_lists` (append) |
| `trend_results` | Trend agent | `merge_lists` (append) |
| `errors` | Any agent | `merge_lists` (accumulate) |
| `disclaimer_required` | Any agent | `merge_bool_or` (True if any) |
| `final_response` | Synthesis | `keep_first` (written once) |

---

## 🔌 MCP & Function Calling

### MCP Server (`/api/v1/mcp/`)
Exposes patient data as MCP-compatible tools for external AI systems:
- `GET /mcp/info` — server capabilities
- `GET /mcp/tools` — list all available tools
- `POST /mcp/call` — invoke a tool (e.g., `query_patient_lab_results`)

### Function Calling (`/api/v1/tools/`)
OpenAI-compatible function/tool schema:
- `GET /tools/definitions` — all tool schemas
- `POST /tools/invoke` — call a tool with structured arguments

Both are demonstrable live via **Swagger UI** at `/docs`.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL with pgvector or [Neon](https://neon.tech) 
- [Groq API key](https://console.groq.com) 

### Local Setup

```bash
# 1. Clone and enter directory
git clone <your-repo-url>
cd medinsight

# 2. Create virtualenv
python -m venv .venv312
.venv312\Scripts\activate      # Windows
source .venv312/bin/activate   # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cp .env.example .env

# 5. Run DB migrations
alembic upgrade head

# 6. Ingest knowledge base (first time only)
python scripts/ingest_knowledge_base.py

# 7. Start backend (Terminal 1)
uvicorn app.api.main:app --host 0.0.0.0 --port 8000

# 8. Start frontend (Terminal 2)
streamlit run app/frontend/main.py
```

**Access:**
- Frontend: http://localhost:8501
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Demo Login
```
Email:    bhavya@gmail.com
Password: bhavya1122
```

## ☁️ Azure Deployment

Deployed on **Azure App Service** using **Azure Container Registry**.
Deployed link: https://medinsight-hyhhdvfkcpfqh3gb.centralindia-01.azurewebsites.net/

---

## 📊 Supported Lab Tests (4 Categories)

| Category | Tests |
|----------|-------|
| **Blood Count** | Hemoglobin, Hematocrit, RBC Count, WBC Count, Platelet Count, Neutrophils, Lymphocytes, Eosinophils |
| **Metabolic** | Fasting Blood Glucose, HbA1c, Random Blood Sugar, Insulin, Sodium, Potassium, Chloride |
| **Liver** | SGPT/ALT, SGOT/AST, Total Bilirubin, Direct Bilirubin, Alkaline Phosphatase, Albumin, Total Protein, GGT |
| **Thyroid** | TSH, Free T3, Free T4, T3, T4 |

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v



## 📁 Project Structure

```
medinsight/
├── app/
│   ├── agents/          # LangGraph agents (orchestrator, rag, sql, trend, synthesis, report)
│   ├── api/             # FastAPI routers (auth, chat, reports, patients, history, mcp, tools)
│   ├── core/            # Config, database, logging, prompts, categories
│   ├── frontend/        # Streamlit pages (dashboard, chat, trends, upload, history)
│   ├── mcp/             # MCP server implementation
│   ├── models/          # SQLAlchemy ORM models
│   ├── schemas/         # Pydantic schemas
│   └── services/        # PDF extractor, LLM service, RAG knowledge base, safeguards
├── alembic/             # Database migrations
├── data/
│   ├── knowledge_base/  # MedlinePlus, WHO, clinic files
│   └── synthetic_reports/
├── docs/                # Component documentation
│   ├── agents.md        # Agent system deep dive
│   ├── rag_pipeline.md  # RAG pipeline details
│   ├── api_reference.md # All API endpoints
│   └── deployment.md    # Deployment guide
├── evaluation/          # RAG, SQL, extraction quality metrics
├── scripts/             # Data generation and ingestion utilities
├── tests/               # Pytest test suite
├── Dockerfile           # Multi-service container (nginx + supervisord)
├── docker-compose.yml
└── requirements.txt
```

## 🔒 Security

- JWT authentication (bcrypt passwords, HS256 tokens)
- Pydantic input validation on all endpoints
- Parameterised SQL queries (no injection risk)
- CORS restricted to configured origins
- Rate limiting: 30 requests/minute per IP
- Docker non-root user (`medinsight`, UID 1000)
- Medical disclaimers injected on every health response
- Safeguards module: input sanitisation + output filtering

---

