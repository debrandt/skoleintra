# Deploying Skoleintra on a NixOS Server

This guide covers deploying Skoleintra on a NixOS home server managed with
[Colmena](https://github.com/zhaofengli/colmena) and
[agenix](https://github.com/ryantm/agenix) for secrets.

---

## Prerequisites

- NixOS host with flakes enabled
- Colmena configured in your server repo's `flake.nix`
- agenix set up with at least one host key (typically derived from the host's
  SSH host key)
- PostgreSQL not yet required on the host — the module enables it

---

## Step 1 — Add the flake input

In your server repo's `flake.nix`, add the `skoleintra` input and thread the
package down to your host via `specialArgs`:

```nix
inputs = {
  # ... existing inputs ...
  skoleintra.url = "github:debrandt/skoleintra";
};

outputs = { nixpkgs, agenix, colmena, skoleintra, ... }: {
  colmena = {
    meta.nixpkgs = import nixpkgs { system = "x86_64-linux"; };

    your-server = {
      deployment = { ... };

      imports = [ ./modules/skoleintra.nix ];

      _module.args.skoleintra-pkg =
        skoleintra.packages.x86_64-linux.default;

      services.skoleintra = {
        enable = true;
        virtualHost = "skoleintra.your-tailnet.ts.net";
        # port defaults to 8000
      };
    };
  };
};
```

> **Local development tip:** while iterating, pin the input to a local path so
> you don't need to push every change:
> ```nix
> skoleintra.url = "path:/home/th/github/skoleintra";
> ```
> Switch back to `github:debrandt/skoleintra` before a real deployment.

---

## Step 2 — Create the agenix secret

Create a plaintext env file, then encrypt it with agenix.

**Plaintext** (never commit this — encrypt it first):

```
DATABASE_URL=postgresql+psycopg:///skoleintra?host=/run/postgresql
SKOLEINTRA_HOSTNAME=your-school.skoleintra.dk
SKOLEINTRA_USERNAME=your-username
SKOLEINTRA_PASSWORD=your-password
SKOLEINTRA_LOGIN_TYPE=alm
SKOLEINTRA_STATE_DIR=/var/lib/skoleintra
NTFY_URL=https://ntfy.your-domain.dk
NTFY_TOPIC=skoleintra
NTFY_TOKEN=tk_token
ALERT_NTFY_URL=https://ntfy.your-domain.dk
ALERT_NTFY_TOPIC=skoleintra-alerts
ALTER_NTFY_TOKEN=tk_alert_token
```

> `DATABASE_URL` uses the PostgreSQL Unix socket with peer authentication — no
> database password is needed because the service runs as the `skoleintra`
> system user which is granted ownership of the database.

Encrypt it:

```bash
# from the root of your server repo
agenix -e secrets/skoleintra.env.age
```

Register the secret in your agenix secrets config (typically `secrets/secrets.nix`):

```nix
{
  "skoleintra.env.age".publicKeys = [
    "ssh-ed25519 AAAA... root@server"  # host public key
  ];
}
```

---

## Step 3 — Create `modules/skoleintra.nix`

Create `modules/skoleintra.nix` in your server repo:

```nix
{ config, lib, pkgs, skoleintra-pkg, ... }:

let
  cfg = config.services.skoleintra;
  pkg = cfg.package;
  portStr = toString cfg.port;

  commonService = {
    User = "skoleintra";
    Group = "skoleintra";
    StateDirectory = "skoleintra";
    StateDirectoryMode = "0700";
    EnvironmentFile = cfg.environmentFile;
    PrivateTmp = true;
    NoNewPrivileges = true;
    StandardOutput = "journal";
    StandardError = "journal";
  };
in
{
  options.services.skoleintra = {
    enable = lib.mkEnableOption "Skoleintra scraper and web UI";

    package = lib.mkOption {
      type = lib.types.package;
      default = skoleintra-pkg;
      description = "The skoleintra package to use.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 8000;
      description = "Local port for the web UI.";
    };

    virtualHost = lib.mkOption {
      type = lib.types.str;
      description = "Caddy virtual host name (e.g. Tailscale MagicDNS hostname).";
    };

    environmentFile = lib.mkOption {
      type = lib.types.path;
      default = config.age.secrets.skoleintra-env.path;
      description = "Path to the systemd EnvironmentFile with runtime secrets.";
    };
  };

  config = lib.mkIf cfg.enable {

    # ------------------------------------------------------------------ secrets
    age.secrets.skoleintra-env = {
      file = ../secrets/skoleintra.env.age;
      owner = "skoleintra";
    };

    # ------------------------------------------------------------------- users
    users.users.skoleintra = {
      isSystemUser = true;
      group = "skoleintra";
      description = "Skoleintra service account";
    };
    users.groups.skoleintra = {};

    # ---------------------------------------------------------------- postgres
    services.postgresql = {
      enable = true;
      ensureDatabases = [ "skoleintra" ];
      ensureUsers = [{
        name = "skoleintra";
        ensureDBOwnership = true;
      }];
    };

    # ------------------------------------------------------------ migrate unit
    systemd.services.skoleintra-migrate = {
      description = "Skoleintra — apply database migrations";
      after = [ "postgresql.service" ];
      requires = [ "postgresql.service" ];
      before = [
        "skoleintra-web.service"
        "skoleintra-scrape.service"
        "skoleintra-notify.service"
      ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = commonService // {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = "${pkg}/bin/skoleintra migrate";
      };
    };

    # --------------------------------------------------------------- web unit
    systemd.services.skoleintra-web = {
      description = "Skoleintra — web UI";
      after = [ "skoleintra-migrate.service" "network.target" ];
      requires = [ "skoleintra-migrate.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = commonService // {
        Type = "simple";
        Restart = "on-failure";
        RestartSec = "5s";
        ExecStart = "${pkg}/bin/skoleintra web --host 127.0.0.1 --port ${portStr}";
      };
    };

    # ------------------------------------------------------------- scrape units
    systemd.services.skoleintra-scrape = {
      description = "Skoleintra — scrape ForældreIntra";
      after = [ "skoleintra-migrate.service" "network-online.target" ];
      requires = [ "skoleintra-migrate.service" "network-online.target" ];
      serviceConfig = commonService // {
        Type = "oneshot";
        ExecStart = "${pkg}/bin/skoleintra scrape";
      };
    };

    systemd.timers.skoleintra-scrape = {
      description = "Skoleintra — scrape timer (every 15 min)";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "2min";
        OnUnitActiveSec = "15min";
        RandomizedDelaySec = "60";
        Persistent = true;
      };
    };

    # ------------------------------------------------------------- notify units
    systemd.services.skoleintra-notify = {
      description = "Skoleintra — send pending notifications";
      after = [ "skoleintra-migrate.service" "network-online.target" ];
      requires = [ "skoleintra-migrate.service" "network-online.target" ];
      serviceConfig = commonService // {
        Type = "oneshot";
        ExecStart = "${pkg}/bin/skoleintra notify";
      };
    };

    systemd.timers.skoleintra-notify = {
      description = "Skoleintra — notify timer (every 15 min, offset 5 min)";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "7min";
        OnUnitActiveSec = "15min";
        Persistent = true;
      };
    };

    # ------------------------------------------------------------------ caddy
    services.caddy.virtualHosts.${cfg.virtualHost}.extraConfig = ''
      reverse_proxy localhost:${portStr}
    '';
  };
}
```

---

## Step 4 — Deploy

```bash
# Validate locally
nix build .#nixosConfigurations.your-server.config.system.build.toplevel

# Deploy
colmena apply --on your-server
```

---

## Step 5 — Verify

Run each step manually before relying on the timers:

```bash
# Check migration completed successfully
systemctl status skoleintra-migrate
journalctl -u skoleintra-migrate -n 20

# Check web UI is up
curl -s http://localhost:8000/healthz

# Run a manual scrape and inspect output
systemctl start skoleintra-scrape
journalctl -u skoleintra-scrape -n 50

# Run a manual notify cycle
systemctl start skoleintra-notify
journalctl -u skoleintra-notify -n 30

# Confirm timers are active and cadence looks right
systemctl list-timers skoleintra*
```

Then open `https://<virtualHost>` from any device on your Tailscale network.

---

## Notes

| Topic | Detail |
|---|---|
| **Web access** | Restricted to Tailscale by using the MagicDNS hostname as the Caddy `virtualHost`. No additional auth layer is configured. |
| **Database auth** | Peer auth via Unix socket — no DB password required. `DATABASE_URL` must use `?host=/run/postgresql`. |
| **State directory** | Cookie jar and debug artifacts are stored in `/var/lib/skoleintra` (mode 0700, owned by `skoleintra`). |
| **Migrations** | `skoleintra-migrate` runs at boot and is ordered before all other units. It uses `RemainAfterExit` so restarts don't re-run it unnecessarily. |
| **Scrape cadence** | 15-minute interval with up to 60 s random jitter. Increase cadence only after confirming portal tolerance. |
| **Notify cadence** | 15-minute interval, offset ~5 minutes from scrape boot delay so notifications follow shortly after each scrape. |
| **Logs** | All units log to journald: `journalctl -u skoleintra-* -f` |

---

## Optional: MinIO blob storage for attachments and photos

Skoleintra can download message attachments and photos and store them in any
S3-compatible object store. MinIO is the easiest self-hosted option on a NixOS
server. When `BLOB_S3_BUCKET` is not set the blob pipeline is silently skipped
and everything still works — attachments just link back to the portal URL
instead of a locally-served file.

### Enable MinIO in your NixOS module

Add the following to `modules/skoleintra.nix` (or a separate
`modules/minio.nix`) inside the `config` block, alongside the existing
`systemd.services` entries:

```nix
# ------------------------------------------------------------------ MinIO
services.minio = {
  enable = true;
  dataDir = [ "/var/lib/minio/data" ];
  # credentials are read from the environment file below
  credentialsFile = config.age.secrets.minio-env.path;
};

age.secrets.minio-env = {
  file = ../secrets/minio.env.age;
  owner = "minio";
};
```

The MinIO service binds to `127.0.0.1:9000` (API) and `127.0.0.1:9001`
(console) by default on NixOS. If you want the console reachable over
Tailscale, add a Caddy virtual host:

```nix
services.caddy.virtualHosts."minio.your-tailnet.ts.net".extraConfig = ''
  reverse_proxy localhost:9001
'';
```

### Create the MinIO credentials secret

**Plaintext** (encrypt before committing):

```
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=change-me-use-a-long-random-string
```

Encrypt:

```bash
agenix -e secrets/minio.env.age
```

Register the public key in `secrets/secrets.nix`:

```nix
"minio.env.age".publicKeys = [
  "ssh-ed25519 AAAA... root@server"
];
```

### Create the bucket and an access key

After deploying, create the bucket and a service account key via the MinIO
console (`https://minio.your-tailnet.ts.net`) or with `mc` (MinIO Client):

```bash
# Install mc in a nix-shell if not present on the server
nix-shell -p minio-client

# Alias the local server (run on the server itself or over SSH)
mc alias set local http://127.0.0.1:9000 minioadmin 'change-me-use-a-long-random-string'

# Create the bucket
mc mb local/skoleintra

# Create a restricted service account for skoleintra
mc admin user svcacct add \
  --access-key skoleintra-access \
  --secret-key 'another-long-random-string' \
  local minioadmin
```

The service account only needs `s3:GetObject`, `s3:PutObject`, and
`s3:GetObject` on the `skoleintra` bucket. You can scope it further via a
MinIO policy if desired.

### Add blob settings to your Skoleintra environment secret

Append the following to the plaintext env file before re-encrypting:

```
BLOB_S3_ENDPOINT_URL=http://127.0.0.1:9000
BLOB_S3_BUCKET=skoleintra
BLOB_S3_ACCESS_KEY_ID=skoleintra-access
BLOB_S3_SECRET_ACCESS_KEY=another-long-random-string
BLOB_S3_REGION=us-east-1
BLOB_S3_PREFIX=skoleintra
```

`BLOB_S3_REGION` is required by boto3 but ignored by MinIO — any value works.
`BLOB_S3_PREFIX` is the key prefix inside the bucket; the default `skoleintra`
is fine for a single-tenant setup.

### Verify

After deploying and running a scrape cycle:

```bash
# Confirm blobs were uploaded (look for "blobs uploaded: N" in output)
journalctl -u skoleintra-scrape -n 50

# List objects in the bucket
mc ls local/skoleintra --recursive | head -20

# Open an item with an attachment in the web UI and click the link —
# it should redirect through a presigned MinIO URL
```

### Notes

| Topic | Detail |
|---|---|
| **Presigned URL expiry** | Default 24 hours. The web UI generates a fresh presigned URL on every `/blobs/{id}` request, so users always get a valid link. |
| **Graceful fallback** | If MinIO is unreachable or `BLOB_S3_BUCKET` is unset, the web UI falls back to the original portal URL and the scraper continues without uploading blobs. |
| **Existing attachments** | Blobs are downloaded for any attachment with a null `blob_key`. Running `skoleintra scrape` after enabling MinIO will back-fill all historical attachments on the next cycle. |
| **Photos** | When a photos scraper is added, photos will use the same pipeline — no additional configuration is needed. ntfy will deliver the first photo as an inline attachment via a presigned URL. |
