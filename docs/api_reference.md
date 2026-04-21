# API Reference — MedInsight

Base URL (local): `http://localhost:8000/api/v1`  
Base URL (Azure): `https://<app-name>.azurewebsites.net/api/v1`  
Interactive docs: `/docs` (Swagger UI)

All protected endpoints require: `Authorization: Bearer <token>`

---

## Authentication

### POST `/api/v1/auth/register`
Register a new patient account.

**Body:**
```json
{
  "email": "patient@example.com",
  "password": "securepassword",
  "full_name": "Ajay Singh"
}
```
**Response:** `201` — `{ "id": "uuid", "email": "...", "full_name": "..." }`

---

### POST `/api/v1/auth/login`
Login and receive JWT token.

**Body (form-data):**
```
username=patient@example.com
password=securepassword
```
**Response:** `200` — `{ "access_token": "eyJ...", "token_type": "bearer" }`

---

## Chat (Multi-Agent)

### POST `/api/v1/chat/query`
Send a natural language question. Routes to RAG / SQL / Trend agents automatically.

**Body:**
```json
{
  "message": "What does my high WBC count mean?",
  "session_id": "optional-uuid"
}
```
**Response:**
```json
{
  "answer": "High WBC typically indicates...",
  "confidence": "high",
  "agents_used": ["rag", "sql"],
  "trend_data": null,
  "session_id": "uuid"
}
```

---

## Reports (PDF Upload & Generation)

### POST `/api/v1/reports/upload`
Upload a lab report PDF. Triggers extraction and DB storage.

**Body:** `multipart/form-data` — `file: <pdf>`

**Response:**
```json
{
  "report_id": "uuid",
  "extracted_tests": 12,
  "patient_demographics": { "age": 28, "gender": "Female" },
  "status": "processed"
}
```

---

### POST `/api/v1/reports/generate-pdf`
Generate a comprehensive PDF report with trends and recommendations.

**Body:**
```json
{ "report_type": "comprehensive" }
```
**Response:** `200` — `{ "pdf_base64": "JVBERi0...", "filename": "report.pdf" }`

---

## Patients

### GET `/api/v1/patients/me`
Get current patient's profile.

**Response:** `{ "id": "uuid", "full_name": "...", "age": 28, "gender": "Female", "blood_group": "O+" }`

---

### GET `/api/v1/patients/me/lab-results/latest`
Get all test results from the latest uploaded report.

**Response:**
```json
{
  "report_id": "uuid",
  "report_date": "2026-04-01",
  "tests": [
    { "test_name": "Hemoglobin", "value": 11.2, "unit": "g/dL", "status": "low", "reference_range": "12.0-16.0" }
  ]
}
```

---

### GET `/api/v1/patients/me/lab-results/trends/{test_name}`
Get historical trend data for a specific test.

**Response:**
```json
{
  "test_name": "Hemoglobin",
  "direction": "falling",
  "percent_change": -8.5,
  "data_points": [
    { "date": "2026-02-01", "value": 12.2 },
    { "date": "2026-03-01", "value": 11.6 },
    { "date": "2026-04-01", "value": 11.2 }
  ],
  "reference_low": 12.0,
  "reference_high": 16.0
}
```

---

## Chat History

### GET `/api/v1/history/`
Get all past conversations for the current patient.

**Response:** `[ { "id": "uuid", "question": "...", "answer": "...", "created_at": "..." } ]`

---

## MCP (Model Context Protocol)

### GET `/api/v1/mcp/info`
Get MCP server capabilities.

### GET `/api/v1/mcp/tools`
List all available MCP tools.

### POST `/api/v1/mcp/call`
Call an MCP tool directly.

**Body:**
```json
{
  "tool_name": "query_patient_lab_results",
  "arguments": { "patient_id": "uuid", "test_name": "Hemoglobin" }
}
```

---

## Function Calling (Tools)

### GET `/api/v1/tools/definitions`
List all available function-calling tool definitions (OpenAI-compatible schema).

### POST `/api/v1/tools/invoke`
Invoke a tool with structured parameters.

**Body:**
```json
{
  "tool_name": "analyze_lab_report",
  "arguments": { "focus": "overall", "detail_level": "comprehensive" }
}
```

---

## System

### GET `/health`
Health check (no auth required).

**Response:** `{ "status": "ok", "version": "1.0.0" }`

---

## Error Codes

| Code | Meaning |
|------|---------|
| `401` | Missing or invalid JWT token |
| `403` | Access denied (wrong patient) |
| `404` | Resource not found |
| `422` | Validation error in request body |
| `429` | Rate limit exceeded (30 req/min) |
| `500` | Internal server error |
