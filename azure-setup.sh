#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# MedInsight Azure Infrastructure Setup Script
# ═══════════════════════════════════════════════════════════════════════════════
# Prerequisites:
# - Azure CLI installed: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli
# - Logged in to Azure: az login
# ═══════════════════════════════════════════════════════════════════════════════

set -e  # Exit on error

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration Variables
# ═══════════════════════════════════════════════════════════════════════════════
RESOURCE_GROUP="medinsight-rg"
LOCATION="eastus"
ACR_NAME="medinsightacr"
POSTGRES_SERVER="medinsight-postgres-server"
POSTGRES_DB="medinsight"
POSTGRES_ADMIN="medinsightadmin"
POSTGRES_SKU="B_Gen5_1"  # Basic tier (for dev), upgrade to GP_Gen5_2 for production
CONTAINER_APP_ENV="medinsight-env"
BACKEND_APP="medinsight-backend-app"
FRONTEND_APP="medinsight-frontend-app"

# ═══════════════════════════════════════════════════════════════════════════════
# Color codes for output
# ═══════════════════════════════════════════════════════════════════════════════
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  MedInsight Azure Infrastructure Setup${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════${NC}"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 1: Create Resource Group
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[1/8] Creating Resource Group: ${RESOURCE_GROUP}${NC}"
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

# ═══════════════════════════════════════════════════════════════════════════════
# Step 2: Create Azure Container Registry (ACR)
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[2/8] Creating Azure Container Registry: ${ACR_NAME}${NC}"
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true

# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query "username" -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

echo -e "${YELLOW}ACR Username: ${ACR_USERNAME}${NC}"
echo -e "${YELLOW}ACR Password: ${ACR_PASSWORD}${NC}"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 3: Create Azure Database for PostgreSQL
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[3/8] Creating Azure Database for PostgreSQL: ${POSTGRES_SERVER}${NC}"

# Generate random password
POSTGRES_PASSWORD=$(openssl rand -base64 32)

az postgres server create \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER \
  --location $LOCATION \
  --admin-user $POSTGRES_ADMIN \
  --admin-password "$POSTGRES_PASSWORD" \
  --sku-name $POSTGRES_SKU \
  --version 14 \
  --ssl-enforcement Enabled

echo -e "${YELLOW}PostgreSQL Admin: ${POSTGRES_ADMIN}${NC}"
echo -e "${YELLOW}PostgreSQL Password: ${POSTGRES_PASSWORD}${NC}"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 4: Configure PostgreSQL Firewall (Allow Azure Services)
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[4/8] Configuring PostgreSQL Firewall${NC}"
az postgres server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --server-name $POSTGRES_SERVER \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

# ═══════════════════════════════════════════════════════════════════════════════
# Step 5: Enable pgvector extension
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[5/8] Enabling pgvector extension${NC}"
az postgres server configuration set \
  --resource-group $RESOURCE_GROUP \
  --server-name $POSTGRES_SERVER \
  --name azure.extensions \
  --value VECTOR

# Create database
az postgres db create \
  --resource-group $RESOURCE_GROUP \
  --server-name $POSTGRES_SERVER \
  --name $POSTGRES_DB

# Construct DATABASE_URL
DATABASE_URL="postgresql+asyncpg://${POSTGRES_ADMIN}@${POSTGRES_SERVER}:${POSTGRES_PASSWORD}@${POSTGRES_SERVER}.postgres.database.azure.com:5432/${POSTGRES_DB}?ssl=require"

echo -e "${YELLOW}DATABASE_URL: ${DATABASE_URL}${NC}"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 6: Create Container Apps Environment
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[6/8] Creating Container Apps Environment: ${CONTAINER_APP_ENV}${NC}"
az containerapp env create \
  --name $CONTAINER_APP_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# ═══════════════════════════════════════════════════════════════════════════════
# Step 7: Create Backend Container App
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[7/8] Creating Backend Container App: ${BACKEND_APP}${NC}"

# Note: You'll need to build and push images first, then update this command
# For initial setup, we'll create with a placeholder image
az containerapp create \
  --name $BACKEND_APP \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_ENV \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --target-port 8000 \
  --ingress external \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --cpu 1.0 \
  --memory 2Gi \
  --min-replicas 1 \
  --max-replicas 3

echo -e "${YELLOW}Backend will be deployed via GitHub Actions workflow${NC}"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 8: Create Frontend Container App
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[8/8] Creating Frontend Container App: ${FRONTEND_APP}${NC}"

az containerapp create \
  --name $FRONTEND_APP \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_ENV \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --target-port 8501 \
  --ingress external \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 2

echo -e "${YELLOW}Frontend will be deployed via GitHub Actions workflow${NC}"

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${BLUE}═══════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Setup Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════${NC}"

echo -e "\n${GREEN}Resource Group:${NC} $RESOURCE_GROUP"
echo -e "${GREEN}ACR:${NC} ${ACR_NAME}.azurecr.io"
echo -e "${GREEN}PostgreSQL Server:${NC} ${POSTGRES_SERVER}.postgres.database.azure.com"
echo -e "${GREEN}Backend App:${NC} https://${BACKEND_APP}.azurecontainerapps.io"
echo -e "${GREEN}Frontend App:${NC} https://${FRONTEND_APP}.azurecontainerapps.io"

echo -e "\n${YELLOW}Next Steps:${NC}"
echo -e "1. Add these GitHub Secrets:"
echo -e "   - AZURE_CREDENTIALS (from: az ad sp create-for-rbac)"
echo -e "   - ACR_USERNAME: ${ACR_USERNAME}"
echo -e "   - ACR_PASSWORD: ${ACR_PASSWORD}"
echo -e "   - DATABASE_URL: ${DATABASE_URL}"
echo -e "   - GROQ_API_KEY: <your-groq-api-key>"
echo -e "   - SECRET_KEY: <generate-with-openssl-rand-base64-32>"
echo -e ""
echo -e "2. Push code to GitHub main branch to trigger deployment"
echo -e ""
echo -e "3. Monitor deployment: https://github.com/<your-repo>/actions"
echo -e ""
echo -e "${GREEN}Done!${NC}"
