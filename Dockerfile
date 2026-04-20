# ============================================================================
# MedInsight - Unified Multi-Service Dockerfile
# Runs both Backend (FastAPI) and Frontend (Streamlit) in single container
# Optimized for Azure Container Apps deployment
# ============================================================================

FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ============================================================================
# Stage 1: Dependencies Installation
# ============================================================================
FROM base as dependencies

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Application Build
# ============================================================================
FROM base as application

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data/generated_reports data/synthetic_reports/uploads

# Create non-root user for security
RUN useradd -m -u 1000 medinsight && \
    chown -R medinsight:medinsight /app && \
    mkdir -p /home/medinsight/.streamlit && \
    chown -R medinsight:medinsight /home/medinsight

USER medinsight

# Expose ports
# 8000 = FastAPI backend
# 8501 = Streamlit frontend
EXPOSE 8000 8501

# ============================================================================
# Startup Script - Runs both services using supervisord
# ============================================================================
FROM application as final

USER root

# Install supervisor + nginx to manage multiple processes
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Configure nginx as reverse proxy on port 80 → Streamlit 8501
# Also proxies /api/ → FastAPI 8000
RUN cat > /etc/nginx/sites-available/default <<'NGINXEOF'
server {
    listen 80;
    server_name _;

    # Streamlit WebSocket support
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;

    # API routes → FastAPI backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }

    # Everything else → Streamlit frontend
    location / {
        proxy_pass http://127.0.0.1:8501;
    }
}
NGINXEOF

# Create supervisor config
RUN mkdir -p /var/log/supervisor
COPY <<EOF /etc/supervisor/conf.d/medinsight.conf
[supervisord]
nodaemon=true
user=root
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid

[program:nginx]
command=/usr/sbin/nginx -g "daemon off;"
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/nginx.err.log
stdout_logfile=/var/log/supervisor/nginx.out.log

[program:backend]
command=/usr/local/bin/uvicorn app.api.main:app --host 0.0.0.0 --port 8000
directory=/app
user=medinsight
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/backend.err.log
stdout_logfile=/var/log/supervisor/backend.out.log
environment=PYTHONUNBUFFERED=1,HOME=/home/medinsight

[program:frontend]
command=/usr/local/bin/streamlit run app/frontend/main.py --server.port=8501 --server.address=0.0.0.0
directory=/app
user=medinsight
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/frontend.err.log
stdout_logfile=/var/log/supervisor/frontend.out.log
environment=PYTHONUNBUFFERED=1,HOME=/home/medinsight,PYTHONPATH=/app
EOF

# Expose port 80 (nginx proxy) + internal ports
EXPOSE 80 8000 8501

# Health check on nginx port 80
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:80/ || exit 1

# Start supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
