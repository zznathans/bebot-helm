# ao-bebot Helm Chart

Helm chart for deploying [BeBot](https://github.com/J-Soft/BeBot) (an Anarchy Online IRC bot) on Kubernetes, with optional in-cluster MariaDB, automated backups, and full ExternalSecret support for credential management.

---

## Features

- Deploy one or more bot instances from a single chart
- Optional in-cluster MariaDB (shared or per-instance)
- Credentials via direct Helm Secrets or GCP Secret Manager (ExternalSecrets)
- S3-compatible or PVC-based database backups
- NetworkPolicy to isolate MariaDB access
- Checksum-based pod rollouts when config or secrets change

---

## Prerequisites

- Helm 3
- Kubernetes 1.25+
- [external-secrets operator](https://external-secrets.io) (only if using `createSecret: false`)

---

## Quick Start

```bash
# 1. Add the Helm repository
helm repo add bebot https://zznathans.github.io/bebot-helm
helm repo update

# 2. Install the chart
helm install my-bebot bebot/bebot -f my-values.yaml
```

---

## Values Reference

### `bebot.mariadb`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Deploy an in-cluster MariaDB. Set `false` to use an external database. |
| `perInstance` | bool | `false` | Create a separate MariaDB deployment per bot instance. |
| `persistence.enabled` | bool | `true` | Enable a PVC for MariaDB data. |
| `persistence.size` | string | `1Gi` | PVC size. |
| `persistence.storageClass` | string | `""` | StorageClass name. Empty uses cluster default. |
| `persistence.accessMode` | string | `ReadWriteOnce` | PVC access mode. |
| `rootUser` | string | `root` | MariaDB root username. |
| `rootHost` | string | `%` | Host mask for the root user grant. |
| `dbSetupEnabled` | bool | `true` | Run the db-setup job to create per-instance databases and users. |
| `createSecret` | bool | `true` (unset) | When `false`, create an ExternalSecret for root credentials instead. |
| `gcpSecretName` | string | — | GCP secret containing `root-password` and `root-user` (when `createSecret: false`). |
| `secretStoreName` | string | `gcp-clusterstore` | ExternalSecrets store name. |
| `secretStoreKind` | string | `ClusterSecretStore` | ExternalSecrets store kind. |
| `secretRefreshInterval` | string | `1h` | How often to refresh the external secret. |

### `bebot.mariadb.backup`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable the backup CronJob. |
| `schedule` | string | `0 2 * * *` | Cron schedule. |
| `destination` | string | `pvc` | Backup destination: `pvc` or `s3`. |
| `pvc.size` | string | `5Gi` | PVC size for backup storage. |
| `pvc.storageClass` | string | `""` | StorageClass for backup PVC. |
| `pvc.accessMode` | string | `ReadWriteOnce` | Access mode for backup PVC. |
| `s3.bucket` | string | — | S3 bucket name. |
| `s3.region` | string | `us-east-1` | AWS region. |
| `s3.endpoint` | string | `""` | Custom endpoint URL (MinIO, Backblaze, etc.). |
| `s3.path` | string | `backups/bebot` | Key prefix within the bucket. |
| `s3.image` | string | `amazon/aws-cli:2` | Image used for the upload step. |
| `s3.credentialsSecret` | string | — | Name of K8s Secret with `access-key-id` and `secret-access-key`. |
| `s3.externalSecret.enabled` | bool | `false` | Create an ExternalSecret to populate `credentialsSecret`. |
| `s3.externalSecret.gcpSecretName` | string | — | GCP secret with S3 credential keys. |

### `bebot`

| Key | Type | Default | Description |
|---|---|---|---|
| `imageRepository` | string | — | Container image repository. |
| `imageTag` | string | `latest` | Image tag. |
| `imagePullSecrets` | list | `[]` | Image pull secret names. |

### `bebot.instances[]`

| Key | Type | Description |
|---|---|---|
| `name` | string | Unique instance name, used in all resource names. |
| `enabled` | bool | Set `false` to suspend the bot without removing MariaDB. |
| `guildId` | int | Anarchy Online guild/org ID. |
| `mariadbUser` | string | MySQL user for this instance. |
| `mariadbDatabase` | string | MySQL database for this instance. |
| `ao_username` | string | AO account username. |
| `bot_name` | string | In-game bot character name. |
| `dimension` | string | AO dimension ID (`5` = Rubi-Ka). |
| `raidbot` | bool | Enable raid bot mode. |
| `botOwner` | string | AO character with owner-level access. |
| `superAdmins` | list | AO characters with super-admin access. |
| `ao_password` | string | AO account password. Required when `createSecret: true`. |
| `mariadbPassword` | string | MySQL password for `mariadbUser`. Required when `createSecret: true`. |
| `mariadbHost` | string | MySQL host. Defaults to the in-cluster MariaDB service name. Override when using an external database. |
| `createSecret` | bool | `true` = Helm manages the secret. `false` = use ExternalSecret. |
| `gcpSecretName` | string | GCP secret with `ao_password`, `mariadb_user`, `mariadb_password`, `mariadb_database`, `mariadb_host`. |
| `secretStoreName` | string | ExternalSecrets store name. |
| `secretStoreKind` | string | `SecretStore` or `ClusterSecretStore`. |
| `secretRefreshInterval` | string | Refresh interval for the ExternalSecret. |

### `bebot.instances[]` — advanced bot settings

These are optional. All values have sensible defaults matching the original BeBot defaults and do not need to be set for a standard deployment.

#### Multi-bot / AOC

| Key | Type | Default | Description |
|---|---|---|---|
| `guild` | string | `""` | AOC guild name. Leave empty for AO. |
| `slave` | string | `""` | Name of a slave bot, if any. |
| `periph` | int | `0` | Number of peripheral bots. |
| `otherBots` | list | `[]` | List of other bot character names that are guild/raidbot members. Rendered as `$other_bots["name"] = true;` entries. |

#### Logging

| Key | Type | Default | Description |
|---|---|---|---|
| `log` | string | `chat` | Logging level: `all`, `chat`, or `off`. |
| `logPath` | string | `./log` | Relative or absolute path for log files. |
| `logTimestamp` | string | `none` | Timestamp format in logs: `datetime`, `date`, `time`, or `none`. |

#### Bot behaviour

| Key | Type | Default | Description |
|---|---|---|---|
| `commandPrefix` | string | `!` | Bot command prefix. Must be a valid PHP regex character (e.g. use `\.` for `.`). |
| `cronDelay` | int | `30` | Seconds before cron jobs run for the first time after startup. |
| `tellDelay` | int | `2222` | Milliseconds between outgoing tells (anti-flood). |
| `reconnectTime` | int | `60` | Seconds to wait before attempting reconnect after a disconnect. |
| `accessAllBots` | bool | `false` | Allow cross-bot access in modules like BotStatistics. |
| `coreDirectories` | string | `""` | Comma-separated list of additional core directories to load. |
| `moduleDirectories` | string | `""` | Comma-separated list of additional module directories to load. |

#### Proxy

| Key | Type | Default | Description |
|---|---|---|---|
| `useProxyServer` | bool | `false` | Enable HTTP proxy fallback for web lookups. |
| `proxyServerAddress` | string | `""` | Comma-separated list of proxy addresses in `IP:PORT` format. |

#### MySQL advanced

| Key | Type | Default | Description |
|---|---|---|---|
| `tablePrefix` | string | _(unset)_ | Override the default table prefix (defaults to bot name). Set to `""` for no prefix. Only rendered when explicitly set. |
| `noUnderscore` | bool | `false` | When `true`, suppresses the `_` separator appended after `tablePrefix`. |
| `masterTableName` | string | _(unset)_ | Override the master table name (defaults to `botname_tablenames`). Only rendered when explicitly set. |

---

## GCP Secret Payloads

Use the included helper script to generate the JSON payload for each secret type:

```bash
# Bot instance credentials
python tools/generate-gcp-secret.py bot-config | \
  gcloud secrets versions add my-bebot-secret --data-file=-

# MariaDB root credentials
python tools/generate-gcp-secret.py mariadb-root | \
  gcloud secrets versions add my-bebot-mariadb-root --data-file=-

# S3 backup credentials
python tools/generate-gcp-secret.py s3-credentials | \
  gcloud secrets versions add my-bebot-s3-creds --data-file=-

# Container registry pull credentials
python tools/generate-gcp-secret.py registry | \
  gcloud secrets versions add my-registry-creds --data-file=-
```

---

## Deployment Examples

Ready-to-use values files are provided in the [`examples/`](examples/) directory:

| File | Description |
|---|---|
| [`values-baked-secrets.yaml`](charts/bebot/examples/values-baked-secrets.yaml) | All credentials in values — simplest setup, dev/local use |
| [`values-external-secrets.yaml`](charts/bebot/examples/values-external-secrets.yaml) | All credentials from GCP Secret Manager via ExternalSecrets |
| [`values-backup-pvc.yaml`](charts/bebot/examples/values-backup-pvc.yaml) | Backup overlay — dump databases to a PVC |
| [`values-backup-s3.yaml`](charts/bebot/examples/values-backup-s3.yaml) | Backup overlay — dump databases and sync to S3 |

The backup files are designed as overlays — layer them on top of a base values file:

```bash
helm install my-bebot . \
  -f examples/values-external-secrets.yaml \
  -f examples/values-backup-s3.yaml
```

---

### Option A: Credentials baked into values.yaml

The simplest path. All credentials are stored directly in the Helm values and rendered into a Kubernetes Secret at install time. Suitable for local or dev deployments where a secret store is not available.

> **Note:** Avoid committing a values file containing real passwords to source control. Use `helm install -f my-secret-values.yaml` with a file kept outside the repo, or use Sealed Secrets / SOPS to encrypt it at rest.

```yaml
bebot:
  mariadb:
    enabled: true
    persistence:
      enabled: true
      size: 2Gi
    # Root credentials are auto-generated on first install and stored in a
    # K8s Secret. They are reused on subsequent upgrades.

  imageRepository: "ghcr.io/my-org/ao-bebot"
  imageTag: "1.2.3"

  instances:
    - name: myguild
      enabled: true
      guildId: 123456
      mariadbUser: "myguilduser"
      mariadbDatabase: "myguilddb"
      ao_username: "my_ao_account"
      bot_name: "MyBotCharacter"
      dimension: "5"
      raidbot: false
      botOwner: "MyOwnerChar"
      superAdmins:
        - "AdminChar1"
        - "AdminChar2"
      # createSecret defaults to true — Helm creates the Secret directly.
      # The following keys must be supplied in the values file (or via --set):
      ao_password: "change_me"
      mariadbPassword: "change_me"
```

---

### Option B: Credentials from GCP Secret Manager (ExternalSecrets)

Recommended for production. Credentials are never stored in the Helm values or in-cluster ConfigMaps — they are pulled at runtime from GCP Secret Manager by the [external-secrets operator](https://external-secrets.io).

#### 1. Create the secrets in GCP

Use the helper script to generate the correct JSON payload for each secret, then upload it:

```bash
# Bot instance credentials
python tools/generate-gcp-secret.py bot-config | \
  gcloud secrets versions add my-bebot-myguild --data-file=-

# MariaDB root credentials
python tools/generate-gcp-secret.py mariadb-root | \
  gcloud secrets versions add my-bebot-mariadb-root --data-file=-

# Container registry pull credentials (if registry is private)
python tools/generate-gcp-secret.py registry | \
  gcloud secrets versions add my-registry-creds --data-file=-
```

Each GCP secret is a JSON object. The ExternalSecret resources created by this chart will pull individual keys from it — you do not need to structure it any differently.

#### 2. Configure values.yaml

```yaml
bebot:
  mariadb:
    enabled: true
    persistence:
      enabled: true
      size: 2Gi
    # Pull root credentials from GCP instead of auto-generating them.
    createSecret: false
    gcpSecretName: my-bebot-mariadb-root   # GCP secret with root-user and root-password keys
    secretStoreName: gcp-clusterstore
    secretStoreKind: ClusterSecretStore
    secretRefreshInterval: 1h

  imageRepository: "ghcr.io/my-org/ao-bebot"
  imageTag: "1.2.3"
  imagePullSecrets:
    - my-regcred

  instances:
    - name: myguild
      enabled: true
      guildId: 123456
      mariadbUser: "myguilduser"       # Still required — used by the db-setup job
      mariadbDatabase: "myguilddb"     # Still required — used by the db-setup job
      ao_username: "my_ao_account"
      bot_name: "MyBotCharacter"
      dimension: "5"
      raidbot: false
      botOwner: "MyOwnerChar"
      superAdmins:
        - "AdminChar1"
        - "AdminChar2"
      # createSecret: false tells the chart to create an ExternalSecret instead
      # of a K8s Secret for bot credentials.
      createSecret: false
      gcpSecretName: my-bebot-myguild  # GCP secret with ao_password, mariadb_user,
                                       # mariadb_password, mariadb_database, mariadb_host
      secretStoreName: gcp-clusterstore
      secretStoreKind: ClusterSecretStore
      secretRefreshInterval: 1h

  # Use extraObjects to pull registry credentials from GCP.
  extraObjects:
    - apiVersion: external-secrets.io/v1
      kind: ExternalSecret
      metadata:
        name: my-regcred
      spec:
        refreshInterval: 1h
        secretStoreRef:
          name: gcp-clusterstore
          kind: ClusterSecretStore
        target:
          name: my-regcred
          creationPolicy: Owner
          template:
            type: kubernetes.io/dockerconfigjson
            data:
              .dockerconfigjson: "{{ .dockerconfigjson }}"
        data:
          - secretKey: dockerconfigjson
            remoteRef:
              key: my-registry-creds
```
