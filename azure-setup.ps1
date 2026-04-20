# ═══════════════════════════════════════════════════════════════════════════════
# MedInsight Azure Infrastructure Setup Script (PowerShell)
# ═══════════════════════════════════════════════════════════════════════════════
# Prerequisites:
# - Azure CLI installed: winget install Microsoft.AzureCLI
# - Logged in to Azure: az login
# ═══════════════════════════════════════════════════════════════════════════════

# Configuration Variables
$RESOURCE_GROUP = "medinsight-rg"
$LOCATION = "eastus"
$ACR_NAME = "medinsightacr"
$POSTGRES_SERVER = "medinsight-postgres-server"
$POSTGRES_DB = "medinsight"
$POSTGRES_ADMIN = "medinsightadmin"
$POSTGRES_SKU = "B_Gen5_1"  # Basic tier for dev
$CONTAINER_APP_ENV = "medinsight-env"
$BACKEND_APP = "medinsight-backend-app"
$FRONTEND_APP = "medinsight-frontend-app"

Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Blue
Write-Host "  MedInsight Azure Infrastructure Setup" -ForegroundColor Blue
Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Blue

# Step 1: Create Resource Group
Write-Host "`n[1/8] Creating Resource Group: $RESOURCE_GROUP" -ForegroundColor Green
az group create --name $RESOURCE_GROUP --location $LOCATION

# Step 2: Create Azure Container Registry (ACR)
Write-Host "`n[2/8] Creating Azure Container Registry: $ACR_NAME" -ForegroundColor Green
az acr create `
  --resource-group $RESOURCE_GROUP `
  --name $ACR_NAME `
  --sku Basic `
  --admin-enabled true

# Get ACR credentials
$ACR_USERNAME = az acr credential show --name $ACR_NAME --query "username" -o tsv
$ACR_PASSWORD = az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv

Write-Host "ACR Username: $ACR_USERNAME" -ForegroundColor Yellow
Write-Host "ACR Password: $ACR_PASSWORD" -ForegroundColor Yellow

# Step 3: Create Azure Database for PostgreSQL
Write-Host "`n[3/8] Creating Azure Database for PostgreSQL: $POSTGRES_SERVER" -ForegroundColor Green

# Generate random password
$POSTGRES_PASSWORD = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 20 | ForEach-Object {[char]$_})
$POSTGRES_PASSWORD += "!@#"  # Add special chars

az postgres server create `
  --resource-group $RESOURCE_GROUP `
  --name $POSTGRES_SERVER `
  --location $LOCATION `
  --admin-user $POSTGRES_ADMIN `
  --admin-password $POSTGRES_PASSWORD `
  --sku-name $POSTGRES_SKU `
  --version 14 `
  --ssl-enforcement Enabled

Write-Host "PostgreSQL Admin: $POSTGRES_ADMIN" -ForegroundColor Yellow
Write-Host "PostgreSQL Password: $POSTGRES_PASSWORD" -ForegroundColor Yellow

# Step 4: Configure PostgreSQL Firewall
Write-Host "`n[4/8] Configuring PostgreSQL Firewall" -ForegroundColor Green
az postgres server firewall-rule create `
  --resource-group $RESOURCE_GROUP `
  --server-name $POSTGRES_SERVER `
  --name AllowAzureServices `
  --start-ip-address 0.0.0.0 `
  --end-ip-address 0.0.0.0

# Step 5: Enable pgvector extension
Write-Host "`n[5/8] Enabling pgvector extension" -ForegroundColor Green
az postgres server configuration set `
  --resource-group $RESOURCE_GROUP `
  --server-name $POSTGRES_SERVER `
  --name azure.extensions `
  --value VECTOR

# Create database
az postgres db create `
  --resource-group $RESOURCE_GROUP `
  --server-name $POSTGRES_SERVER `
  --name $POSTGRES_DB

# Construct DATABASE_URL
$DATABASE_URL = "postgresql+asyncpg://${POSTGRES_ADMIN}@${POSTGRES_SERVER}:${POSTGRES_PASSWORD}@${POSTGRES_SERVER}.postgres.database.azure.com:5432/${POSTGRES_DB}?ssl=require"
Write-Host "DATABASE_URL: $DATABASE_URL" -ForegroundColor Yellow

# Step 6: Create Container Apps Environment
Write-Host "`n[6/8] Creating Container Apps Environment: $CONTAINER_APP_ENV" -ForegroundColor Green
az containerapp env create `
  --name $CONTAINER_APP_ENV `
  --resource-group $RESOURCE_GROUP `
  --location $LOCATION

# Step 7: Create Backend Container App
Write-Host "`n[7/8] Creating Backend Container App: $BACKEND_APP" -ForegroundColor Green
az containerapp create `
  --name $BACKEND_APP `
  --resource-group $RESOURCE_GROUP `
  --environment $CONTAINER_APP_ENV `
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest `
  --target-port 8000 `
  --ingress external `
  --registry-server "${ACR_NAME}.azurecr.io" `
  --registry-username $ACR_USERNAME `
  --registry-password $ACR_PASSWORD `
  --cpu 1.0 `
  --memory 2Gi `
  --min-replicas 1 `
  --max-replicas 3

# Step 8: Create Frontend Container App
Write-Host "`n[8/8] Creating Frontend Container App: $FRONTEND_APP" -ForegroundColor Green
az containerapp create `
  --name $FRONTEND_APP `
  --resource-group $RESOURCE_GROUP `
  --environment $CONTAINER_APP_ENV `
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest `
  --target-port 8501 `
  --ingress external `
  --registry-server "${ACR_NAME}.azurecr.io" `
  --registry-username $ACR_USERNAME `
  --registry-password $ACR_PASSWORD `
  --cpu 0.5 `
  --memory 1Gi `
  --min-replicas 1 `
  --max-replicas 2

# Summary
Write-Host "`n═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Blue
Write-Host "  Setup Complete!" -ForegroundColor Blue
Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Blue

Write-Host "`nResource Group: $RESOURCE_GROUP" -ForegroundColor Green
Write-Host "ACR: ${ACR_NAME}.azurecr.io" -ForegroundColor Green
Write-Host "PostgreSQL Server: ${POSTGRES_SERVER}.postgres.database.azure.com" -ForegroundColor Green
Write-Host "Backend App: https://${BACKEND_APP}.azurecontainerapps.io" -ForegroundColor Green
Write-Host "Frontend App: https://${FRONTEND_APP}.azurecontainerapps.io" -ForegroundColor Green

Write-Host "`nNext Steps:" -ForegroundColor Yellow
Write-Host "1. Add these GitHub Secrets:"
Write-Host "   - AZURE_CREDENTIALS (run: az ad sp create-for-rbac)"
Write-Host "   - ACR_USERNAME: $ACR_USERNAME"
Write-Host "   - ACR_PASSWORD: $ACR_PASSWORD"
Write-Host "   - DATABASE_URL: $DATABASE_URL"
Write-Host "   - GROQ_API_KEY: <your-groq-api-key>"
Write-Host "   - SECRET_KEY: <generate-random-string>"
Write-Host ""
Write-Host "2. Push code to GitHub main branch to trigger deployment"
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
