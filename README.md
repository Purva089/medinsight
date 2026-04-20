# MedInsight

> AI-powered medical lab report analysis platform with multi-agent architecture

MedInsight is a comprehensive Gen AI application that combines RAG (Retrieval-Augmented Generation), Text-to-SQL, trend analysis, and multi-agent orchestration to help patients understand their lab test results and health trends.

---

## 🎯 Features

### Core Capabilities
- **📄 PDF Extraction**: Automatic extraction of lab test results from PDF reports using Groq LLM + regex fallback
- **🧠 Medical Knowledge RAG**: Retrieve relevant medical guidelines from MedlinePlus & clinic data using pgvector
- **📊 Trend Analysis**: Track how lab values change over time with improving/worsening/stable detection
- **💬 Natural Language Queries**: Ask questions in plain English, get structured SQL results
- **🤖 Multi-Agent System**: LangGraph-orchestrated agents for parallel execution (RAG, SQL, Trend)
- **📈 Health Reports**: AI-generated personalized health summaries with recommendations
- **🔐 Secure Authentication**: JWT-based auth with role-based access control (RBAC)

### Advanced Features
- Category-based test classification (blood count, metabolic, liver, thyroid)
- Long-term memory (LTM) for patient history tracking
- Agent-to-Agent (A2A) communication logging
- Automatic clinic referral suggestions
- Confidence scoring for extracted data
- Safeguards: input validation, output filtering, disclaimer injection

---

## 🏗️ Architecture

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | Groq (llama-3.3-70b-versatile, llama-3.1-8b-instant) |
| **Agents** | LangGraph 1.1.6 with native Send() parallelism |
| **RAG** | LlamaIndex + pgvector (Neon PostgreSQL) |
| **Embeddings** | BAAI/bge-base-en-v1.5 (local, 768-dim) |
| **Backend** | FastAPI 0.135.3 + asyncpg |
| **Frontend** | Streamlit 1.42.0 |
| **Database** | PostgreSQL 16 (Neon serverless) |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Migrations** | Alembic |
| **Logging** | structlog |
| **PDF** | PyMuPDF |

### Multi-Agent Workflow

```
User Question
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  orchestrator_node                                          │
│  • Classifies intent (rag/sql/trend/general)                │
│  • Sets execution flags (needs_rag, needs_sql, needs_trend) │
│  • Tags tests with categories                               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
              route_to_agents() → Send()
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌──────────────┐
   │   RAG   │ │  Trend  │ │  Text2SQL    │  (parallel execution)
   └────┬────┘ └────┬────┘ └──────┬───────┘
        └─────┬─────┴─────────────┘
              ▼  (state merge via reducers)
      ┌───────────────┐
      │ report_agent  │  → Final response + DB save
      └───────┬───────┘
              ▼
             END
```

---

## 🚀 Setup

### Prerequisites
- Python 3.12+
- PostgreSQL with pgvector extension (or Neon account)
- Groq API key

### Installation

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd medinsight
```

2. **Create virtual environment**
```bash
python -m venv .venv312
.venv312\Scripts\activate  # Windows
source .venv312/bin/activate  # Linux/Mac
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Environment setup**
Create `.env` file in the root:
```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host/db

# Groq API
GROQ_API_KEY=gsk_...

# Auth
SECRET_KEY=your-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# API Config
API_HOST=127.0.0.1
API_PORT=8000
FRONTEND_PORT=8501
APP_DEBUG=True
```

5. **Run migrations**
```bash
alembic upgrade head
```

6. **Ingest knowledge base**
```bash
# Download embeddings (first time only)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"

# Ingest documents
python scripts/ingest_knowledge_base.py --source all
```

7. **Seed demo data** (optional)
```bash
python scripts/seed_db.py
```

---

## 📦 Usage

### Start Backend (FastAPI)
```bash
.\start_api.ps1
# or manually:
uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
```

API Docs: http://localhost:8000/docs

### Start Frontend (Streamlit)
```bash
.\start_frontend.ps1
# or manually:
streamlit run app/frontend/main.py --server.port 8501
```

App: http://localhost:8501

### Demo Credentials
```
Email: patient1@medinsight.demo
Password: demo1234
```

---

---

## 🔧 Key Components

### Agents
| Agent | Purpose | Input | Output |
|-------|---------|-------|--------|
| **Orchestrator** | Intent classification + test categorization | User question | `intent`, `needs_*` flags |
| **RAG Agent** | Retrieve medical knowledge from pgvector | Test names | `rag_context`, `rag_chunks` |
| **Trend Agent** | Compute trends from historical lab data | Test names + patient_id | `trend_results` |
| **Text2SQL Agent** | Convert natural language → SQL query | Question + schema | `sql_results` |
| **Report Agent** | Synthesize final response + save to DB | All above contexts | `final_response` |

### API Endpoints

#### Authentication
- `POST /auth/register` - Register new patient
- `POST /auth/token` - Login (get JWT)
- `GET /auth/me` - Get current user

#### Chat
- `POST /chat` - Ask a question (invokes agent graph)

#### Reports
- `POST /reports/upload` - Upload lab report PDF
- `GET /reports` - List patient's reports
- `GET /reports/{id}` - Get report details
- `DELETE /reports/{id}` - Delete report

#### Patients
- `GET /patients/profile` - Get patient demographics
- `PUT /patients/profile` - Update profile

---

## 🧪 Testing

Run the test suite:
```bash
pytest tests/ -v
```

Individual test modules:
```bash
pytest tests/test_extraction_agent.py
pytest tests/test_rag_agent.py
pytest tests/test_trend_agent.py
```

---

## 🛠️ Development

### Code Quality Tools
```bash
# Type checking
pyright

# Linting
ruff check .

# Formatting
ruff format .
```

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## 📊 Supported Lab Tests (4 Categories)

### Blood Count (8 tests)
Hemoglobin, Hematocrit, RBC Count, WBC Count, Platelet Count, Neutrophils, Lymphocytes, Eosinophils

### Metabolic (4 tests)
Fasting Blood Glucose, HbA1c, Random Blood Sugar, Insulin

### Liver (9 tests)
SGPT, ALT, SGOT, AST, Total Bilirubin, Direct Bilirubin, Alkaline Phosphatase, Albumin, Total Protein

### Thyroid (3 tests)
TSH, Free T3, Free T4


---

## � Deployment

### Docker (Local Development)

```bash
# Quick start
docker-compose up --build

# Access
# - Frontend: http://localhost:8501
# - Backend: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

### Azure Container Apps (Production)

```bash
# 1. Install Azure CLI
winget install Microsoft.AzureCLI  # Windows
brew install azure-cli             # Mac

# 2. Login and run setup
az login
.\azure-setup.ps1  # Windows
./azure-setup.sh   # Linux/Mac

# 3. Configure GitHub Secrets and push
git push origin main
```

**📚 Full Documentation:**
- **Quick Start**: [QUICKSTART.md](QUICKSTART.md) - 3-minute Docker setup
- **Comprehensive Guide**: [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) - Complete deployment instructions
- **Summary**: [DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md) - Architecture & cost breakdown

---

## 🔒 Security

- JWT-based authentication with secure token generation
- Password hashing with bcrypt
- Input validation via Pydantic models
- SQL injection protection (parameterized queries)
- CORS middleware configured for trusted origins
- Rate limiting (TODO: add Redis-based limiter)
- Docker non-root user containers
- Azure managed HTTPS certificates

---

## 📈 Performance

- Async I/O throughout (FastAPI + asyncpg + async LLM calls)
- Connection pooling for database
- Parallel agent execution via LangGraph Send()
- Vector search with pgvector HNSW indexing
- Chunked document processing (1000 token chunks, 200 overlap)

---

**Data Sources:**
- MedlinePlus (U.S. National Library of Medicine)
- Synthetic demo data generated for testing

---
