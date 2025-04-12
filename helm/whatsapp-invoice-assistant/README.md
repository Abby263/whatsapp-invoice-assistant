# WhatsApp Invoice Assistant Helm Chart

This Helm chart deploys the WhatsApp Invoice Assistant application on a Kubernetes cluster.

## Prerequisites

- Kubernetes 1.16+
- Helm 3.0+
- PV provisioner support in the underlying infrastructure (for persistent storage)

## Getting Started

### Add the Repository

```bash
# Add the Bitnami repository for the MongoDB and PostgreSQL dependencies
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

### Install the Chart

To install the chart with the release name `my-release`:

```bash
# First, create a values.yaml file to customize your deployment
# Ensure you set the required secrets like OPENAI_API_KEY

# Then install the chart
helm install my-release ./helm/whatsapp-invoice-assistant -f values.yaml
```

### Uninstall the Chart

To uninstall/delete the `my-release` deployment:

```bash
helm delete my-release
```

## Configuration

| Parameter                                 | Description                                                  | Default                                                      |
|-------------------------------------------|--------------------------------------------------------------|--------------------------------------------------------------|
| `replicaCount`                            | Number of replicas                                           | `1`                                                          |
| `image.repository`                        | Image repository                                             | `whatsapp-invoice-assistant`                                 |
| `image.tag`                               | Image tag                                                    | `latest`                                                     |
| `image.pullPolicy`                        | Image pull policy                                            | `IfNotPresent`                                               |
| `service.type`                            | Kubernetes Service type                                      | `ClusterIP`                                                  |
| `service.port`                            | Port for the service                                         | `5001`                                                       |
| `ingress.enabled`                         | Enable ingress                                               | `false`                                                      |
| `ingress.hosts[0].host`                   | Hostname for the ingress                                     | `chart-example.local`                                        |
| `resources.limits.cpu`                    | CPU limits                                                  | `1000m`                                                      |
| `resources.limits.memory`                 | Memory limits                                               | `1Gi`                                                       |
| `resources.requests.cpu`                  | CPU requests                                                | `500m`                                                       |
| `resources.requests.memory`               | Memory requests                                             | `512Mi`                                                     |
| `app.env.*`                               | Environment variables                                        | See values.yaml                                              |
| `app.secretEnv.*`                         | Secret environment variables                                 | See values.yaml                                              |
| `app.persistence.enabled`                 | Enable persistence                                           | `true`                                                       |
| `app.persistence.uploads.size`            | Size of the uploads volume                                   | `5Gi`                                                        |
| `app.persistence.logs.size`               | Size of the logs volume                                      | `1Gi`                                                        |
| `postgresql.enabled`                      | Deploy PostgreSQL                                            | `true`                                                       |
| `postgresql.auth.username`                | PostgreSQL username                                          | `postgres`                                                   |
| `postgresql.auth.password`                | PostgreSQL password                                          | `postgres`                                                   |
| `postgresql.auth.database`                | PostgreSQL database name                                     | `whatsapp_invoice_assistant`                                 |
| `mongodb.enabled`                         | Deploy MongoDB                                               | `true`                                                       |
| `mongodb.auth.enabled`                    | Enable MongoDB authentication                                | `true`                                                       |
| `mongodb.auth.rootPassword`               | MongoDB root password                                        | `password`                                                   |
| `mongodb.auth.username`                   | MongoDB username                                             | `whatsapp_invoice_assistant`                                 |
| `mongodb.auth.password`                   | MongoDB password                                             | `password`                                                   |
| `mongodb.auth.database`                   | MongoDB database name                                        | `whatsapp_invoice_assistant`                                 |

## Memory Management Configuration

The Helm chart includes configuration options for MongoDB memory management:

```yaml
memory:
  expirationHours: 72  # Conversation expiration in hours
  maxConversations: 1000  # Maximum number of conversations to keep
  cleanupSchedule: "0 0 * * *"  # Daily cleanup at midnight
```

## Production Deployment

For production deployments, ensure you:

1. Set proper resource limits and requests
2. Use strong passwords for databases
3. Configure proper ingress with TLS
4. Set up proper persistent storage
5. Configure all required API keys through secrets

Example production values file:

```yaml
# production-values.yaml
replicaCount: 2

resources:
  limits:
    cpu: 2000m
    memory: 2Gi
  requests:
    cpu: 1000m
    memory: 1Gi

ingress:
  enabled: true
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: whatsapp-assistant.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: whatsapp-assistant-tls
      hosts:
        - whatsapp-assistant.example.com

app:
  persistence:
    uploads:
      size: 20Gi
      storageClass: "managed-premium"
    logs:
      size: 5Gi
      storageClass: "managed-premium"

postgresql:
  primary:
    persistence:
      size: 20Gi
      storageClass: "managed-premium"

mongodb:
  persistence:
    size: 20Gi
    storageClass: "managed-premium"
```

Apply the production configuration:

```bash
helm install whatsapp-assistant ./helm/whatsapp-invoice-assistant -f production-values.yaml
``` 