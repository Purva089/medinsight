# Blood Count Report - Test Queries for Each Agent

## Patient: Ajay singh (Female, 28, O+)
## Report Type: Blood Count Panel (CBC - Complete Blood Count)

---

## 1. SQL AGENT TEST QUERIES (Text-to-SQL)

### Basic Value Retrieval
```
Q: "What is my hemoglobin?"
Expected: Returns current hemoglobin value with unit (e.g., "14.2 g/dL")
SQL: SELECT test_name, value, unit FROM lab_results WHERE patient_id='...' AND test_name='Hemoglobin'
```

```
Q: "Show my WBC count"
Expected: Returns WBC value (e.g., "7500 cells/µL")
```

```
Q: "List all my blood count results"
Expected: Shows Hemoglobin, RBC, WBC, Platelets, Hematocrit
```

### Filtering & Status Queries
```
Q: "Show tests with high values"
Expected: Lists only tests with status='high' (above reference range)
```

```
Q: "Which tests are abnormal?"
Expected: Lists tests where status != 'normal'
```

```
Q: "Show my normal test results"
Expected: Lists tests within reference range
```

### Summary Queries
```
Q: "Summarize my blood count report"
Expected: Brief overview - abnormal tests first, then normal
```

```
Q: "How many tests are abnormal?"
Expected: Count of high/low tests
```

---

## 2. RAG AGENT TEST QUERIES (Medical Knowledge)

### Test Explanation
```
Q: "What is hemoglobin?"
Expected: Concise medical definition (protein in RBCs that carries oxygen)
Agent: Should search knowledge base for hemoglobin info
```

```
Q: "What does high WBC count mean?"
Expected: Explains infection/inflammation/immune response
Should: Include causes (infection, stress, inflammation)
```

```
Q: "Why is platelet count important?"
Expected: Explains blood clotting function
Should: Mention bleeding/clotting risks when abnormal
```

### Interpretation Queries
```
Q: "What causes low hemoglobin?"
Expected: Lists common causes (anemia, blood loss, nutritional deficiency)
```

```
Q: "Is high hematocrit dangerous?"
Expected: Explains dehydration/polycythemia risks
Should: NOT diagnose, just explain possibilities
```

```
Q: "What does RBC count show?"
Expected: Explains red blood cell role in oxygen transport
```

### Symptoms & Clinical Context
```
Q: "What are symptoms of low hemoglobin?"
Expected: Fatigue, weakness, pale skin, shortness of breath
```

```
Q: "When should I worry about WBC count?"
Expected: Guidelines for critical values, when to see doctor
```

---

## 3. TREND AGENT TEST QUERIES (Temporal Analysis)

### Change Detection
```
Q: "How has my hemoglobin changed over time?"
Expected: Shows trend (rising/falling/stable), % change, chart
Should: Display line chart with dates and values
```

```
Q: "Is my WBC count improving?"
Expected: Compares first vs latest values, direction
Should: Show "improving" if moving toward normal range
```

```
Q: "Show platelet count trends"
Expected: Chart + summary (stable/rising/falling over X months)
```

### Comparative Queries
```
Q: "Compare my last 3 blood count reports"
Expected: Shows changes across all tests
Should: Highlight which tests changed significantly
```

```
Q: "Has my hemoglobin crossed normal range?"
Expected: Detects threshold_crossed=True
Should: Mention when it went from normal→abnormal
```

### Rate of Change
```
Q: "Is my RBC count dropping fast?"
Expected: Checks velocity_concern flag
Should: Calculate delta per month, compare to reference range width
```

---

## 4. REPORT GENERATOR AGENT TEST QUERIES (PDF Reports)

```
Q: "Generate a comprehensive report"
Expected: Creates downloadable PDF with all sections
Should include:
  - Patient demographics
  - All test results table (with status colors)
  - Trend charts for tests with history
  - Medical interpretations (from RAG)
  - Recommendations
```

```
Q: "Create a PDF of my blood count results"
Expected: Same as above, focused on blood count category
```

```
Q: "Download my full report with trends"
Expected: PDF with embedded matplotlib/plotly charts
```

---

## 5. MULTI-AGENT QUERIES (Orchestrator Routes to Multiple Agents)

### RAG + SQL Combination
```
Q: "What is hemoglobin and what's my value?"
Expected: 
  - RAG: Explains what hemoglobin is
  - SQL: Returns patient's value
  - Synthesis: Combines into "Hemoglobin is [definition]. Your value is X g/dL."
```

```
Q: "Explain my high WBC count"
Expected:
  - SQL: Fetches WBC value and status
  - RAG: Explains what high WBC means
  - Synthesis: "Your WBC is [value] (high). This may indicate..."
```

### SQL + Trend Combination
```
Q: "Show my hemoglobin history"
Expected:
  - SQL: Gets all hemoglobin values
  - Trend: Computes direction, % change
  - Chart: Displays line chart
  - Synthesis: "Your hemoglobin has [risen/fallen] by X% over Y months"
```

### RAG + Trend Combination
```
Q: "Why is my platelet count dropping?"
Expected:
  - Trend: Detects falling direction
  - RAG: Explains causes of low platelets
  - Synthesis: "Your platelets dropped from X→Y (Z%). Common causes include..."
```

### All 3 Agents (RAG + SQL + Trend)
```
Q: "Is my blood count getting better?"
Expected:
  - SQL: Lists all current values
  - Trend: Shows direction for each test
  - RAG: Provides context on improving vs worsening
  - Synthesis: Comprehensive answer with charts
```

---

## 6. EDGE CASES & ERROR HANDLING

### Missing Data
```
Q: "Show my eosinophil count"
Expected: "No data found for eosinophil count in your reports"
Should: Gracefully handle tests not in blood_count category
```

### Insufficient Trend Data
```
Q: "What's my hemoglobin trend?" (only 1 report uploaded)
Expected: "Need at least 2 reports to show trends"
Should: Still show current value
```

### Ambiguous Queries
```
Q: "Is my blood count good?"
Expected: 
  - Classifies as SQL (list values)
  - Returns summary of normal/abnormal
  - Does NOT make judgments ("good" vs "bad")
```

---

## 7. EXPECTED RAG IMPROVEMENTS

### Current Issues:
1. ❌ Responses too generic/not specific to patient data
2. ❌ Not using patient's actual test values in context
3. ❌ Missing actionable advice (when to see doctor)

### Improved RAG Responses Should:
1. ✅ Reference patient's actual values: "Your hemoglobin of 14.2 g/dL is..."
2. ✅ Be concise (30-50 words for definitions, 50-80 for interpretations)
3. ✅ Include practical advice: "Consult doctor if you experience..."
4. ✅ Use bullet points for readability
5. ✅ Avoid repeating test values already shown
6. ✅ Match the question scope (don't explain unrelated tests)

### Example of GOOD RAG Response:
**Q: "What does high WBC count mean?"**

**Current (BAD):**
"WBC count measures white blood cells in blood. Normal range is 4000-11000. High values may indicate infection or inflammation. See your doctor."

**Improved (GOOD):**
"High WBC (>11000) typically indicates:
• Active infection (bacterial/viral)
• Inflammation or tissue injury
• Immune response to stress

⚠️ Consult your doctor if you have fever, fatigue, or unexplained symptoms."

---

## 8. TESTING CHECKLIST

**Setup:**
- [ ] Patient logged in: ajay.singh@example.com (or create if not exists)
- [ ] Blood count report uploaded (Ajay_singh_bloodcount_2026.pdf)
- [ ] Backend running without --reload flag
- [ ] Frontend (Streamlit) running

**Test Each Agent:**
- [ ] SQL: Test 3 queries from section 1
- [ ] RAG: Test 3 queries from section 2
- [ ] Trend: Test 2 queries from section 3 (need 2+ reports)
- [ ] Multi-agent: Test 2 queries from section 5

**Verify:**
- [ ] Charts display automatically when trend data exists
- [ ] RAG answers are concise and relevant
- [ ] No HTML tags in responses
- [ ] Confidence badges correct (high/medium/low)
- [ ] No duplicate information in answer

**Performance:**
- [ ] Queries complete in <10s (after first load)
- [ ] Charts render correctly (Plotly interactive)
- [ ] No errors in backend logs
- [ ] Frontend doesn't timeout

---

## 9. BLOOD COUNT NORMAL RANGES (Reference)

| Test | Unit | Normal Range (Female) | Clinical Significance |
|------|------|----------------------|----------------------|
| Hemoglobin | g/dL | 12.0 - 16.0 | Low: Anemia; High: Dehydration/Polycythemia |
| RBC Count | million/µL | 4.0 - 5.5 | Low: Anemia; High: Polycythemia |
| WBC Count | cells/µL | 4000 - 11000 | Low: Immune suppression; High: Infection |
| Platelet Count | lakh/µL | 1.5 - 4.0 | Low: Bleeding risk; High: Clotting risk |
| Hematocrit | % | 36.0 - 46.0 | % of blood volume that's RBCs |

---

## Quick Test Command (Copy-Paste):

```bash
# 1. Start backend (uvicorn terminal)
uvicorn app.api.main:app --host 0.0.0.0 --port 8000

# 2. Start frontend (streamlit terminal)
streamlit run app/frontend/main.py

# 3. Login as Ajay singh and test these queries in sequence:
# - "What is my hemoglobin?"
# - "Show tests with high values"  
# - "What does high WBC count mean?"
# - "How has my hemoglobin changed over time?"
# - "Explain my blood count results"
```
