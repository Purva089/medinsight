"""
Report Generator Agent - Creates downloadable PDF reports with visualizations.

Uses A2A to orchestrate data gathering and chart generation.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from app.agents.state import MedInsightState
from app.agents.a2a_protocol import (
    get_a2a_hub, 
    request_trend_summary,
    request_guidelines,
    A2ARequest
)
from app.core.logging import get_logger

log = get_logger(__name__)


async def report_generator_node(state: MedInsightState) -> MedInsightState:
    """
    Generate comprehensive downloadable PDF report.
    
    Workflow:
    1. A2A → sql_agent: Get all patient lab results
    2. A2A → trend_agent: Get trend analysis + charts
    3. A2A → rag_agent: Get medical explanations for abnormal values
    4. Generate PDF with:
       - Patient demographics
       - Test results table
       - Trend charts (matplotlib/plotly)
       - Medical interpretations
       - Recommendations
    5. Return: {chat_summary: "...", pdf_url: "..."}
    """
    hub = get_a2a_hub()
    patient_id = state["patient_id"]
    patient_profile = state.get("patient_profile", {})
    
    log.info("report_generator_start", 
             patient_id=patient_id,
             patient_profile=patient_profile,
             has_age=bool(patient_profile.get("age")),
             has_gender=bool(patient_profile.get("gender")))
    
    # ── 1. Get all patient data from state (extracted tests + SQL if available) ────
    # First priority: extracted_tests from the uploaded report
    extracted_tests = state.get("extracted_tests", [])
    all_results = [
        {
            "test_name": t.get("test_name"),
            "value": t.get("value"),
            "unit": t.get("unit"),
            "status": t.get("status"),
            "reference_range_low": t.get("reference_range_low"),
            "reference_range_high": t.get("reference_range_high"),
            "category": t.get("category"),
        }
        for t in extracted_tests
        if t.get("test_name")
    ]
    
    # Second priority: Try SQL query via A2A if no extracted tests
    if not all_results:
        sql_request = A2ARequest(
            request_id=str(uuid.uuid4()),
            source_agent="report_generator",
            target_agent="text_to_sql_agent",
            action="query_data",
            payload={"query": "Get all my test results from all reports"},
        )
        
        try:
            sql_response = await hub.send_request(sql_request, state)
            all_results = sql_response.data.get("results", []) if (sql_response.success and sql_response.data) else []
        except Exception as exc:
            log.error("a2a_sql_request_failed", error=str(exc)[:200], exc_info=True)
            all_results = []
    
    # ── 2. Get trend analysis via A2A ─────────────────────────────────────────
    try:
        trend_summary = await request_trend_summary("report_generator", state)
        trend_data = state.get("trend_results", [])
        log.info("trend_data_retrieved", 
                 trend_count=len(trend_data),
                 trend_sample=trend_data[0] if trend_data else None,
                 has_data_points=len(trend_data[0].get("data_points", [])) if trend_data else 0)
    except Exception as exc:
        log.error("a2a_trend_request_failed", error=str(exc)[:200], exc_info=True)
        trend_summary = {"summary": "", "trend_count": 0}
        trend_data = []
    
    # ── 3. Get medical guidelines ─────────────────────────────────────────────
    abnormal_tests = [r for r in all_results if r.get("status") in ("high", "low", "critical")]
    normal_tests = [r for r in all_results if r.get("status") == "normal"]
    
    guidelines_collection = []
    
    # Get guidelines for abnormal tests (detailed explanations)
    for test in abnormal_tests[:5]:  # Limit to top 5 to avoid too many A2A calls
        try:
            test_name = test.get("test_name", "")
            if not test_name:
                continue
            guidelines = await request_guidelines(
                "report_generator",
                state,
                f"high {test_name}"
            )
            if guidelines and guidelines.get("rag_context"):
                guidelines_collection.append({
                    "test": test_name,
                    "explanation": guidelines["rag_context"][:500],  # Truncate
                    "type": "abnormal"
                })
        except Exception as exc:
            log.error("guideline_request_failed", test=test_name, error=str(exc)[:200])
            continue
    
    # If all tests are normal, add a simple educational note (no RAG calls to avoid bad formatting)
    if len(abnormal_tests) == 0 and len(normal_tests) > 0:
        # Instead of RAG calls, add a simple congratulatory message
        educational_note = (
            "All your test results are within healthy ranges. This indicates:\n\n"
            "• Your blood cell counts are balanced\n"
            "• Organ function is normal\n"
            "• No immediate health concerns detected\n\n"
            "Continue maintaining a healthy lifestyle with balanced diet, regular exercise, "
            "and adequate sleep. Consult your doctor if you experience any symptoms."
        )
        guidelines_collection.append({
            "test": "Overall Health",
            "explanation": educational_note,
            "type": "summary"
        })
    
    # ── 4. Generate PDF report ────────────────────────────────────────────────
    report_data = {
        "patient_name": patient_profile.get("name", "Patient"),
        "patient_age": patient_profile.get("age"),
        "patient_gender": patient_profile.get("gender"),
        "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "test_results": all_results,
        "trend_summary": trend_summary.get("summary", ""),
        "trend_charts": trend_data,  # For visualization
        "abnormal_count": len(abnormal_tests),
        "guidelines": guidelines_collection,
    }
    
    # Generate PDF (returns dict with filename and base64 bytes)
    try:
        pdf_result = await _generate_pdf_report(report_data)
    except Exception as exc:
        log.error("pdf_generation_failed", error=str(exc)[:200], exc_info=True)
        pdf_result = {"filename": "error.pdf", "bytes": "", "error": str(exc)[:200]}
    
    # ── 5. Prepare response ───────────────────────────────────────────────────
    if len(all_results) > 0:
        # Build summary text based on results
        if len(abnormal_tests) == 0:
            # All normal - simple congratulatory message
            chat_summary = (
                f"📊 Report Generated Successfully!\n\n"
                f"✓ All {len(all_results)} tests are NORMAL - Great news!\n"
                f"✓ Trends analyzed: {trend_summary.get('trend_count', 0)}\n\n"
                f"Your blood work shows healthy levels across all parameters. "
                f"This indicates good overall health with no immediate concerns. "
                f"Continue your healthy lifestyle and routine check-ups."
            )
        else:
            # Has abnormal values - focus on those
            chat_summary = (
                f"📊 Report Generated Successfully!\n\n"
                f"• Total tests: {len(all_results)}\n"
                f"• Abnormal values: {len(abnormal_tests)}\n"
                f"• Trends analyzed: {trend_summary.get('trend_count', 0)}\n\n"
                f"Your comprehensive medical report is ready with detailed analysis, "
                f"trend charts, and medical interpretations."
            )
    else:
        # No data found - provide helpful message
        chat_summary = (
            "⚠️ **No Test Data Found**\n\n"
            "Unable to generate report - no lab test results found in your records.\n\n"
            "**To generate a report:**\n"
            "1. Upload a lab report PDF in the Upload section\n"
            "2. Wait for processing to complete\n"
            "3. Return here to generate your comprehensive report"
        )
    
    state["final_response"] = {
        "direct_answer": chat_summary,
        "guideline_context": "",
        "trend_summary": trend_summary.get("summary", ""),
        "watch_for": "" if len(all_results) > 0 else "Please upload a lab report to enable report generation.",
        "sources": [],
        "disclaimer": "This report is for informational purposes only." if len(all_results) > 0 else "",
        "confidence": "high" if len(all_results) > 0 else "low",
        "intent_handled": "report_generation",
        "pdf_data": pdf_result if len(all_results) > 0 else None,  # PDF bytes + filename
    }
    
    log.info(
        "report_generator_complete",
        patient_id=patient_id,
        pdf_filename=pdf_result.get("filename", "none"),
        test_count=len(all_results),
    )
    
    return state


async def _generate_pdf_report(data: dict) -> dict:
    """
    Generate concise, patient-friendly PDF report (2-3 pages).
    
    Structure:
    1. Patient Info + Executive Summary (all normal vs abnormal found)
    2. Abnormal Tests (detailed) - if any exist
    3. Normal Tests (compact summary)
    4. Trend Analysis (if available)
    5. Specialist Recommendations (only if abnormal tests exist)
    6. Disclaimer
    
    Returns: dict with 'filename' and 'bytes' (base64 encoded)
    """
    import base64
    import io
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    except ImportError:
        log.error("reportlab_not_installed", error="reportlab is required for PDF generation")
        return {"filename": "error.txt", "bytes": "", "error": "ReportLab not installed"}
    
    report_id = str(uuid.uuid4())[:8]
    patient_name = data.get('patient_name', 'Patient').replace(' ', '_')
    pdf_filename = f"medical_report_{patient_name}_{report_id}.pdf"
    
    # Generate PDF to BytesIO instead of file
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, 
                           rightMargin=72, leftMargin=72,
                           topMargin=60, bottomMargin=40)
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title', parent=styles['Heading1'], fontSize=22,
        textColor=colors.HexColor('#1E40AF'), spaceAfter=20, alignment=TA_CENTER
    )
    heading_style = ParagraphStyle(
        'Heading', parent=styles['Heading2'], fontSize=14,
        textColor=colors.HexColor('#1E40AF'), spaceAfter=10, spaceBefore=15
    )
    normal_style = styles['Normal']
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 1. TITLE & PATIENT INFO
    # ═══════════════════════════════════════════════════════════════════════════
    elements.append(Paragraph("📊 Medical Lab Report", title_style))
    elements.append(Spacer(1, 10))
    
    # Build age/gender string gracefully
    age = data.get('patient_age')
    gender = data.get('patient_gender')
    if age and gender:
        age_gender_str = f"{age} years | {gender}"
    elif age:
        age_gender_str = f"{age} years"
    elif gender:
        age_gender_str = gender
    else:
        age_gender_str = "Not specified"
    
    patient_info = [
        ["Patient:", data.get('patient_name', 'N/A')],
        ["Age/Gender:", age_gender_str],
        ["Generated:", data.get('generated_date', 'N/A')],
    ]
    patient_table = Table(patient_info, colWidths=[1.2*inch, 5*inch])
    patient_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(patient_table)
    elements.append(Spacer(1, 15))
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 2. EXECUTIVE SUMMARY & STATUS
    # ═══════════════════════════════════════════════════════════════════════════
    test_results = data.get('test_results', [])
    abnormal_tests = [t for t in test_results if t.get('status', '').lower() in ('high', 'low', 'critical')]
    normal_tests = [t for t in test_results if t.get('status', '').lower() == 'normal']
    
    # Add results summary with visual status box
    elements.append(Paragraph("📋 Summary", heading_style))
    
    if not abnormal_tests:
        # All normal - green box with encouraging message
        summary_bg = colors.HexColor('#D1FAE5')
        summary_text = (
            f"✓ <b>All {len(test_results)} tests are within normal range.</b><br/><br/>"
            f"Your results indicate good overall health. "
            f"Continue maintaining a healthy lifestyle with balanced nutrition, regular exercise, and adequate rest."
        )
    else:
        # Abnormal found - yellow box with alert
        summary_bg = colors.HexColor('#FEF3C7')
        summary_text = (
            f"⚠ <b>{len(abnormal_tests)} test(s) need attention</b> out of {len(test_results)} total.<br/><br/>"
            f"The abnormal results are detailed below with reference ranges and recommendations. "
            f"Please consult with your healthcare provider to discuss these findings."
        )
    
    summary_table = Table([[Paragraph(summary_text, normal_style)]], colWidths=[6.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), summary_bg),
        ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#10B981') if not abnormal_tests else colors.HexColor('#F59E0B')),
        ('LEFTPADDING', (0, 0), (-1, -1), 15),
        ('RIGHTPADDING', (0, 0), (-1, -1), 15),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 3. ABNORMAL TESTS (Detailed) - Only if abnormal tests exist
    # ═══════════════════════════════════════════════════════════════════════════
    if abnormal_tests:
        elements.append(Paragraph("⚠️ Tests Needing Attention", heading_style))

        # Single clean table for all abnormal tests
        abnormal_header = [[
            Paragraph('<b>Test Name</b>', normal_style),
            Paragraph('<b>Your Value</b>', normal_style),
            Paragraph('<b>Reference Range</b>', normal_style),
            Paragraph('<b>Status</b>', normal_style),
        ]]
        abnormal_rows = []
        for test in abnormal_tests:
            test_name = test.get('test_name', 'Unknown')
            value = test.get('value', 'N/A')
            unit = test.get('unit', '')
            ref_low = test.get('reference_range_low')
            ref_high = test.get('reference_range_high')
            status = test.get('status', '').upper()
            ref_range = f"{ref_low} - {ref_high}" if ref_low and ref_high else "N/A"
            abnormal_rows.append([
                test_name,
                f"{value} {unit}".strip(),
                ref_range,
                status,
            ])

        abnormal_table = Table(abnormal_header + abnormal_rows,
                               colWidths=[2.2*inch, 1.6*inch, 1.8*inch, 0.9*inch])
        abnormal_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F87171')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.HexColor('#FEF3C7'), colors.HexColor('#FFFBEB')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(abnormal_table)
        elements.append(Spacer(1, 15))
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 4. NORMAL TESTS (Compact Summary)
    # ═══════════════════════════════════════════════════════════════════════════
    if normal_tests:
        elements.append(Paragraph("✓ Normal Test Results", heading_style))
        
        # Compact table
        normal_data = [['Test Name', 'Value', 'Reference Range']]
        for test in normal_tests:
            ref_low = test.get('reference_range_low')
            ref_high = test.get('reference_range_high')
            ref_range = f"{ref_low}-{ref_high}" if ref_low and ref_high else "N/A"
            normal_data.append([
                test.get('test_name', 'N/A'),
                f"{test.get('value', 'N/A')} {test.get('unit', '')}",
                ref_range
            ])
        
        normal_table = Table(normal_data, colWidths=[2.5*inch, 2*inch, 2*inch])
        normal_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10B981')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(normal_table)
        elements.append(Spacer(1, 15))
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 5. TREND ANALYSIS (Only if trend data exists)
    # ═══════════════════════════════════════════════════════════════════════════
    trend_charts = data.get('trend_charts', [])
    log.info("pdf_trend_charts_check", 
             trend_count=len(trend_charts),
             has_trend_data=bool(trend_charts),
             first_chart=trend_charts[0] if trend_charts else None)
    
    if trend_charts and len(trend_charts) > 0:
        from reportlab.platypus import Image
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        import io
        
        elements.append(Paragraph("📈 Trends Over Time", heading_style))
        
        # Generate charts for up to 4 tests
        for idx, trend in enumerate(trend_charts[:4]):
            test_name = trend.get('test_name', 'Unknown')
            data_points = trend.get('data_points', [])
            ref_low = trend.get('reference_low')
            ref_high = trend.get('reference_high')
            
            if len(data_points) < 2:
                continue
            
            # Extract dates and values
            dates = [p.get('date', '') for p in data_points]
            values = [p.get('value', 0) for p in data_points]
            
            # Create matplotlib chart
            fig, ax = plt.subplots(figsize=(6, 3))
            ax.plot(dates, values, marker='o', linewidth=2, markersize=6, color='#3B82F6')
            
            # Add reference range shading
            if ref_low is not None and ref_high is not None:
                ax.axhspan(ref_low, ref_high, alpha=0.2, color='green', label='Normal Range')
            
            ax.set_title(f"{test_name} Trend", fontsize=12, fontweight='bold')
            ax.set_xlabel('Date', fontsize=9)
            ax.set_ylabel('Value', fontsize=9)
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis='x', rotation=45, labelsize=8)
            ax.tick_params(axis='y', labelsize=8)
            
            if ref_low is not None and ref_high is not None:
                ax.legend(fontsize=8)
            
            plt.tight_layout()
            
            # Save to BytesIO
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
            img_buffer.seek(0)
            plt.close(fig)
            
            # Add to PDF
            img = Image(img_buffer, width=5*inch, height=2.5*inch)
            elements.append(img)
            elements.append(Spacer(1, 10))
        
        elements.append(Spacer(1, 15))
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 6. SPECIALIST RECOMMENDATIONS (Only if abnormal tests exist)
    # ═══════════════════════════════════════════════════════════════════════════
    if abnormal_tests:
        elements.append(Paragraph("👨‍⚕️ Recommended Next Steps", heading_style))

        # Determine specialist type based on abnormal test categories
        categories = list({t.get('category', 'others') for t in abnormal_tests})
        specialist_map = {
            'liver':       ('Gastroenterologist / Hepatologist', 'for liver function abnormalities'),
            'blood_count': ('Hematologist', 'for blood count abnormalities'),
            'metabolic':   ('Endocrinologist', 'for metabolic panel abnormalities'),
            'thyroid':     ('Endocrinologist', 'for thyroid function abnormalities'),
            'kidney':      ('Nephrologist', 'for kidney function abnormalities'),
            'cardiac':     ('Cardiologist', 'for cardiac marker abnormalities'),
        }
        specialists = []
        for cat in categories:
            if cat in specialist_map:
                specialists.append(specialist_map[cat])
        if not specialists:
            specialists = [('General Physician', 'to review your abnormal results')]

        steps = [
            "1. Schedule an appointment with your doctor to review these results.",
        ]
        for spec, reason in specialists:
            steps.append(f"2. Consider consulting a {spec} {reason}.")
        steps.append("3. Do not self-medicate based on this report.")
        steps.append("4. Repeat tests in 4-6 weeks to monitor changes if advised.")

        for step in steps:
            elements.append(Paragraph(step, normal_style))
            elements.append(Spacer(1, 4))

        elements.append(Spacer(1, 12))
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 7. DISCLAIMER
    # ═══════════════════════════════════════════════════════════════════════════
    elements.append(Paragraph("⚠️ Important Disclaimer", heading_style))
    disclaimer_text = (
        "<i>This report is generated by MedInsight AI for informational purposes only. "
        "It should NOT replace professional medical advice, diagnosis, or treatment. "
        "Always consult your doctor or qualified healthcare provider with any health questions. "
        "In case of emergency, call your local emergency number immediately.</i>"
    )
    elements.append(Paragraph(disclaimer_text, normal_style))
    elements.append(Spacer(1, 10))
    
    # Report ID footer
    footer_text = f"<i>Report ID: {report_id} | Generated by MedInsight AI v1.0</i>"
    elements.append(Paragraph(footer_text, normal_style))
    
    # Build PDF
    doc.build(elements)
    
    # Get bytes and encode to base64
    pdf_buffer.seek(0)
    pdf_bytes = pdf_buffer.read()
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    
    log.info(
        "pdf_generated",
        filename=pdf_filename,
        test_count=len(test_results),
        abnormal_count=len(abnormal_tests),
        normal_count=len(normal_tests),
        has_trends=bool(trend_charts),
        size_kb=round(len(pdf_bytes) / 1024, 1)
    )
    
    return {
        "filename": pdf_filename,
        "bytes": pdf_base64,
        "size_kb": round(len(pdf_bytes) / 1024, 1)
    }


async def _generate_simple_text_report(data: dict) -> str:
    """
    Fallback: Generate simple text report if ReportLab not available.
    """
    report_id = str(uuid.uuid4())[:8]
    patient_name = data.get('patient_name', 'Patient').replace(' ', '_')
    txt_filename = f"medical_report_{patient_name}_{report_id}.txt"
    pdf_dir = Path("data/generated_reports")
    pdf_dir.mkdir(parents=True, exist_ok=True)
    
    txt_path = pdf_dir / txt_filename
    
    # Generate simple text report
    content = []
    content.append("=" * 60)
    content.append("MEDICAL LAB REPORT")
    content.append("=" * 60)
    content.append(f"\nPatient: {data.get('patient_name', 'N/A')}")
    content.append(f"Age: {data.get('patient_age', 'N/A')}")
    content.append(f"Gender: {data.get('patient_gender', 'N/A')}")
    content.append(f"Generated: {data.get('generated_date', 'N/A')}")
    content.append("\n" + "=" * 60)
    content.append("TEST RESULTS")
    content.append("=" * 60 + "\n")
    
    test_results = data.get('test_results', [])
    for test in test_results:
        content.append(f"\nTest: {test.get('test_name', 'N/A')}")
        content.append(f"  Value: {test.get('value', 'N/A')} {test.get('unit', '')}")
        ref_low = test.get('reference_range_low')
        ref_high = test.get('reference_range_high')
        if ref_low and ref_high:
            content.append(f"  Reference: {ref_low}-{ref_high}")
        content.append(f"  Status: {test.get('status', 'N/A').upper()}")
    
    content.append("\n" + "=" * 60)
    content.append("DISCLAIMER")
    content.append("=" * 60)
    content.append("\nThis is for informational purposes only.")
    content.append("Always consult your healthcare provider.\n")
    
    txt_path.write_text("\n".join(content))
    
    log.warning(
        "text_report_generated_fallback",
        filename=txt_filename,
        reason="reportlab_not_available"
    )
    
    return f"/api/v1/reports/download/{txt_filename}"


# ── Visualization helpers ──────────────────────────────────────────────────────

def generate_trend_chart(trend_data: list[dict]) -> bytes:
    """
    Generate trend chart using matplotlib.
    
    Args:
        trend_data: List of trend results from trend_agent
        
    Returns:
        PNG image bytes for embedding in PDF
    """
    import io
    
    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend (no GUI)
        import matplotlib.pyplot as plt
    except ImportError:
        log.error("matplotlib_not_installed", error="matplotlib is required for chart generation")
        return b""  # Return empty bytes if matplotlib not available
    
    if not trend_data:
        log.warning("generate_trend_chart_no_data")
        return b""
    
    try:
        # Create chart
        fig, ax = plt.subplots(figsize=(10, 6))
        
        for trend in trend_data:
            test_name = trend.get("test_name", "Unknown")
            history = trend.get("history", [])
            
            if not history:
                continue
                
            dates = [h.get("date") for h in history if h.get("date")]
            values = [h.get("value") for h in history if h.get("value") is not None]
            
            if dates and values and len(dates) == len(values):
                ax.plot(dates, values, marker='o', label=test_name)
        
        ax.set_xlabel("Date")
        ax.set_ylabel("Value")
        ax.set_title("Lab Result Trends Over Time")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Convert to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)  # Free memory
        
        return buf.read()
    except Exception as exc:
        log.error("generate_trend_chart_error", error=str(exc)[:200], exc_info=True)
        return b""
