# Agent System — MedInsight

## Overview

MedInsight uses a **LangGraph multi-agent system** where specialized agents run in parallel, coordinated by an orchestrator. Each agent has one job, runs independently, and writes its result back to a shared state. A synthesis agent merges everything into a final answer.

---

## Full Agent Flow

```
User sends question
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  orchestrator_node                                      │
│  • Classifies intent via LLM (rag/sql/trend/report)    │
│  • Categorises extracted tests (blood_count/liver/...)  │
│  • Sets flags: needs_rag, needs_sql, needs_trend        │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
               route_to_agents()  ← LangGraph Send()
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
  ┌──────────┐      ┌───────────┐      ┌────────────┐
  │ rag_node │      │ trend_node│      │ sql_node   │   ← parallel
  └────┬─────┘      └─────┬─────┘      └──────┬─────┘
       │                  │                   │
       └──────────────────┼───────────────────┘
                          │ (state reducers merge outputs)
                          ▼
              ┌───────────────────────┐
              │   synthesis_node      │
              │ • Merges all results  │
              │ • Final LLM call      │
              │ • Saves to DB         │
              └──────────┬────────────┘
                         │
                         ▼
                        END
```

For **PDF report generation**, a separate path is used:
```
route_to_agents()
        │
        ▼
┌─────────────────────┐
│ report_generator    │ ← Uses A2A protocol to call other agents
│  • A2A → rag_agent  │
│  • A2A → sql_agent  │
│  • Builds PDF       │
└─────────────────────┘
```

---

## Agents

### 1. Orchestrator (`app/agents/orchestrator.py`)

**Job:** Decide which agents to run.

- Calls Groq LLM with the user's question
- Classifies intent into: `rag`, `sql`, `trend`, `report`, `general`
- Sets boolean flags on shared state: `needs_rag`, `needs_sql`, `needs_trend`, `needs_report_generation`
- Also categorises each extracted test (e.g., Hemoglobin → `blood_count`) using a deterministic rule-based classifier — no LLM needed

**Intent → Agent mapping:**

| Intent classified | Flags set | Agents triggered |
|------------------|-----------|-----------------|
| `rag` | `needs_rag=True` | RAG agent |
| `sql` | `needs_sql=True` | SQL agent |
| `trend` | `needs_trend=True` | Trend agent |
| `report` | `needs_report_generation=True` | Report generator |
| `general` | `needs_rag=True` | RAG agent (default fallback) |
| Multi-intent question | Multiple flags | Multiple agents in parallel |

---

### 2. RAG Agent (`app/agents/rag_agent.py`)

**Job:** Answer medical knowledge questions using the vector knowledge base.

Steps:
1. Extract relevant test names from the question
2. Run vector similarity search on pgvector (top-3 chunks)
3. Load deterministic clinic context based on test category
4. Build a prompt: question + patient test values + retrieved chunks + clinic info
5. Call Groq LLM → structured JSON response
6. Write `rag_context` and `rag_chunks` to shared state

**Outputs written to state:**
- `rag_context` — formatted text with retrieved knowledge
- `rag_chunks` — raw chunk metadata for source attribution

---

### 3. Text-to-SQL Agent (`app/agents/text_to_sql_agent.py`)

**Job:** Answer questions about the patient's actual lab values from the database.

Steps:
1. Call Groq LLM with the question → generates a SQL query
2. SQL always uses a deterministic subquery to get the **latest report only**:
   ```sql
   WHERE report_id = (
     SELECT report_id FROM lab_results
     WHERE patient_id = '{patient_id}'
     GROUP BY report_id
     ORDER BY MAX(report_date) DESC
     LIMIT 1
   )
   ```
3. Execute generated SQL against PostgreSQL
4. Format results as a structured list
5. Write `sql_results` and `sql_query_generated` to shared state

**Outputs written to state:**
- `sql_results` — list of `{test_name, value, unit, status}` dicts
- `sql_query_generated` — the actual SQL for transparency/debugging

---

### 4. Trend Agent (`app/agents/trend_agent.py`)

**Job:** Analyse how a patient's lab values have changed across multiple reports over time.

Steps:
1. Query all historical values for each mentioned test across all reports
2. Calculate: direction (rising/falling/stable), % change, velocity (change/month)
3. Compare latest value against reference range
4. Detect: threshold crossing (normal→abnormal), velocity concern
5. Write `trend_results` to shared state

**Each trend result contains:**
```json
{
  "test_name": "Hemoglobin",
  "direction": "falling",
  "percent_change": -8.5,
  "threshold_crossed": true,
  "velocity_concern": false,
  "data_points": [{"date": "2026-02-01", "value": 12.2}, ...],
  "reference_low": 12.0,
  "reference_high": 16.0,
  "trend_description": "⚠️ Currently LOW (your value: 11.2, normal: 12.0–16.0)"
}
```

**Requires at least 2 reports** to compute a trend.

---

### 5. Synthesis Agent (`app/agents/synthesis_agent.py`)

**Job:** Merge outputs from all parallel agents into one coherent final response.

Steps:
1. Receive merged state (RAG context + SQL results + trend results all combined)
2. Build a final prompt with all available data
3. Call Groq LLM → final structured JSON response
4. Save the conversation to the database
5. Write `final_response` to state

**Always runs last** — every query path ends here (except report generation which has its own ending).

---

### 6. Report Generator (`app/agents/report_generator_agent.py`)

**Job:** Build a comprehensive downloadable PDF report using A2A protocol.

Uses **Agent-to-Agent (A2A) communication** to request data from other agents:
```
report_generator → A2ARequest → rag_agent    (gets medical explanations)
report_generator → A2ARequest → sql_agent    (gets current test values)
report_generator → A2ARequest → trend_agent  (gets trend charts)
```

PDF sections generated:
1. Patient demographics header
2. All test results table (colour-coded: red=high, blue=low, green=normal)
3. Trend charts (matplotlib, embedded as images)
4. Abnormal tests summary with explanations
5. Recommended specialist referrals (by test category)
6. Disclaimer

---

## Shared State (`app/agents/state.py`)

All agents read from and write to a single `MedInsightState` TypedDict. LangGraph handles merging when multiple agents write in parallel using **reducer functions**:

| State field | Set by | Reducer |
|-------------|--------|---------|
| `needs_rag`, `needs_sql`, `needs_trend` | Orchestrator | `keep_first` (immutable) |
| `rag_context` | RAG agent | `merge_str` (concatenate) |
| `rag_chunks` | RAG agent | `merge_lists` (append) |
| `sql_results` | SQL agent | `merge_lists` (append) |
| `trend_results` | Trend agent | `merge_lists` (append) |
| `errors` | Any agent | `merge_lists` (accumulate) |
| `final_response` | Synthesis agent | `keep_first` (written once) |
| `disclaimer_required` | Any agent | `merge_bool_or` (True if any agent sets it) |

---

## Agent-to-Agent (A2A) Protocol (`app/agents/a2a_protocol.py`)

The A2A protocol allows one agent to explicitly request work from another agent. Used primarily by the report generator.

```python
# Report generator sends an A2A request to the RAG agent
request = A2ARequest(
    source_agent="report_generator",
    target_agent="rag_agent",
    action="get_medical_context",
    payload={"tests": ["Hemoglobin", "WBC Count"]}
)
response = await a2a_hub.send(request)
```

All A2A messages are logged to `state["a2a_messages"]` for traceability and audit.

---

## LangGraph Parallelism — How It Works

MedInsight uses LangGraph's **`Send()` API** for native parallel execution — not threads, not asyncio.gather.

```python
def route_to_agents(state) -> list[Send]:
    sends = []
    if state["needs_rag"]:
        sends.append(Send("rag_agent", state))
    if state["needs_sql"]:
        sends.append(Send("text_to_sql_agent", state))
    if state["needs_trend"]:
        sends.append(Send("trend_agent", state))
    return sends   # LangGraph runs all of these in parallel
```

LangGraph then waits for all parallel branches to complete and merges their state updates using the reducer functions before passing to the synthesis agent.

---

## Example: "Explain my high WBC count"

```
Question: "Explain my high WBC count"
         │
         ▼
Orchestrator: intent=rag+sql, needs_rag=True, needs_sql=True
         │
         ├─── RAG agent (parallel) ─────────────────────────────────────►
         │      retrieves: "High WBC indicates infection/inflammation..."
         │      writes: rag_context = "High WBC (>11000) typically means..."
         │
         └─── SQL agent (parallel) ─────────────────────────────────────►
                queries DB: SELECT ... WHERE test_name='WBC Count'...
                finds: WBC = 13,500 cells/µL (HIGH)
                writes: sql_results = [{test_name: WBC Count, value: 13500, status: high}]
         │
         ▼ (both complete, state merged)
Synthesis agent:
  - Has both rag_context and sql_results
  - Calls LLM: "Your WBC count is 13,500 cells/µL (high).
                This typically indicates active infection or inflammation..."
         │
         ▼
Response saved to DB, returned to user
```
