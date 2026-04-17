import asyncio
import json
from app.services.llm_service import LLMService

async def test():
    llm = LLMService()
    
    # Simple test prompt
    prompt = """You are a medical AI. Respond with ONLY valid JSON, no markdown:
{"direct_answer":"Low hemoglobin (12.5) indicates mild anemia.","guideline_context":"Normal 13-17 g/dL","trend_summary":"Single reading","watch_for":"Fatigue","sources":["Report"],"disclaimer":"Consult doctor","confidence":"medium","intent_handled":"report"}"""
    
    print("Calling LLM (will try fallback if rate limited)...")
    try:
        result = await llm.call_reasoning(prompt, 'report')
        print("="*50)
        print("SUCCESS! Response:")
        print(result[:500])
        print("="*50)
        
        # Try to parse
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()
        
        try:
            parsed = json.loads(cleaned)
            print("PARSED OK! Keys:", list(parsed.keys()))
        except Exception as e:
            print("PARSE FAILED:", e)
    except Exception as e:
        print("LLM CALL FAILED:", e)

if __name__ == "__main__":
    asyncio.run(test())
