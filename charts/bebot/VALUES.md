# bebot

Helm chart for bebot

**Version:** 3.0.0

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| bebot.externalSecret | object | `{"gcpSecretName":"","secretRefreshInterval":"1h","secretStoreKind":"ClusterSecretStore","secretStoreName":"gcp-clusterstore"}` | Configuration for the single upstream external secret used by all ExternalSecret resources in this chart. All ExternalSecrets reference this one GCP/external secret, which must be a JSON object with a key per credential. Required keys: <instance-name>_ao_password, <instance-name>_mariadb_user, <instance-name>_mariadb_password, <instance-name>_mariadb_database (per instance); mariadb_root_password, mariadb_root_user (shared). |
| bebot.externalSecret.gcpSecretName | string | `""` | Name of the upstream secret in the external store (required when any resource uses createSecret: false). |
| bebot.externalSecret.secretRefreshInterval | string | `"1h"` | How often ExternalSecrets poll for updates. |
| bebot.externalSecret.secretStoreKind | string | `"ClusterSecretStore"` | Kind of the secret store (ClusterSecretStore or SecretStore). |
| bebot.externalSecret.secretStoreName | string | `"gcp-clusterstore"` | Name of the ClusterSecretStore or SecretStore to use. |
| bebot.extraObjects | list | `[]` | Raw Kubernetes objects to render alongside chart-managed resources. Useful for ExternalSecrets, NetworkPolicies, or other objects not covered by chart values. |
| bebot.imagePullSecrets | list | `[]` | List of image pull secret names to attach to the ServiceAccount. Leave empty if the registry is public. |
| bebot.imageRepository | string | `"ghcr.io/zznathans/bebot"` | Container image registry and repository for the bebot image. |
| bebot.imageTag | string | `"2.0.2"` | Image tag to deploy. Use a specific digest or tag in production for reproducibility. |
| bebot.instances[0].ao_username | string | `"ao_account"` |  |
| bebot.instances[0].botOwner | string | `"OwnerCharacter"` |  |
| bebot.instances[0].bot_name | string | `"BotCharacter"` |  |
| bebot.instances[0].createSecret | bool | `true` |  |
| bebot.instances[0].dimension | string | `"5"` |  |
| bebot.instances[0].enabled | bool | `true` |  |
| bebot.instances[0].guildId | int | `0` |  |
| bebot.instances[0].log | string | `"chat"` |  |
| bebot.instances[0].logConsoleFormat | string | `"plain"` |  |
| bebot.instances[0].logFileFormat | string | `"plain"` |  |
| bebot.instances[0].logPath | string | `"./log"` |  |
| bebot.instances[0].logSecurityFormat | string | `"plain"` |  |
| bebot.instances[0].logTimestamp | string | `"none"` |  |
| bebot.instances[0].mariadbDatabase | string | `"botdb"` |  |
| bebot.instances[0].mariadbUser | string | `"botuser"` |  |
| bebot.instances[0].name | string | `"mybot"` |  |
| bebot.instances[0].raidbot | bool | `false` |  |
| bebot.instances[0].superAdmins[0] | string | `"AdminCharacter"` |  |
| bebot.mariadb.enabled | bool | `true` | this to false and point each instance at it with mariadbHost. |
| bebot.mariadb.image | string | `"mariadb:11.4"` | Container image for MariaDB. |
| bebot.mariadb.persistence.size | string | `"1Gi"` | Size of the MariaDB data PVC. |
| bebot.mariadb.persistence.storageClass | string | `""` | StorageClass to use for the PVC. Leave empty to use the cluster default. |
| bebot.mariadb.resources | object | `{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"50m","memory":"256Mi"}}` | Resource requests and limits for the MariaDB container. |
| bebot.redis | object | `{"enabled":false,"image":"quay.io/opstree/redis:v7.0.15","metrics":{"enabled":false,"image":""},"persistence":{"enabled":true,"size":"1Gi","storageClass":""},"resources":{"limits":{"cpu":"200m","memory":"128Mi"},"requests":{"cpu":"50m","memory":"64Mi"}}}` | to install it regardless of bebot.redis.enabled. enabled: true |
| bebot.redis.enabled | bool | `false` | present in the cluster (see bebot.redisOperator.enabled). |
| bebot.redis.image | string | `"quay.io/opstree/redis:v7.0.15"` | Container image for Redis, passed through to the Redis CR. |
| bebot.redis.metrics.enabled | bool | `false` | Enable the redis-operator's built-in Prometheus exporter sidecar. |
| bebot.redis.metrics.image | string | `""` | Container image for the redis-exporter sidecar. Leave empty to use the operator's default. |
| bebot.redis.persistence.enabled | bool | `true` | on pod restart since nothing but the DB fallback depends on it. |
| bebot.redis.persistence.size | string | `"1Gi"` | Size of the Redis CR's storage volume. |
| bebot.redis.persistence.storageClass | string | `""` | StorageClass to use for the volume. Leave empty to use the cluster default. |
| bebot.redis.resources | object | `{"limits":{"cpu":"200m","memory":"128Mi"},"requests":{"cpu":"50m","memory":"64Mi"}}` | Resource requests and limits for the Redis CR's pod. |
| bebot.redisOperator | string | `nil` |  |
| bebot.resources | object | `{"limits":{"cpu":"500m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits for the bot container. Tune based on bot module load and guild activity. |
| bebot.terminationGracePeriodSeconds | int | `60` | Seconds Kubernetes waits for the bot to exit after SIGTERM before sending SIGKILL. Should be long enough for the bot to disconnect from AO servers cleanly. |
