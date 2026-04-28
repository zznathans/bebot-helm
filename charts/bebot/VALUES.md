# bebot

helm chart for bebot

**Version:** 1.0.8

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| bebot.extraObjects | list | `[]` | Raw Kubernetes objects to render alongside chart-managed resources. Useful for ExternalSecrets, NetworkPolicies, or other objects not covered by chart values. |
| bebot.imagePullSecrets | list | `[]` | List of image pull secret names to attach to the ServiceAccount. Leave empty if the registry is public. |
| bebot.imageRepository | string | `"ghcr.io/zznathans/bebot-helm"` | Container image registry and repository for the bebot image. |
| bebot.imageTag | string | `"1.0.8"` | Image tag to deploy. Use a specific digest or tag in production for reproducibility. |
| bebot.instances[0].ao_username | string | `"ao_account"` |  |
| bebot.instances[0].botOwner | string | `"OwnerCharacter"` |  |
| bebot.instances[0].bot_name | string | `"BotCharacter"` |  |
| bebot.instances[0].createSecret | bool | `true` |  |
| bebot.instances[0].dimension | string | `"5"` |  |
| bebot.instances[0].enabled | bool | `true` |  |
| bebot.instances[0].guildId | int | `0` |  |
| bebot.instances[0].mariadbDatabase | string | `"botdb"` |  |
| bebot.instances[0].mariadbUser | string | `"botuser"` |  |
| bebot.instances[0].name | string | `"mybot"` |  |
| bebot.instances[0].raidbot | bool | `false` |  |
| bebot.instances[0].superAdmins[0] | string | `"AdminCharacter"` |  |
| bebot.mariadb.backup.destination | string | `"pvc"` | Where to send backups: `pvc` stores dumps on a PersistentVolumeClaim, `s3` dumps to an emptyDir then uploads to an S3-compatible bucket. |
| bebot.mariadb.backup.enabled | bool | `false` | Enable a CronJob to periodically dump each database to SQL files. |
| bebot.mariadb.backup.pvc.accessMode | string | `"ReadWriteOnce"` | Access mode for the backup PVC. |
| bebot.mariadb.backup.pvc.size | string | `"5Gi"` | Size of the PVC used to store backup dumps. |
| bebot.mariadb.backup.pvc.storageClass | string | `""` | StorageClass for the backup PVC. Leave empty to use the cluster default. |
| bebot.mariadb.backup.s3.bucket | string | `""` | S3 bucket name to upload dumps to. |
| bebot.mariadb.backup.s3.credentialsSecret | string | `""` | Name of the K8s Secret containing AWS credentials (keys: access-key-id, secret-access-key). This secret can be created manually or managed by the externalSecret block below. |
| bebot.mariadb.backup.s3.endpoint | string | `""` | Optional: override endpoint URL for non-AWS providers (MinIO, Backblaze B2, etc.). |
| bebot.mariadb.backup.s3.externalSecret.enabled | bool | `false` | When true, create an ExternalSecret to populate credentialsSecret from an external store. When false (default), the secret named by credentialsSecret must already exist. |
| bebot.mariadb.backup.s3.image | string | `"amazon/aws-cli:2"` | Container image used to perform the S3 upload. Must have the aws CLI available. |
| bebot.mariadb.backup.s3.path | string | `"backups/bebot"` | Key prefix/path within the bucket where dumps are written. |
| bebot.mariadb.backup.s3.region | string | `"us-east-1"` | AWS region (or region of your S3-compatible provider). |
| bebot.mariadb.backup.schedule | string | `"0 2 * * *"` | Cron schedule for the backup job (default: 2am daily). |
| bebot.mariadb.dbSetupEnabled | bool | `true` | Run the db-setup job to create per-instance databases and users on first deploy. Disable if managing database setup externally. |
| bebot.mariadb.enabled | bool | `true` | Deploy a MariaDB instance as part of this chart. Set to false to use an external/managed database. |
| bebot.mariadb.metrics.enabled | bool | `false` | Deploy a prom/mysqld_exporter sidecar and expose metrics on port 9104. |
| bebot.mariadb.metrics.grafanaDashboard.enabled | bool | `false` | Create a ConfigMap containing the MySQL Overview dashboard for Grafana's sidecar to load. Requires `grafana.sidecar.dashboards.enabled=true` in your Grafana Helm deployment. |
| bebot.mariadb.metrics.grafanaDashboard.label | string | `"grafana_dashboard"` | Label the Grafana sidecar uses to discover dashboard ConfigMaps. |
| bebot.mariadb.metrics.image | string | `"prom/mysqld-exporter:v0.16.0"` | Container image for the mysqld_exporter sidecar. |
| bebot.mariadb.perInstance | bool | `false` | When true, create a separate MariaDB deployment and PVC per bot instance. When false, use a single shared MariaDB. |
| bebot.mariadb.persistence.accessMode | string | `"ReadWriteOnce"` | Access mode for the PVC. RWO is required for most block storage backends. |
| bebot.mariadb.persistence.enabled | bool | `true` | Enable persistent storage for MariaDB data. If false, data is lost on pod restart. |
| bebot.mariadb.persistence.size | string | `"1Gi"` | Size of the PersistentVolumeClaim for MariaDB data. |
| bebot.mariadb.persistence.storageClass | string | `""` | StorageClass to use for the PVC. Leave empty to use the cluster default. |
| bebot.mariadb.rootHost | string | `"%"` | Host mask for the root user grant (% = allow from any host). |
| bebot.mariadb.rootUser | string | `"root"` | MySQL root user name to create. |
| bebot.resources | object | `{"limits":{"cpu":"500m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"128Mi"}}` | Resource requests and limits for the bot container. Tune based on bot module load and guild activity. |
