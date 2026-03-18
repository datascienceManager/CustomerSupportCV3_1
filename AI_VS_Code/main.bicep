// ─────────────────────────────────────────────────────────────────────────────
// azure/main.bicep
// Provisions all Azure resources for the AI Voice Agent
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

@description('Container image (e.g. myregistry.azurecr.io/ai-voice-agent:latest)')
param containerImage string

@description('Anthropic API key')
@secure()
param anthropicApiKey string

@description('OpenAI API key')
@secure()
param openaiApiKey string

@description('SendGrid API key')
@secure()
param sendgridApiKey string

@description('Product department email')
param productEmail string

@description('Payment department email')
param paymentEmail string

// ── Variables ─────────────────────────────────────────────────────────────────

var acrName   = replace('${appName}acr', '-', '')
var kvName    = '${appName}-kv'
var logName   = '${appName}-logs'
var appEnvName = '${appName}-env'
var appFqdn   = '${appName}-app'

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

resource kvSecretAnthropic 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: kv
  name: 'ANTHROPIC-API-KEY'
  properties: { value: anthropicApiKey }
}

resource kvSecretOpenAI 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
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

// ── Container App ─────────────────────────────────────────────────────────────

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: appFqdn
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: appEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8501
        transport: 'auto'
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'OPTIONS']
          allowedHeaders: ['*']
        }
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'ai-voice-agent'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'APP_ENV',            value: 'production' }
            { name: 'DB_TYPE',            value: 'sqlite' }
            { name: 'SQLITE_DB_PATH',     value: '/app/data/queries.db' }
            { name: 'PRODUCT_DEPT_EMAIL', value: productEmail }
            { name: 'PAYMENT_DEPT_EMAIL', value: paymentEmail }
            { name: 'ANTHROPIC_API_KEY',  secretRef: 'anthropic-key' }
            { name: 'OPENAI_API_KEY',     secretRef: 'openai-key' }
            { name: 'SENDGRID_API_KEY',   secretRef: 'sendgrid-key' }
          ]
          volumeMounts: [
            {
              volumeName: 'data-volume'
              mountPath: '/app/data'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling'
            http: { metadata: { concurrentRequests: '20' } }
          }
        ]
      }
      volumes: [
        {
          name: 'data-volume'
          storageType: 'EmptyDir'
        }
      ]
    }
  }
}

// ── Key Vault Role Assignment for Container App ───────────────────────────────

resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, containerApp.id, 'KeyVaultSecretsUser')
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6'  // Key Vault Secrets User
    )
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output appUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output acrLoginServer string = acr.properties.loginServer
output keyVaultName string = kv.name
