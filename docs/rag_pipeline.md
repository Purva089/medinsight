# RAG Pipeline — MedInsight

## Overview

MedInsight uses **Retrieval-Augmented Generation (RAG)** to answer medical questions grounded in real clinical knowledge rather than relying solely on LLM training data.

---

## Pipeline Flow

```
User Question
     │
     ▼
[Orchestrator] — classifies intent as needs_rag=True
     │
     ▼
[RAG Agent]
  ├─ 1. Extract lab test context from patient state
  ├─ 2. Vector search: query pgvector for relevant chunks
  ├─ 3. Load deterministic clinic context (by test category)
  ├─ 4. Build prompt with: question + patient data + retrieved chunks
  └─ 5. Call Groq LLM → structured JSON response
     │
     ▼
[Synthesis Agent] — merges RAG result with SQL/Trend if multi-agent
     │
     ▼
Final Answer
```

---

## Components

### 1. Knowledge Base (Vector Store)

| Source | Content | Location |
|--------|---------|----------|
| MedlinePlus | Disease explanations, normal ranges, symptoms | `data/knowledge_base/medlineplus/` |
| WHO Guidelines | Clinical thresholds, recommendations | `data/knowledge_base/who/` |
| Clinic Data | Local doctor info by specialty | `data/knowledge_base/clinics/` |

- **Embedding model**: `BAAI/bge-base-en-v1.5` (local, 768-dim, no API cost)
- **Vector DB**: pgvector on Neon PostgreSQL
- **Chunk size**: 512 tokens, 50 token overlap
- **Similarity metric**: Cosine distance
- **Top-K retrieved**: 3 chunks per query

### 2. Deterministic Clinic Context Injection

Problem: Vector search sometimes ranks clinic info low even when a test is abnormal.

Solution: `_load_clinic_context()` in `app/agents/rag_agent.py` deterministically reads the relevant clinic file based on the test's category (e.g., `clinics_blood_count.txt` for hemoglobin tests) and appends the first doctor entry to the retrieved context.

```python
# Category → clinic file mapping
"blood_count" → data/knowledge_base/clinics/clinics_blood_count.txt
"liver"       → data/knowledge_base/clinics/clinics_liver.txt
"metabolic"   → data/knowledge_base/clinics/clinics_metabolic.txt
"thyroid"     → data/knowledge_base/clinics/clinics_thyroid.txt
```

### 3. Prompt Construction

The RAG prompt includes:
- **System role**: Medical AI assistant with formatting rules
- **Patient context**: Age, gender, current test values with status
- **Retrieved chunks**: Top-3 vector search results + clinic info
- **Question**: User's original query
- **Output format**: Structured JSON with fields: `direct_answer`, `guideline_context`, `watch_for`, `sources`, `disclaimer`, `confidence`

### 4. LLM Call

- **Primary model**: `llama-3.3-70b-versatile` (Groq)
- **Fallback model**: `llama-3.1-8b-instant` (on rate limit)
- **Temperature**: 0.1 (deterministic, factual)
- **Max tokens**: 500 (enforces concise responses)

---

## Hallucination Prevention

| Rule | Implementation |
|------|---------------|
| No fake doctor names | Explicit prompt rule: "NEVER invent doctor names" |
| No diagnosis | Prompt rule: explain possibilities, never diagnose |
| Grounded answers | Retrieved chunks included in every prompt |
| Disclaimer always | `disclaimer` field forced in JSON output schema |
| Confidence scoring | `high/medium/low` based on source quality |

---

## Knowledge Base Ingestion

```bash
# Ingest all knowledge base files into pgvector
python scripts/ingest_knowledge_base.py

# Scrape fresh MedlinePlus data (optional)
python scripts/scrape_medlineplus.py
```

---

## Example: RAG Response for "What does high WBC mean?"

**Retrieved chunks**: MedlinePlus CBC article, WHO infection guidelines  
**Clinic context**: Dr. Neha Kapoor, General Medicine (from clinics_blood_count.txt)

**LLM Output**:
```json
{
  "direct_answer": "High WBC (>11,000) typically indicates:\n• Active bacterial or viral infection\n• Inflammation or tissue injury\n• Immune system response to stress",
  "guideline_context": "Normal WBC range: 4,000–11,000 cells/µL (WHO guidelines)",
  "watch_for": "Fever, chills, fatigue, or unexplained weight loss",
  "sources": ["MedlinePlus CBC Reference", "WHO Clinical Guidelines"],
  "disclaimer": "This is educational information. Consult your doctor for diagnosis.",
  "confidence": "high"
}
```
