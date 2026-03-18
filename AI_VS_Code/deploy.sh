#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# azure/deploy.sh
# One-shot Azure deployment script for the AI Voice Agent
# Prerequisites: Azure CLI installed & logged in (az login)
# Usage: bash azure/deploy.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Config — edit these ────────────────────────────────────────────────────────
APP_NAME="ai-voice-agent"
RESOURCE_GROUP="${APP_NAME}-rg"
LOCATION="eastus"
ACR_NAME="${APP_NAME//-/}acr"      # No hyphens allowed in ACR names
IMAGE_TAG="latest"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║       AI Voice Agent — Azure Deployment Script           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Ensure resource group ──────────────────────────────────────────────────
echo "📦 Creating resource group: $RESOURCE_GROUP in $LOCATION..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# ── 2. Create Container Registry ─────────────────────────────────────────────
echo "🐳 Creating Azure Container Registry: $ACR_NAME..."
az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true \
  --output none

ACR_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
echo "   ACR: $ACR_SERVER"

# ── 3. Build & push Docker image ─────────────────────────────────────────────
echo "🔨 Building and pushing Docker image..."
az acr build \
  --registry "$ACR_NAME" \
  --image "${APP_NAME}:${IMAGE_TAG}" \
  --file Dockerfile \
  . \
  --output none

FULL_IMAGE="${ACR_SERVER}/${APP_NAME}:${IMAGE_TAG}"
echo "   Image: $FULL_IMAGE"

# ── 4. Collect secrets ────────────────────────────────────────────────────────
echo ""
echo "🔑 Enter API keys (input is hidden):"
read -rsp "   Anthropic API Key: " ANTHROPIC_KEY; echo
read -rsp "   OpenAI API Key (for STT — press Enter to skip): " OPENAI_KEY; echo
read -rsp "   SendGrid API Key (for email — press Enter to skip): " SENDGRID_KEY; echo
read -rp  "   Product dept email: " PRODUCT_EMAIL
read -rp  "   Payment dept email: " PAYMENT_EMAIL

# ── 5. Deploy Bicep template ──────────────────────────────────────────────────
echo ""
echo "☁️  Deploying infrastructure via Bicep..."
DEPLOY_OUTPUT=$(az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file azure/main.bicep \
  --parameters \
      appName="$APP_NAME" \
      location="$LOCATION" \
      containerImage="$FULL_IMAGE" \
      anthropicApiKey="$ANTHROPIC_KEY" \
      openaiApiKey="${OPENAI_KEY:-placeholder}" \
      sendgridApiKey="${SENDGRID_KEY:-placeholder}" \
      productEmail="$PRODUCT_EMAIL" \
      paymentEmail="$PAYMENT_EMAIL" \
  --output json)

APP_URL=$(echo "$DEPLOY_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['properties']['outputs']['appUrl']['value'])" 2>/dev/null || echo "")

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                  ✅ Deployment Complete!                  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
if [ -n "$APP_URL" ]; then
  echo "  🌐 App URL: $APP_URL"
fi
echo "  📦 Resource Group: $RESOURCE_GROUP"
echo "  🐳 Image: $FULL_IMAGE"
echo ""
echo "  Next steps:"
echo "  1. Open the app URL above in your browser"
echo "  2. Configure Google Sheets credentials in azure/config/"
echo "  3. Set up GitHub Actions secrets for CI/CD (see README.md)"
echo ""
