// ─────────────────────────────────────────────────────────────────────────────
// azure/main.bicep  —  AI Voice Agent (Ollama edition)
//
// Provisions:
//   • Azure Container Registry (ACR)
//   • Azure Container Apps Environment
//   • Container App: Streamlit app + Ollama sidecar
//   • Azure Key Vault (secrets)
//   • Log Analytics workspace
//
// Deploy:
//   az deployment group create \
//     --resource-group ai-voice-agent-rg \
//     --template-file azure/main.bicep \
//     --parameters @azure/parameters.json
// ─────────────────────────────────────────────────────────────────────────────

@description('Base name used for all resources')
param appName string = 'ai-voice-agent'

@description('Azure region')
param location string = resourceGroup().location

@description('Streamlit app container image')
param containerImage string

@description('Ollama model to use, e.g. llama3.2')
param ollamaModel string = 'llama3.2'

@description('OpenAI API key (optional — for Whisper STT only)')
@secure()
param openaiApiKey string = ''

@description('SendGrid API key')
@secure()
param sendgridApiKey string

@description('Product department email')
param productEmail string

@description('Payment department email')
param paymentEmail string

// ── Variables ─────────────────────────────────────────────────────────────────
var acrName    = replace('${appName}acr', '-', '')
var kvName     = '${appName}-kv'
var logName    = '${appName}-logs'
var appEnvName = '${appName}-env'
var appFqdn    = '${appName}-app'

// ── Azure Container Registry ──────────────────────────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: true }
}

// ── Key Vault ─────────────────────────────────────────────────────────────────
resource kv 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: kvName
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    softDeleteRetentionInDays: 7
  }
}

resource kvSecretOpenAI 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = if (!empty(openaiApiKey)) {
  parent: kv
  name: 'OPENAI-API-KEY'
  properties: { value: openaiApiKey }
}

resource kvSecretSendGrid 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: kv
  name: 'SENDGRID-API-KEY'
  properties: { value: sendgridApiKey }
}

// ── Log Analytics ─────────────────────────────────────────────────────────────
resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ── Container Apps Environment ────────────────────────────────────────────────
resource appEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: appEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logWorkspace.properties.customerId
        sharedKey: logWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

// ── Container App (Streamlit + Ollama sidecar) ────────────────────────────────
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: appFqdn
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: appEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8501
        transport: 'auto'
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password',   value: acr.listCredentials().passwords[0].value }
        { name: 'sendgrid-key',   value: sendgridApiKey }
        { name: 'openai-key',     value: empty(openaiApiKey) ? 'not-set' : openaiApiKey }
      ]
    }
    template: {
      containers: [

        // ── Ollama sidecar ─────────────────────────────────────────────────
        {
          name: 'ollama'
          image: 'ollama/ollama:latest'
          resources: {
            cpu: json('1.0')
            memory: '4Gi'
          }
          env: [
            { name: 'OLLAMA_KEEP_ALIVE', value: '24h' }
          ]
          volumeMounts: [
            { volumeName: 'ollama-models', mountPath: '/root/.ollama' }
          ]
        }

        // ── Streamlit app ──────────────────────────────────────────────────
        {
          name: 'ai-voice-agent'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'APP_ENV',            value: 'production' }
            { name: 'OLLAMA_BASE_URL',    value: 'http://localhost:11434' }  // sidecar shares localhost
            { name: 'OLLAMA_MODEL',       value: ollamaModel }
            { name: 'OLLAMA_TIMEOUT',     value: '180' }
            { name: 'DB_TYPE',            value: 'sqlite' }
            { name: 'SQLITE_DB_PATH',     value: '/app/data/queries.db' }
            { name: 'PRODUCT_DEPT_EMAIL', value: productEmail }
            { name: 'PAYMENT_DEPT_EMAIL', value: paymentEmail }
            { name: 'SENDGRID_API_KEY',   secretRef: 'sendgrid-key' }
            { name: 'OPENAI_API_KEY',     secretRef: 'openai-key' }
          ]
          volumeMounts: [
            { volumeName: 'data-volume', mountPath: '/app/data' }
          ]
        }
      ]

      scale: {
        minReplicas: 1
        maxReplicas: 2
        rules: [
          {
            name: 'http-scaling'
            http: { metadata: { concurrentRequests: '10' } }
          }
        ]
      }

      volumes: [
        { name: 'data-volume',    storageType: 'EmptyDir' }
        { name: 'ollama-models',  storageType: 'EmptyDir' }
      ]
    }
  }
}

// ── Key Vault RBAC for Container App ─────────────────────────────────────────
resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, containerApp.id, 'KeyVaultSecretsUser')
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6'
    )
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────
output appUrl        string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output acrLoginServer string = acr.properties.loginServer
output keyVaultName  string = kv.name
