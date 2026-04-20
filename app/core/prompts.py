"""
LLM prompt templates for MedInsight.

All prompts are Python string constants.
Use .format(**kwargs) to fill placeholders before sending to the LLM.

"""
from __future__ import annotations

# ── Intent Classification ─────────────────────────────────────────────────────

PROMPT_CLASSIFICATION = """\
Classify the question into ONE category. Every question MUST map to sql, rag, or trend.

Categories:
- sql: asking for VALUES, results, lists, summaries ("what is my X?", "show Y", "list Z")
- rag: asking WHAT/WHY about medical concepts, meanings, causes ("what does X mean?", "why is Y important?", "explain Z")
- trend: asking about CHANGES, history, comparisons over time ("how has X changed?", "is Y improving?", "compare")

Key distinction:
"What is my hemoglobin?" = sql (wants the VALUE)
"What is hemoglobin?" = rag (wants EXPLANATION)

Examples:
"What is my hemoglobin?" → sql
"Show my WBC count" → sql
"List high values" → sql
"Summarize results" → sql
"What is hemoglobin?" → rag
"What does high WBC mean?" → rag
"Why is platelet count important?" → rag
"What causes low hemoglobin?" → rag
"How has my glucose changed?" → trend
"Is my cholesterol improving?" → trend
"Show hemoglobin trend" → trend

Question: {question}

Output ONLY one word (sql/rag/trend):"""


# ── Text-to-SQL ───────────────────────────────────────────────────────────────

PROMPT_TEXT_TO_SQL = """\
Generate a PostgreSQL SELECT query.
Patient ID: {patient_id} — use directly, never ask for it.
Schema: {schema_description}
Rules: SELECT only, no INSERT/UPDATE/DELETE/DROP.

ALWAYS query ONLY the latest report using this exact subquery pattern:
WHERE patient_id='{patient_id}'
  AND report_id = (
    SELECT report_id FROM lab_results
    WHERE patient_id='{patient_id}'
    GROUP BY report_id
    ORDER BY MAX(report_date) DESC
    LIMIT 1
  )

Never query historical or multiple reports. Trend/history is handled by a separate agent.

Question: {question}
Return only SQL, nothing else."""


# ── Report Synthesis ──────────────────────────────────────────────────────────

PROMPT_REPORT = """\
You are MedInsight, a medical AI assistant. Provide clear, accurate, patient-specific answers.

=== FEW-SHOT EXAMPLES ===

EXAMPLE 1 (SQL - List specific values):
Question: "What is my hemoglobin?"
SQL RESULTS: Hemoglobin: 13.8 g/dL (normal, ref: 12.0-16.0)
CORRECT:
{{"direct_answer":"Your Hemoglobin is 13.8 g/dL (normal range: 12.0-16.0).","guideline_context":"","trend_summary":"","watch_for":"","sources":[],"intent_handled":"sql"}}

EXAMPLE 2 (SQL - List abnormal):
Question: "Show high values"
SQL RESULTS: 
  - WBC Count: 12500 cells/µL (high, ref: 4000-11000)
  - Alkaline Phosphatase: 174 U/L (high, ref: 40-150)
CORRECT:
{{"direct_answer":"2 tests with high values:\\n\\n• WBC Count: 12,500 cells/µL (ref: 4,000-11,000)\\n• Alkaline Phosphatase: 174 U/L (ref: 40-150)","guideline_context":"","trend_summary":"","watch_for":"Consult your doctor about these elevated values.","sources":[],"intent_handled":"sql"}}

EXAMPLE 3 (RAG - Explain medical concept):
Question: "Why is platelet count important?"
CORRECT:
{{"direct_answer":"Platelet Count measures tiny blood cells that stop bleeding by forming clots.\n\nWhy it matters:\n\n• Too Low (<1.5 lakh/µL): Risk of bleeding, bruising easily\n• Too High (>4.0 lakh/µL): Risk of blood clots, stroke\n• Normal Range: Healthy clotting and healing\n\nYour current level (3.0 lakh/µL) is normal.","guideline_context":"","trend_summary":"","watch_for":"","sources":["Medical Guidelines"],"intent_handled":"rag"}}

EXAMPLE 4 (RAG - Interpret abnormal result with clinic info available):
Question: "What does high WBC mean?"
SQL RESULTS: WBC Count: 12500 cells/µL (high)
GUIDELINES: High WBC indicates infection or inflammation.
[clinics_blood_count.txt | blood_count | clinic_info]
doctor_name: Dr. Neha Kapoor
specialization: Hematologist
clinic_name: Delhi Blood & Bone Marrow Centre
contact: +91-98112-34567
address: B-14, Lajpat Nagar Phase II, New Delhi - 110024
CORRECT:
{{"direct_answer":"Your WBC count of 12,500 cells/µL is elevated (ref: 4,000-11,000).\n\nHigh WBC typically indicates:\n\n• Bacterial or viral infection\n• Inflammation or tissue injury\n• Immune system response to stress\n\nCommon causes include colds, urinary tract infections, or recent surgery.\n\n📋 Recommended Specialist:\n\nDr. Neha Kapoor (Hematologist)\nDelhi Blood & Bone Marrow Centre\n📞 +91-98112-34567\nB-14, Lajpat Nagar Phase II, New Delhi","guideline_context":"","trend_summary":"","watch_for":"Contact your doctor if you have fever, unexplained fatigue, or symptoms worsen.","sources":["Medical Guidelines"],"intent_handled":"rag"}}

EXAMPLE 5 (RAG - Abnormal liver result with clinic info available):
Question: "What does low Total Protein mean?"
SQL RESULTS: Total Protein: 5.68 g/dL (low, ref: 6.0-8.3)
GUIDELINES: Low total protein may indicate liver disease, kidney disease, or malnutrition.
[clinics_liver.txt | liver | clinic_info]
doctor_name: Dr. Priya Sharma
specialization: Hepatologist
clinic_name: City Liver & Gastro Centre
contact: +91-98765-43210
address: SCO 45, Model Town, Gurugram - 122001
CORRECT:
{{"direct_answer":"Your Total Protein is 5.68 g/dL, which is below the normal range (6.0-8.3 g/dL).\n\nLow total protein may indicate:\n\n• Liver disease — reduced protein synthesis\n• Kidney disease — protein loss in urine\n• Malnutrition — inadequate dietary protein\n• Malabsorption disorders\n\n📋 Recommended Specialist:\n\nDr. Priya Sharma (Hepatologist)\nCity Liver & Gastro Centre\n📞 +91-98765-43210\nSCO 45, Model Town, Gurugram","guideline_context":"","trend_summary":"","watch_for":"Consult your doctor about your low Total Protein. Watch for fatigue, swelling, or poor wound healing.","sources":["Medical Guidelines"],"intent_handled":"rag"}}

EXAMPLE 6 (SQL - Summary with no clinic info in guidelines):
Question: "Summarize my blood count"
SQL RESULTS:
  - Hemoglobin: 13.8 g/dL (normal)
  - WBC: 12500 (high)
  - Platelets: 2.8 lakh/µL (normal)
GUIDELINES: No guidelines available.
CORRECT:
{{"direct_answer":"ABNORMAL:\n\n• WBC Count: 12,500 cells/µL (ref: 4,000-11,000) — HIGH\n\nNORMAL:\n\n• Hemoglobin: 13.8 g/dL\n• Platelets: 2.8 lakh/µL","guideline_context":"","trend_summary":"","watch_for":"Consult your doctor about the elevated WBC. Monitor for fever, fatigue, or worsening symptoms.","sources":[],"intent_handled":"sql"}}

=== YOUR TASK ===

Question: "{question}"
Intent: {intent}
Patient: {patient_name}

TEST RESULTS FROM REPORT:
{extracted_tests}

SQL QUERY RESULTS:
{sql_results}

MEDICAL GUIDELINES:
{rag_context}

TRENDS:
{trend_summary}

=== RULES ===

**For SQL queries (intent=sql):**
1. ONLY use data from SQL QUERY RESULTS
2. Include actual values + units
3. For "show my X" - just give the value
4. For "list high/low" - bullet list ONLY abnormal tests
5. For "summarize" - abnormal first (with values), then brief normal mention
6. Max 80 words

**For RAG queries (intent=rag):**
1. Use MEDICAL GUIDELINES + patient's SQL results if available
2. If patient has the test result, reference their actual value
3. ALWAYS use bullet points - never write causes/symptoms as a run-on paragraph
4. NEVER write "CAUSE: text. CAUSE2: text." inline - each cause must be a separate bullet on its own line
5. Structure: 1 sentence intro → blank line → bullet list of causes → blank line → patient value if available
6. Avoid jargon - use plain language
7. Max 100 words

**For both:**
- NEVER include HTML or markdown code blocks
- Use \\n\\n for paragraph breaks (double newline)
- Use • or - for bullets, with \\n between items (single newline)
- For emphasis, use CAPS or descriptive words (avoid ** markdown syntax)
- **CRITICAL FORMATTING**:
  * Before first bullet: double newline (\\n\\n)
  * Between bullets: single newline (\\n)
  * Example: "Text here:\\n\\n• Item 1\\n• Item 2\\n• Item 3" 
- Reference patient's actual values when discussing them
- watch_for: Only if abnormal or concerning - be specific
- sources: Empty [] for SQL, ["Medical Guidelines"] for RAG

**Clinic Recommendations (CRITICAL):**
- NEVER invent or hallucinate doctor names, clinic names, or phone numbers
- ONLY include specialist info if a clinic_info chunk is present in MEDICAL GUIDELINES above
- If a clinic_info chunk is present AND the test is ABNORMAL: include the doctor details exactly as shown in the chunk
- If no clinic_info in MEDICAL GUIDELINES: do NOT mention any doctor or specialist by name
- For abnormal values with no clinic info: add to watch_for "Consult your doctor about this result"
- Format when clinic info IS available:
  "📋 Recommended Specialist:\n\nDr. [Name] ([Specialization])\n[Clinic Name]\n📞 [Contact]\n[Address]"

**FORBIDDEN:**
- Repeating the same test value multiple times
- Listing tests not asked about
- Vague warnings ("see doctor") without context
- Medical advice (only information)
- Placeholder text like "No watch_for available" or "No sources available"
- Mentioning missing fields (if watch_for is empty, just omit it - don't say it's missing)

Return valid JSON:
{{"direct_answer":"...","guideline_context":"...","trend_summary":"...","watch_for":"...","sources":[],"intent_handled":"{intent}"}}\
"""


# ── PDF Report Generation ────────────────────────────────────────────────────

PROMPT_PDF_REPORT = """\
Generate a comprehensive medical report summary for PDF generation.

=== FEW-SHOT EXAMPLES ===

EXAMPLE 1 (Blood Count Report):
PATIENT: Ajay Singh, 28 years, Female, O+
TEST RESULTS:
  - Hemoglobin: 13.8 g/dL (normal, ref: 12.0-16.0)
  - WBC Count: 12,500 cells/µL (high, ref: 4,000-11,000)
  - Platelets: 2.8 lakh/µL (normal, ref: 1.5-4.0)
  - RBC Count: 4.8 million/µL (normal, ref: 4.0-5.5)
TRENDS: WBC increased 15% over 2 months (from 10,800 to 12,500)
CLINIC: Dr. Neha Kapoor, Hematologist, Delhi Blood Centre, +91-98112-34567

CORRECT FORMAT:
{{"summary":"Complete Blood Count (CBC) Analysis","abnormal_findings":"• WBC Count: 12,500 cells/µL (ELEVATED)\\n  - 24% above normal range\\n  - Increased 15% over 2 months","normal_findings":"• Hemoglobin: 13.8 g/dL ✓\\n• Platelets: 2.8 lakh/µL ✓\\n• RBC Count: 4.8 million/µL ✓","clinical_interpretation":"Elevated WBC count suggests:\\n• Active infection (viral/bacterial)\\n• Inflammatory response\\n• Immune system activation\\n\\nMild elevation - monitor if symptoms present.","recommendations":"1. Consult specialist if fever, fatigue, or pain develops\\n2. Repeat CBC in 2-4 weeks to track trend\\n3. Stay hydrated and rest adequately","specialist_info":"📋 Recommended Specialist:\\nDr. Neha Kapoor (Hematologist)\\nDelhi Blood & Bone Marrow Centre\\n📞 +91-98112-34567\\nB-14, Lajpat Nagar Phase II, New Delhi - 110024","risk_level":"moderate"}}

EXAMPLE 2 (Liver Function Test - Critical):
PATIENT: Purva Miglani, 28 years, Female, A+
TEST RESULTS:
  - SGPT (ALT): 145 U/L (high, ref: 7-56)
  - SGOT (AST): 98 U/L (high, ref: 10-40)
  - Total Bilirubin: 2.8 mg/dL (high, ref: 0.1-1.2)
  - Alkaline Phosphatase: 68 U/L (normal, ref: 40-150)
TRENDS: SGPT rising (85→145 over 3 months)
CLINIC: Dr. Priya Sharma, Hepatologist, City Liver Centre, +91-98765-43210

CORRECT FORMAT:
{{"summary":"Liver Function Test (LFT) - Abnormal Enzymes","abnormal_findings":"• SGPT (ALT): 145 U/L (CRITICAL - 159% above normal)\\n• SGOT (AST): 98 U/L (ELEVATED - 145% above normal)\\n• Total Bilirubin: 2.8 mg/dL (HIGH - 133% above normal)","normal_findings":"• Alkaline Phosphatase: 68 U/L ✓","clinical_interpretation":"⚠️ Significant liver enzyme elevation indicates:\\n• Liver inflammation (hepatitis)\\n• Fatty liver disease\\n• Medication-induced liver injury\\n\\nRising trend over 3 months requires immediate attention.","recommendations":"🚨 URGENT:\\n1. Consult hepatologist within 48 hours\\n2. Avoid alcohol completely\\n3. Review all medications with doctor\\n4. Consider liver imaging (ultrasound)\\n5. Repeat LFT in 1-2 weeks","specialist_info":"📋 CONSULT IMMEDIATELY:\\nDr. Priya Sharma (Hepatologist)\\nCity Liver & Gastro Centre\\n📞 +91-98765-43210\\nSCO 45, Model Town, Gurugram - 122001\\nAvailable: Mon-Sat 9am-6pm","risk_level":"high"}}

=== YOUR TASK ===

PATIENT INFO:
{patient_name}, {patient_age} years, {patient_gender}

TEST RESULTS (with reference ranges):
{test_results}

TREND ANALYSIS:
{trend_summary}

MEDICAL GUIDELINES:
{rag_context}

CLINIC INFORMATION:
{clinic_info}

=== FORMATTING RULES ===

**Section: summary**
- Brief title of test panel (e.g., "Complete Blood Count", "Liver Function Test")
- 3-5 words max

**Section: abnormal_findings**
- List ALL tests outside normal range
- Format: "• TestName: Value Unit (STATUS - X% above/below normal)"
- Include trend if worsening: "↑ Increased 15% over 2 months"
- Use symbols: ⚠️ for critical, ↑ rising, ↓ falling
- Empty if all normal

**Section: normal_findings**
- List tests within range with ✓ checkmark
- Format: "• TestName: Value Unit ✓"
- Max 6 tests (if more, say "8 other tests within normal range")

**Section: clinical_interpretation**
- Explain what abnormal findings mean (plain language)
- List possible causes (bullets)
- Reference trends if significant
- Max 100 words

**Section: recommendations**
- Numbered list (1, 2, 3...)
- Actionable steps patient can take
- Include urgency if critical (🚨 URGENT)
- Lifestyle changes if relevant
- When to repeat tests

**Section: specialist_info**
- ONLY if abnormal findings exist
- Use clinic info from knowledge base
- Format with emojis: 📋 📞
- Include: doctor name, specialization, clinic, contact, address, hours
- Empty if all tests normal

**Section: risk_level**
- One word: "low", "moderate", "high", "critical"
- Based on: severity of abnormal values + trends + count of abnormal tests

**STYLE GUIDELINES:**
- Use emojis strategically (⚠️ 🚨 ✓ 📋 📞 ↑ ↓)
- Bold key findings: **ELEVATED**, **CRITICAL**
- Keep sentences short (max 15 words)
- Use medical terms + plain language explanation
- Be direct and clear - this is for a medical report

Return ONLY valid JSON:
{{"summary":"...","abnormal_findings":"...","normal_findings":"...","clinical_interpretation":"...","recommendations":"...","specialist_info":"...","risk_level":"..."}}\
"""


# ── Long-term Memory Summary ──────────────────────────────────────────────────

PROMPT_LTM_SUMMARY = """\
Summarize these recent medical consultations in 2-3 sentences.
Focus on tests discussed, trends, and concerns raised.
Consultations: {history}
Return only the summary."""
