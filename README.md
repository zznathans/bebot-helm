# ao-bebot Helm Chart

[![CI](https://github.com/zznathans/bebot-helm/actions/workflows/ci.yaml/badge.svg)](https://github.com/zznathans/bebot-helm/actions/workflows/ci.yaml)
[![Release](https://img.shields.io/github/v/release/zznathans/bebot-helm)](https://github.com/zznathans/bebot-helm/releases)

Helm chart for deploying [BeBot](https://github.com/zznathans/BeBot) (a fork of [J-Soft/BeBot](https://github.com/J-Soft/BeBot), an Anarchy Online/Age of Conan chat bot) on Kubernetes, with optional in-cluster MariaDB, automated backups, and full ExternalSecret support for credential management. This chart is deploy-only - the image it deploys is built and published by that repo, not this one.

---

## Features

- Deploy one or more bot instances from a single chart
- Optional in-cluster shared MariaDB, managed via the [mariadb-operator](https://github.com/mariadb-operator/mariadb-operator)'s `MariaDB`/`Database`/`User`/`Grant` CRs
- Credentials via plain-text Helm values or GCP Secret Manager (ExternalSecrets)
- S3-compatible or PVC-based database backups via the operator's `Backup` CR
- On-demand restore (`Restore` CR) and automatic disaster-recovery bootstrap of a fresh MariaDB instance from the latest backup (`bootstrapFrom`)
- NetworkPolicy to isolate MariaDB access
- Checksum-based pod rollouts when config or secrets change

---

## Prerequisites

- Helm 3
- Kubernetes 1.25+
- [external-secrets operator](https://external-secrets.io) (only if using `createSecret: false`)
- [mariadb-operator](https://github.com/mariadb-operator/mariadb-operator) CRDs and controller, pulled in as a dependency automatically whenever `bebot.mariadb.enabled` is true (the default) and skipped when it's false. If your cluster already runs a shared copy of the operator, set `bebot.mariadbOperator.enabled: false` and install/manage it separately instead (`helm install mariadb-operator-crds mariadb-operator/mariadb-operator-crds && helm install mariadb-operator mariadb-operator/mariadb-operator`).

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

### `bebot.mariadbOperator`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | follows `bebot.mariadb.enabled` | Pull in the `mariadb-operator` and `mariadb-operator-crds` charts as toggleable dependencies of this chart (via a `condition` in `Chart.yaml`). Left unset, the operator is installed automatically when `bebot.mariadb.enabled` is true and skipped when it's false (nothing else in this chart uses the operator's CRDs). Set explicitly to override: `false` to reuse a cluster-shared operator instead of installing a second, redundant copy even with `bebot.mariadb.enabled: true`; `true` to install it regardless of `bebot.mariadb.enabled`. |

### `bebot.mariadb`

The chart deploys a **single shared MariaDB** instance via the mariadb-operator's `MariaDB` custom resource, used by default. All bot instances connect to this shared server unless they override `mariadbHost` (see `bebot.instances[]` below); instances using the shared server each get their own database and user within it, declared via `Database`/`User`/`Grant` CRs — an instance with `mariadbHost` set gets none of those CRs, since it isn't using the server this chart manages.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Deploy the shared in-cluster MariaDB (as a `MariaDB` CR). Set `false` to use an external database. Requires the mariadb-operator CRDs/controller to be present in the cluster. |
| `image` | string | `mariadb:11.4` | MariaDB container image, passed through to the `MariaDB` CR. |
| `persistence.enabled` | bool | `true` | Use persistent storage for MariaDB data. If `false`, the `MariaDB` CR uses ephemeral storage. |
| `persistence.size` | string | `1Gi` | Storage volume size. |
| `persistence.storageClass` | string | `""` | StorageClass name. Empty uses cluster default. |
| `rootUser` | string | `root` | MariaDB root username (informational — the underlying image/operator always uses `root`). |
| `rootHost` | string | `%` | Host mask for the root user grant. |
| `createSecret` | bool | `true` (unset) | When `false`, create an ExternalSecret for root credentials instead. Pulls `mariadb_root_password` and `mariadb_root_user` from `bebot.externalSecret`. |

Each enabled bot instance gets a `Database`, `User`, and `Grant` CR (replacing the old init-container SQL bootstrap), reconciled continuously by the operator rather than run once.

### `bebot.mariadb.metrics`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable the `MariaDB` CR's built-in Prometheus exporter (`spec.metrics.enabled`) and expose metrics on port 9104. |
| `image` | string | `""` | Container image for the operator-managed `mysqld_exporter`. Empty uses the operator's default. |
| `grafanaDashboard.enabled` | bool | `false` | Create a ConfigMap containing the MySQL Overview dashboard for Grafana's sidecar to load. Requires `grafana.sidecar.dashboards.enabled=true` in your Grafana Helm deployment. |
| `grafanaDashboard.label` | string | `grafana_dashboard` | Label the Grafana sidecar uses to discover dashboard ConfigMaps. |

### `bebot.mariadb.backup`

A single mariadb-operator `Backup` CR, replacing the old dual CronJob (timestamped + snapshot) setup. Tighten `schedule` for a shorter RPO instead of running a second cadence.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable the `Backup` CR. |
| `schedule` | string | `0 2 * * *` | Cron schedule. |
| `maxRetention` | string | `720h` | How long to retain backups, as a Go duration string. |
| `destination` | string | `pvc` | Backup destination: `pvc` or `s3`. |
| `pvc.size` | string | `5Gi` | PVC size for backup storage. |
| `pvc.storageClass` | string | `""` | StorageClass for backup PVC. |
| `pvc.accessMode` | string | `ReadWriteOnce` | Access mode for backup PVC. |
| `s3.bucket` | string | — | S3 bucket name. Always required — the underlying `Backup` CRD has no `secretKeyRef` for this field, so it can't be sourced from `s3.externalSecret` (only the credentials below can). |
| `s3.region` | string | `us-east-1` | AWS region. |
| `s3.endpoint` | string | `""` | Custom endpoint host, no scheme (MinIO, Backblaze, Cloudflare R2, etc.). Defaults to `s3.<region>.amazonaws.com` when empty. Like `bucket`, this can't be sourced from `s3.externalSecret` — set it directly even when that's enabled. |
| `s3.tls` | bool | `true` | Use TLS when connecting to the S3 endpoint. Almost always leave this `true` — the operator's S3 client defaults to plain HTTP otherwise, which most real providers (including Cloudflare R2) reject with a "301 Moved Permanently" redirect rather than serving the request. |
| `s3.path` | string | `backups/bebot` | Key prefix within the bucket. |
| `s3.credentialsSecret` | string | — | Name of K8s Secret with `access-key-id` and `secret-access-key`. Auto-named when `s3.externalSecret.enabled` is `true`. |
| `s3.externalSecret.enabled` | bool | `false` | When `true`, create an ExternalSecret to populate `credentialsSecret`'s access-key-id/secret-access-key from a dedicated external secret (bucket/endpoint are not sourced from it — set those directly, see above). The secret is identified by `s3.externalSecret.secretName`. |
| `s3.externalSecret.secretName` | string | — | Name of the secret in the external store. Required when `s3.externalSecret.enabled` is `true`. Must be a JSON object with keys `bucket_name`, `endpoint`, `access_key` (base64-encoded), `secret_key` (base64-encoded). |

### `bebot.mariadb.restore`

A one-shot mariadb-operator `Restore` CR that restores the **existing, live** MariaDB instance from a `Backup`. Requires `bebot.mariadb.backup.enabled`. Turn `enabled` on, `helm upgrade`, wait for it to complete, then turn it back off — it is not meant to be left on permanently.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Trigger a restore into the live MariaDB instance. |
| `targetRecoveryTime` | string | `""` | Optional RFC3339 timestamp to restore a specific point in time instead of the latest backup. |

### `bebot.mariadb.bootstrapFrom`

Seeds a **brand-new** MariaDB instance automatically from the latest `Backup` at creation time (`spec.bootstrapFrom` on the `MariaDB` CR) — the disaster-recovery path if the MariaDB CR/PVC is ever lost and recreated. Requires `bebot.mariadb.backup.enabled`. Safe to leave enabled permanently: it has no effect on an already-existing instance.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Bootstrap a fresh MariaDB instance from the latest backup. |
| `targetRecoveryTime` | string | `""` | Optional RFC3339 timestamp to bootstrap from a specific point in time instead of the latest backup. |

### `bebot`

| Key | Type | Default | Description |
|---|---|---|---|
| `imageRepository` | string | — | Container image repository. |
| `imageTag` | string | `latest` | Image tag. |
| `imagePullSecrets` | list | `[]` | Image pull secret names. |
| `terminationGracePeriodSeconds` | int | `60` | Seconds Kubernetes waits for the bot to exit after SIGTERM before sending SIGKILL. Should be long enough for the bot to disconnect from AO servers cleanly. |
| `resources.requests.cpu` | string | `100m` | CPU request for the bot container. |
| `resources.requests.memory` | string | `128Mi` | Memory request for the bot container. |
| `resources.limits.cpu` | string | `500m` | CPU limit for the bot container. |
| `resources.limits.memory` | string | `256Mi` | Memory limit for the bot container. |

### `bebot.instances[]`

| Key | Type | Description |
|---|---|---|
| `name` | string | Unique instance name, used in all resource names. |
| `enabled` | bool | Set `false` to suspend the bot without removing MariaDB. |
| `guildId` | int | Anarchy Online guild/org ID. |
| `mariadbUser` | string | MySQL user for this instance. |
| `mariadbDatabase` | string | MySQL database for this instance. |
| `mariadbHost` | string | MySQL server host for this instance. Leave unset to use this release's shared in-cluster MariaDB (`<release>-mariadb`). Set to point this instance at a different/external MySQL-compatible server; when set, this chart won't create a `Database`/`User`/`Grant` CR for it. |
| `mariadbPort` | int | MySQL port for this instance. Leave unset to use the default (3306). |
| `mariadbSsl` | bool | Connect to `mariadbHost` over SSL/TLS. Required by most managed database providers (DigitalOcean, AWS RDS, etc). Requires a bot image built from a BeBot version with SSL support (`$ssl`/`$ssl_ca` in `Mysql.conf`). |
| `mariadbSslCa` | string | Optional path (inside the bot container) to a CA certificate bundle to verify the server's certificate against when `mariadbSsl` is true. Left unset, the connection is still encrypted but the certificate isn't verified. |
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

This repo is chart resources and their dependencies only - no bot code, no
Dockerfile, no image build. That all lives in
[zznathans/BeBot](https://github.com/zznathans/BeBot), which builds its own
image on every release and opens a PR here bumping `imageRepository`/
`imageTag` in `values.yaml` (`fix(bot): bump image to <version>`) - merging
that PR is what triggers everything below.

### Workflow overview

```
Push / PR
    └── CI ──────────────────────────────────────────────── push to main / PR to main
           └── Release (semantic-release) ──────────────── main only, on CI success
                    └── Release Charts ─────────────────── on GitHub Release published
                              └── Pages deploy ──────────── on Release Charts success
```

PRs are labelled automatically by the **Pull Request Labeler** workflow whenever they are opened or updated.

### Workflows

| File | Name | Trigger | Purpose |
|---|---|---|---|
| `ci.yaml` | CI | Push to `main`; PR to `main` | Lint and test — pylint, pytest, yamllint, helm lint, helm unit tests, helm-docs auto-commit |
| `release.yaml` | Release | CI passes on `main` (skips `[skip ci]` commits) | Runs [semantic-release](https://semantic-release.gitbook.io) to cut a versioned GitHub Release and update the changelog; uses a GitHub App token to satisfy branch protection requirements |
| `helm.yaml` | Release Charts | GitHub Release published | Runs [chart-releaser](https://github.com/helm/chart-releaser-action) to package the chart and publish it to the `gh-pages` branch; also copies `README.md` from `main` to `gh-pages` |
| `static.yml` | Deploy static content to Pages | Release Charts succeeds (or manual `workflow_dispatch`) | Deploys the `gh-pages` branch to GitHub Pages, making the Helm repository publicly available |
| `labeler.yaml` | Pull Request Labeler | Pull request opened / updated | Applies labels (`helm`, `ci`, `documentation`, `tests`, `tools`, `examples`, `dependencies`) based on changed files using `.github/labeler.yml` |

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

All ExternalSecret resources carry `argocd.argoproj.io/sync-wave: "-1"`, the `MariaDB`/`Backup` CRs and bot Deployments carry `sync-wave: "1"`, and the per-instance `Database`/`User`/`Grant` CRs carry `sync-wave: "2"`. ArgoCD waits for each wave's resources to be healthy before applying the next wave, and its built-in ExternalSecret health check waits for `Ready: True` — so nothing is created until the secrets and MariaDB instance it depends on are ready.

### Plain Helm

Use `--wait` with a generous timeout. Pods will initially crash-loop until secrets are available, then recover automatically:

```bash
helm install my-bebot bebot/bebot -f my-values.yaml --wait --timeout 10m
```

---

## GCP Secret Payloads

A helper script generates GCP Secret Manager payloads interactively. Each subcommand produces a separate GCP secret:

```bash
# Main credentials secret (bot instances + MariaDB root):
python charts/bebot/tools/generate-gcp-secret.py secrets --print-to-stdout | \
  gcloud secrets versions add bebot-secrets --data-file=-

# S3 backup credentials (separate secret — reference via s3.externalSecret.secretName):
python charts/bebot/tools/generate-gcp-secret.py s3-creds --print-to-stdout | \
  gcloud secrets versions add bebot-s3-creds --data-file=-

# Registry pull credentials (separate secret):
python charts/bebot/tools/generate-gcp-secret.py registry --print-to-stdout | \
  gcloud secrets versions add bebot-regcred --data-file=-
```

The `secrets` subcommand prompts for each instance's credentials and the shared MariaDB root credentials. The resulting JSON looks like:

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
| [`values-mariadb-restore.yaml`](charts/bebot/examples/values-mariadb-restore.yaml) | Restore overlay — on-demand restore or automatic bootstrap-from-backup |

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


