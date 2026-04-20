# MedInsight Deployment Guide

## Development vs Production

### 🔧 **Development Mode** (with auto-reload)
```powershell
# Good for: Development, testing, making code changes
# Bad for: Performance testing, demos, production

cd "C:\Users\purvamiglani\OneDrive - Nagarro\Desktop\medinsight"
.\.venv312\Scripts\Activate.ps1
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

**⚠️ Known Issues:**
- First query after code change: **70-120 seconds** (server reloads during request)
- Unpredictable delays if editing files while testing
- Memory state resets on every file change

**✅ When to Use:**
- Actively developing features
- Making frequent code changes
- Testing new functionality

---

### 🚀 **Production Mode** (no reload)
```powershell
# Good for: Demos, performance testing, production deployments
# Bad for: Active development (need manual restart after changes)

cd "C:\Users\purvamiglani\OneDrive - Nagarro\Desktop\medinsight"
.\.venv312\Scripts\Activate.ps1
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

**✅ Benefits:**
- First query: **10-15 seconds** (one-time embedding model load)
- Subsequent queries: **3-5 seconds** (cached)
- No random delays from file watching
- Stable memory usage

**⚠️ Trade-off:**
- Must restart manually after code changes

---

## Performance Comparison

| Scenario | Development (--reload) | Production (no reload) |
|----------|----------------------|----------------------|
| **Startup time** | 2 seconds | 2 seconds |
| **First RAG query** | 70-120s (if reload triggered) | 10-15s (model load) |
| **Second RAG query** | 3-5s | 3-5s |
| **Code change impact** | Auto-restart (can interrupt requests) | Manual restart needed |

---

## Recommended Workflow

### **Option 1: Separate Terminals**
```powershell
# Terminal 1: Backend (production mode for testing)
uvicorn app.api.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
streamlit run app/frontend/main.py

# When testing: Use Terminal 1 without --reload
# When developing: Stop Terminal 1, add --reload, restart
```

### **Option 2: Use Reload But Wait**
```powershell
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```
**Rules:**
1. After saving a file, **wait 3 seconds** for "Application startup complete"
2. Don't test queries while "Reloading..." message is shown
3. Check logs for "app_started" before sending requests

---

## Startup Performance Optimization

### Current Strategy: **Lazy Loading** ✅
- Embedding model loads on **first RAG query** (~10s)
- App starts instantly
- Memory efficient (no load if RAG unused)

### Alternative: **Eager Loading** (Optional)

Uncomment in `app/api/main.py`:
```python
# Line 62-64
from app.agents.rag_agent import prewarm_rag
prewarm_rag()
```

**Trade-offs:**
- ✅ First query is fast (3-5s)
- ❌ Startup takes 12-17s
- ❌ Uses 500MB RAM even if RAG never used

**When to Enable:**
- Production deployments where every query must be fast
- Demo environments
- Customer-facing applications

**When to Disable (Current):**
- Development
- Resource-constrained environments
- Serverless deployments

---

## Production Deployment Checklist

- [ ] Remove `--reload` flag from uvicorn command
- [ ] Set `APP_DEBUG=false` in `.env`
- [ ] Enable prewarm in `main.py` (optional, for consistent speed)
- [ ] Configure reverse proxy (nginx/caddy) if needed
- [ ] Set up process manager (systemd/supervisor/PM2)
- [ ] Configure CORS origins for your domain
- [ ] Enable HTTPS
- [ ] Set up monitoring/logging aggregation
- [ ] Configure database connection pooling
- [ ] Review rate limits in `app/core/config.py`

---

## Common Issues

### Issue: "Query takes 2+ minutes"
**Cause:** Server auto-reload interrupted the request  
**Fix:** Use production mode OR wait for reload to complete

### Issue: "First query always slow"
**Cause:** Embedding model loads on demand  
**Fix:** Enable prewarm in `main.py` (see above)

### Issue: "Memory usage keeps growing"
**Cause:** Auto-reload doesn't release old imports  
**Fix:** Restart server manually instead of relying on auto-reload

---

## Frontend (Streamlit) Notes

Streamlit **always** auto-reloads on file changes. This is normal and doesn't affect backend performance.

Run separately from backend:
```powershell
streamlit run app/frontend/main.py
```

For production Streamlit deployment, consider:
- Docker with `CMD ["streamlit", "run", "app/frontend/main.py", "--server.headless=true"]`
- PM2 or systemd service
- Separate domain/subdomain from API

---

## Summary

**For Development:** Keep `--reload`, but **stop editing files during testing**

**For Production/Demos:** Remove `--reload`, optionally enable prewarm

**Current Setup (Lazy Loading):** Good balance for development - fast startup, acceptable first-query delay
