# ao-bebot Helm Chart

Helm chart for deploying [BeBot](https://github.com/J-Soft/BeBot) (an Anarchy Online IRC bot) on Kubernetes, with optional in-cluster MariaDB, automated backups, and full ExternalSecret support for credential management.

---

## Features

- Deploy one or more bot instances from a single chart
- Optional in-cluster shared MariaDB
- Credentials via plain-text Helm values or GCP Secret Manager (ExternalSecrets)
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

### `bebot.externalSecret`

Global configuration for the single upstream secret used by all ExternalSecret resources in this chart. All ExternalSecrets pull from one JSON secret in GCP Secret Manager.

| Key | Type | Default | Description |
|---|---|---|---|
| `gcpSecretName` | string | `""` | Name of the upstream secret in the external store. Required when any resource uses `createSecret: false`. |
| `secretStoreName` | string | `gcp-clusterstore` | Name of the ClusterSecretStore or SecretStore to use. |
| `secretStoreKind` | string | `ClusterSecretStore` | Kind of the secret store (`ClusterSecretStore` or `SecretStore`). |
| `secretRefreshInterval` | string | `1h` | How often ExternalSecrets poll for updates. |

### `bebot.mariadb`

The chart deploys a **single shared MariaDB** instance. All bot instances connect to the same server; each gets its own database and user within it. There is no per-instance MariaDB option.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Deploy the shared in-cluster MariaDB. Set `false` to use an external database. |
| `persistence.enabled` | bool | `true` | Enable a PVC for MariaDB data. |
| `persistence.size` | string | `1Gi` | PVC size. |
| `persistence.storageClass` | string | `""` | StorageClass name. Empty uses cluster default. |
| `persistence.accessMode` | string | `ReadWriteOnce` | PVC access mode. |
| `rootUser` | string | `root` | MariaDB root username. |
| `rootHost` | string | `%` | Host mask for the root user grant. |
| `dbSetupEnabled` | bool | `true` | Run an init container on first deploy to create each bot instance's database and user inside the shared MariaDB. |
| `createSecret` | bool | `true` (unset) | When `false`, create an ExternalSecret for root credentials instead. Pulls `mariadb_root_password` and `mariadb_root_user` from `bebot.externalSecret`. |

### `bebot.mariadb.backup`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable the backup CronJob. |
| `schedule` | string | `0 2 * * *` | Cron schedule. |
| `destination` | string | `pvc` | Backup destination: `pvc` or `s3`. |
| `pvc.size` | string | `5Gi` | PVC size for backup storage. |
| `pvc.storageClass` | string | `""` | StorageClass for backup PVC. |
| `pvc.accessMode` | string | `ReadWriteOnce` | Access mode for backup PVC. |
| `s3.bucket` | string | — | S3 bucket name. Required when `externalSecret.enabled` is `false`; sourced from the external secret otherwise. |
| `s3.region` | string | `us-east-1` | AWS region. |
| `s3.endpoint` | string | `""` | Custom endpoint URL (MinIO, Backblaze, etc.). Ignored when `externalSecret.enabled` is `true`; sourced from the external secret instead. |
| `s3.path` | string | `backups/bebot` | Key prefix within the bucket. |
| `s3.credentialsSecret` | string | — | Name of K8s Secret with `access-key-id` and `secret-access-key`. Auto-named when `externalSecret.enabled` is `true`. |
| `s3.externalSecret.enabled` | bool | `false` | When `true`, create an ExternalSecret to populate `credentialsSecret` from a dedicated external secret. The secret is identified by `s3.externalSecret.secretName`. |
| `s3.externalSecret.secretName` | string | — | Name of the secret in the external store. Required when `externalSecret.enabled` is `true`. Must be a JSON object with keys `bucket_name`, `endpoint`, `access_key` (base64-encoded), `secret_key` (base64-encoded). |

Backup dumps are gzip-compressed (`.sql.gz`).

### `bebot.mariadb.backup.snapshot`

A separate CronJob that dumps each database to a **fixed filename** (no timestamp), so each run overwrites the previous snapshot. Intended for short-term recovery, distinct from the timestamped long-term backups. Uses the same destination and S3 credentials as `bebot.mariadb.backup`.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable the snapshot CronJob. |
| `intervalMinutes` | int | `15` | How often the snapshot runs, in minutes. |
| `path` | string | `snapshots/bebot` | S3 key prefix for snapshot dumps. Ignored for PVC destination. |

Snapshot dumps are gzip-compressed (`{db}_snapshot.sql.gz`) and stored separately from timestamped backups.

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
| `createSecret` | bool | `true` = Helm manages the secret. `false` = use ExternalSecret (pulls `<name>_ao_password`, `<name>_mariadb_user`, `<name>_mariadb_password`, `<name>_mariadb_database` from `bebot.externalSecret`). |

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

## CI / CD

All automation runs through GitHub Actions. The pipelines are chained: each stage only proceeds when the previous one succeeds.

### Workflow overview

```
Push / PR
    └── CI ──────────────────────────────────────────────── push to main / PR to main
           └── Release (semantic-release) ──────────────── main only, on CI success
                    └── Docker (build + push + scan) ───── on GitHub Release published
                              └── Release Charts ─────────── on Docker success
                                        └── Pages deploy ── on Release Charts success
```

PRs are labelled automatically by the **Pull Request Labeler** workflow whenever they are opened or updated.

The **Trivy** workflow runs independently on a weekly schedule to catch newly-disclosed vulnerabilities in the published image.

### Workflows

| File | Name | Trigger | Purpose |
|---|---|---|---|
| `ci.yaml` | CI | Push to `main`; PR to `main` | Lint and test — pylint, pytest, yamllint, helm lint, helm unit tests, helm-docs auto-commit |
| `release.yaml` | Release | CI passes on `main` (skips `[skip ci]` commits) | Runs [semantic-release](https://semantic-release.gitbook.io) to cut a versioned GitHub Release and update the changelog; uses a GitHub App token to bypass branch protection |
| `docker.yaml` | Docker | GitHub Release published | Builds a multi-arch (`linux/amd64`, `linux/arm64`) image, pushes to `ghcr.io`, scans with Trivy, and uploads results to the Security tab; blocks on `CRITICAL`/`HIGH` unfixed CVEs |
| `helm.yaml` | Release Charts | Docker workflow succeeds | Runs [chart-releaser](https://github.com/helm/chart-releaser-action) to package the chart and publish it to the `gh-pages` branch; also copies `README.md` from `main` to `gh-pages` |
| `static.yml` | Deploy static content to Pages | Release Charts succeeds (or manual `workflow_dispatch`) | Deploys the `gh-pages` branch to GitHub Pages, making the Helm repository publicly available |
| `labeler.yaml` | Pull Request Labeler | Pull request opened / updated | Applies labels (`helm`, `docker`, `ci`, `documentation`, `tests`, `tools`, `examples`, `dependencies`) based on changed files using `.github/labeler.yml` |
| `trivy.yml` | trivy | Weekly schedule (Mondays) | Builds the image from the Dockerfile and scans with Trivy; results are uploaded to the Security tab |

### Secrets and variables required

| Name | Kind | Used by | Purpose |
|---|---|---|---|
| `GITHUB_TOKEN` | Automatic | All workflows | Standard GitHub token for checkout, package push, release upload |
| `RELEASE_APP_ID` | Repository variable | `release.yaml` | GitHub App ID used to generate a short-lived installation token |
| `RELEASE_APP_PRIVATE_KEY` | Repository secret | `release.yaml` | GitHub App private key (`.pem` contents) |

---

## Testing

After installing the chart, run the included Helm tests to verify the deployment:

```bash
helm test my-bebot
```

This runs two test suites:

| Test | What it checks |
|---|---|
| `test-mariadb-ping` | MariaDB is reachable and accepting connections via the root credentials secret |
| `test-mariadb-grants` | Each bot instance's database user can connect and run queries against its database |

Both tests clean up their pods automatically on success (`hook-delete-policy: hook-succeeded`).

---

## Startup Ordering (ExternalSecrets Race)

When using `createSecret: false`, Kubernetes may try to start pods before the ExternalSecrets Operator has synced secrets from GCP, causing `CreateContainerConfigError`. Two mitigations are built into the chart:

### ArgoCD (recommended)

All ExternalSecret resources carry `argocd.argoproj.io/sync-wave: "-1"` and all Deployments/CronJobs carry `sync-wave: "1"`. ArgoCD waits for each wave's resources to be healthy before applying the next wave, and its built-in ExternalSecret health check waits for `Ready: True` — so Deployments are never created until secrets are synced.

### Plain Helm

Use `--wait` with a generous timeout. Pods will initially crash-loop until secrets are available, then recover automatically:

```bash
helm install my-bebot bebot/bebot -f my-values.yaml --wait --timeout 10m
```

---

## GCP Secret Payloads

All chart credentials live in a **single GCP Secret Manager secret** as a flat JSON object with plain-text string values (no base64 encoding). A helper script is included to generate the payload interactively:

```bash
# Generate and upload the main credentials secret:
python charts/bebot/tools/generate-gcp-secret.py secrets --print-to-stdout | \
  gcloud secrets versions add bebot-secrets --data-file=-

# Generate registry pull credentials (separate secret):
python charts/bebot/tools/generate-gcp-secret.py registry --print-to-stdout | \
  gcloud secrets versions add bebot-regcred --data-file=-
```

The `secrets` subcommand prompts for each instance's credentials, the shared MariaDB root credentials, and optionally S3 backup credentials. The resulting JSON looks like:

```json
{
  "pfs_ao_password":       "...",
  "pfs_mariadb_user":      "pfsuser",
  "pfs_mariadb_password":  "...",
  "pfs_mariadb_database":  "pfs",
  "mariadb_root_user":     "root",
  "mariadb_root_password": "..."
}
```

The expected keys are:

| Key | Used by |
|---|---|
| `<instance-name>_ao_password` | Bot config ExternalSecret (one per instance) |
| `<instance-name>_mariadb_user` | Bot config ExternalSecret (one per instance) |
| `<instance-name>_mariadb_password` | Bot config ExternalSecret (one per instance) |
| `<instance-name>_mariadb_database` | Bot config ExternalSecret (one per instance) |
| `mariadb_root_user` | MariaDB root credentials ExternalSecret |
| `mariadb_root_password` | MariaDB root credentials ExternalSecret |

Registry pull credentials use a **separate** GCP secret with a single `dockerconfigjson` key. Reference it from `extraObjects` in your values file.

### S3 Backup Secret

S3 backup credentials live in their own dedicated external secret, separate from the main credentials secret. Point to it with `bebot.mariadb.backup.s3.externalSecret.secretName`. The secret must be a JSON object where `access_key` and `secret_key` are base64-encoded strings:

```json
{
  "bucket_name": "my-backup-bucket",
  "endpoint":    "https://s3.example.com",
  "access_key":  "<base64-encoded access key>",
  "secret_key":  "<base64-encoded secret key>"
}
```

| Key | Used by |
|---|---|
| `bucket_name` | S3 backup ExternalSecret → `bucket` key in the credentials secret |
| `endpoint` | S3 backup ExternalSecret → `endpoint` key in the credentials secret |
| `access_key` | S3 backup ExternalSecret → `access-key-id` (decoded from base64) |
| `secret_key` | S3 backup ExternalSecret → `secret-access-key` (decoded from base64) |

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
      ao_password: "change_me"
      mariadbPassword: "change_me"
```

---

### Option B: Credentials from GCP Secret Manager (ExternalSecrets)

Recommended for production. Credentials are never stored in the Helm values or in-cluster ConfigMaps — they are pulled at runtime from GCP Secret Manager by the [external-secrets operator](https://external-secrets.io).

#### 1. Create the secret in GCP

Use the included helper to generate and upload the consolidated credentials payload:

```bash
python charts/bebot/tools/generate-gcp-secret.py secrets --print-to-stdout | \
  gcloud secrets versions add my-bebot-secrets --data-file=-
```

The script prompts for each bot instance's credentials, the shared MariaDB root password, and optionally S3 credentials. All values are stored as plain text.

#### 2. Configure values.yaml

```yaml
bebot:
  # Single upstream secret — all ExternalSecrets in this chart pull from here.
  externalSecret:
    gcpSecretName: my-bebot-secrets
    secretStoreName: gcp-clusterstore
    secretStoreKind: ClusterSecretStore
    secretRefreshInterval: 1h

  mariadb:
    enabled: true
    persistence:
      enabled: true
      size: 2Gi
    # Pull root credentials from GCP instead of auto-generating them.
    createSecret: false

  imageRepository: "ghcr.io/my-org/ao-bebot"
  imageTag: "1.2.3"
  imagePullSecrets:
    - my-regcred

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
      # createSecret: false pulls myguild_ao_password, myguild_mariadb_user,
      # myguild_mariadb_password, myguild_mariadb_database from bebot.externalSecret.
      createSecret: false

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
