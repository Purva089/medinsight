# Azure Deployment Guide for MedInsight

## 📋 Prerequisites

- Azure CLI installed (`az`)
- Docker installed
- Azure subscription active
- GitHub repository (for CI/CD)

## 🚀 Quick Deploy to Azure Container Apps

### Option 1: Manual Deployment (Fast)

```bash
# 1. Login to Azure
az login

# 2. Set variables
RESOURCE_GROUP="medinsight-rg"
LOCATION="eastus"
ACR_NAME="medinsightacr"
CONTAINER_APP="medinsight-app"
ENVIRONMENT="medinsight-env"

# 3. Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# 4. Create Azure Container Registry
az acr create --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME --sku Basic --admin-enabled true

# 5. Build and push Docker image
az acr build --registry $ACR_NAME \
  --image medinsight:latest \
  --file Dockerfile.unified .

# 6. Create Container Apps environment
az containerapp env create \
  --name $ENVIRONMENT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# 7. Deploy container app
az containerapp create \
  --name $CONTAINER_APP \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT \
  --image $ACR_NAME.azurecr.io/medinsight:latest \
  --registry-server $ACR_NAME.azurecr.io \
  --target-port 8501 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars \
    DATABASE_URL="<YOUR_NEON_DB_URL>" \
    GROQ_API_KEY="<YOUR_GROQ_KEY>" \
    SECRET_KEY="<YOUR_SECRET>" \
    API_BASE_URL="http://localhost:8000"

# 8. Get app URL
az containerapp show \
  --name $CONTAINER_APP \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn -o tsv
```

### Option 2: GitHub Actions CI/CD (Automated)

1. **Set up GitHub Secrets:**
   - `AZURE_CREDENTIALS` - Service principal JSON
   - `ACR_LOGIN_SERVER` - `medinsightacr.azurecr.io`
   - `ACR_USERNAME` - ACR admin username
   - `ACR_PASSWORD` - ACR admin password

2. **Push to main branch** - automatic deployment via `.github/workflows/azure-deploy.yml`

## 🗂️ Required Files for Azure

### ✅ KEEP These Files:
- `Dockerfile.unified` - Single container for both services
- `.dockerignore` - Reduce image size
- `requirements.txt` - Python dependencies
- `.github/workflows/azure-deploy.yml` - CI/CD pipeline
- `AZURE_DEPLOYMENT.md` - This guide

### ❌ DELETE These Files (Unnecessary for Azure):
- `Dockerfile` - Old backend-only file
- `Dockerfile.frontend` - Old frontend-only file
- `docker-compose.yml` - Local development only
- `docker-compose.azure.yml` - Not needed for Container Apps
- `azure-setup.sh` - Manual script (use commands above)
- `azure-setup.ps1` - Manual script (use commands above)

## 🔧 Environment Variables

Set these in Azure Container Apps:

```bash
# Required
DATABASE_URL=postgresql://user:pass@neon.tech/db
GROQ_API_KEY=gsk_xxxxx
SECRET_KEY=your-secret-key-here

# Optional
API_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:8501
LOG_LEVEL=INFO
ENABLE_CORS=true
```

## 💰 Cost Optimization

**Estimated Monthly Cost:**
- Container Apps: $30-50/month (1 vCPU, 2GB RAM)
- Container Registry: $5/month (Basic tier)
- Neon PostgreSQL: Free tier (or $19/month Pro)

**Total: ~$35-75/month**

### Tips to Reduce Costs:
1. Use scale-to-zero (min replicas = 0)
2. Use Neon free tier for PostgreSQL
3. Delete unused images in ACR
4. Set max replicas = 1 (for low traffic)

## 🔍 Monitoring

```bash
# View logs
az containerapp logs show \
  --name $CONTAINER_APP \
  --resource-group $RESOURCE_GROUP \
  --follow

# Check health
az containerapp show \
  --name $CONTAINER_APP \
  --resource-group $RESOURCE_GROUP \
  --query properties.runningStatus
```

## 🚨 Troubleshooting

### Container won't start
```bash
# Check events
az containerapp revision list \
  --name $CONTAINER_APP \
  --resource-group $RESOURCE_GROUP

# View detailed logs
az containerapp logs show \
  --name $CONTAINER_APP \
  --resource-group $RESOURCE_GROUP \
  --tail 100
```

### Database connection fails
- Verify `DATABASE_URL` is correct
- Check Neon database allows external connections
- Ensure firewall rules allow Azure IP ranges

### Frontend/Backend not accessible
- Verify ingress is set to `external`
- Check target port is `8501` (Streamlit)
- Ensure health check passes

## 📚 Additional Resources

- [Azure Container Apps Docs](https://learn.microsoft.com/en-us/azure/container-apps/)
- [Neon PostgreSQL Docs](https://neon.tech/docs/introduction)
- [Groq API Docs](https://console.groq.com/docs)
