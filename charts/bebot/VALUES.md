# bebot

Helm chart for bebot

**Version:** 2.28.7

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| bebot.externalSecret | object | `{"gcpSecretName":"","secretRefreshInterval":"1h","secretStoreKind":"ClusterSecretStore","secretStoreName":"gcp-clusterstore"}` | Configuration for the single upstream external secret used by all ExternalSecret resources in this chart. All ExternalSecrets reference this one GCP/external secret, which must be a JSON object with a key per credential. Required keys: <instance-name>_ao_password, <instance-name>_mariadb_user, <instance-name>_mariadb_password, <instance-name>_mariadb_database (per instance); mariadb_root_password, mariadb_root_user (shared); s3_access_key, s3_secret_key (if using S3 backup with externalSecret.enabled). |
| bebot.externalSecret.gcpSecretName | string | `""` | Name of the upstream secret in the external store (required when any resource uses createSecret: false). |
| bebot.externalSecret.secretRefreshInterval | string | `"1h"` | How often ExternalSecrets poll for updates. |
| bebot.externalSecret.secretStoreKind | string | `"ClusterSecretStore"` | Kind of the secret store (ClusterSecretStore or SecretStore). |
| bebot.externalSecret.secretStoreName | string | `"gcp-clusterstore"` | Name of the ClusterSecretStore or SecretStore to use. |
| bebot.extraObjects | list | `[]` | Raw Kubernetes objects to render alongside chart-managed resources. Useful for ExternalSecrets, NetworkPolicies, or other objects not covered by chart values. |
| bebot.imagePullSecrets | list | `[]` | List of image pull secret names to attach to the ServiceAccount. Leave empty if the registry is public. |
| bebot.imageRepository | string | `"ghcr.io/zznathans/bebot"` | Container image registry and repository for the bebot image. |
| bebot.imageTag | string | `"1.6.3"` | Image tag to deploy. Use a specific digest or tag in production for reproducibility. |
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
| bebot.mariadb | object | `{"backup":{"destination":"pvc","enabled":false,"maxRetention":"720h","pvc":{"accessMode":"ReadWriteOnce","size":"5Gi","storageClass":""},"s3":{"bucket":"","credentialsSecret":"","endpoint":"","externalSecret":{"enabled":false,"secretName":""},"path":"backups/bebot","region":"us-east-1","tls":true},"schedule":"0 2 * * *"},"bootstrapFrom":{"enabled":false,"targetRecoveryTime":""},"enabled":true,"image":"mariadb:11.4","metrics":{"enabled":false,"grafanaDashboard":{"enabled":false,"label":"grafana_dashboard"},"image":""},"persistence":{"enabled":true,"size":"1Gi","storageClass":""},"restore":{"enabled":false,"targetRecoveryTime":""},"rootHost":"%","rootUser":"root"}` | regardless of bebot.mariadb.enabled. enabled: true |
| bebot.mariadb.backup.destination | string | `"pvc"` | Where to send backups: `pvc` stores dumps on a PersistentVolumeClaim, `s3` uploads to an S3-compatible bucket. |
| bebot.mariadb.backup.enabled | bool | `false` | Enable a mariadb-operator Backup CR to periodically dump each database. |
| bebot.mariadb.backup.maxRetention | string | `"720h"` | How long to retain backups for, as a Go duration string (e.g. "720h" = 30 days). |
| bebot.mariadb.backup.pvc.accessMode | string | `"ReadWriteOnce"` | Access mode for the backup PVC. |
| bebot.mariadb.backup.pvc.size | string | `"5Gi"` | Size of the PVC used to store backup dumps. |
| bebot.mariadb.backup.pvc.storageClass | string | `""` | StorageClass for the backup PVC. Leave empty to use the cluster default. |
| bebot.mariadb.backup.s3.bucket | unlike the credentials below | `""` | ; set it here even when s3.externalSecret.enabled is true. |
| bebot.mariadb.backup.s3.credentialsSecret | string | `""` | Name of the K8s Secret containing AWS credentials (keys: access-key-id, secret-access-key). This secret can be created manually or managed by the externalSecret block below. |
| bebot.mariadb.backup.s3.endpoint | string | `""` | external secret (the CRD field has no secretKeyRef) - set it directly even with s3.externalSecret.enabled. |
| bebot.mariadb.backup.s3.externalSecret.enabled | bool | `false` | the secret named by credentialsSecret must already exist. |
| bebot.mariadb.backup.s3.externalSecret.secretName | string | `""` | Name of the secret in the external store to pull S3 credentials from. Required when enabled is true. The secret must be a JSON object with keys: bucket_name, endpoint, access_key (base64), secret_key (base64). bucket_name/endpoint in this payload are unused by this chart now (see bucket/endpoint above) but are kept in the schema for compatibility with existing populated secrets. |
| bebot.mariadb.backup.s3.path | string | `"backups/bebot"` | Key prefix/path within the bucket where dumps are written. |
| bebot.mariadb.backup.s3.region | string | `"us-east-1"` | AWS region (or region of your S3-compatible provider). |
| bebot.mariadb.backup.s3.tls | bool | `true` | reject with a "301 Moved Permanently" redirect rather than actually serving the request. |
| bebot.mariadb.backup.schedule | string | `"0 2 * * *"` | Cron schedule for the backup (default: 2am daily). |
| bebot.mariadb.bootstrapFrom.enabled | bool | `false` | Requires bebot.mariadb.backup.enabled. Has no effect on an already-existing instance. |
| bebot.mariadb.bootstrapFrom.targetRecoveryTime | string | `""` | Optional: bootstrap from a specific point in time (RFC3339) instead of the latest backup. |
| bebot.mariadb.enabled | bool | `true` | to already be present in the cluster (see bebot.mariadbOperator.enabled). |
| bebot.mariadb.image | string | `"mariadb:11.4"` | Container image for MariaDB, passed through to the MariaDB CR. |
| bebot.mariadb.metrics.enabled | bool | `false` | Enable the MariaDB CR's built-in Prometheus exporter (spec.metrics.enabled) and expose metrics on port 9104. |
| bebot.mariadb.metrics.grafanaDashboard.enabled | bool | `false` | Create a ConfigMap containing the MySQL Overview dashboard for Grafana's sidecar to load. Requires `grafana.sidecar.dashboards.enabled=true` in your Grafana Helm deployment. |
| bebot.mariadb.metrics.grafanaDashboard.label | string | `"grafana_dashboard"` | Label the Grafana sidecar uses to discover dashboard ConfigMaps. |
| bebot.mariadb.metrics.image | string | `""` | Container image for the operator-managed mysqld_exporter. Leave empty to use the operator's default. |
| bebot.mariadb.persistence.enabled | bool | `true` | Enable persistent storage for MariaDB data. If false, the MariaDB CR uses ephemeral storage and data is lost on pod restart. |
| bebot.mariadb.persistence.size | string | `"1Gi"` | Size of the MariaDB CR's storage volume. |
| bebot.mariadb.persistence.storageClass | string | `""` | StorageClass to use for the volume. Leave empty to use the cluster default. |
| bebot.mariadb.restore.enabled | bool | `false` | Requires bebot.mariadb.backup.enabled so there's a Backup CR to restore from. |
| bebot.mariadb.restore.targetRecoveryTime | string | `""` | Optional: restore from a specific point in time (RFC3339, e.g. "2023-12-19T09:00:00Z") instead of the latest backup. |
| bebot.mariadb.rootHost | string | `"%"` | Host mask for the root user grant (% = allow from any host). |
| bebot.mariadb.rootUser | string | `"root"` | authenticates its root user as literally "root", so this is not actually configurable. |
| bebot.mariadbOperator | string | `nil` |  |
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
