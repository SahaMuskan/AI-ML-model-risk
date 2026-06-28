# Deployment Guide

How to deploy **Model Risk Studio** inside an organisation — typically a bank's internal
environment — so an MRM team can use it as a shared tool.

This guide assumes the app already runs locally. If not, start with [SETUP.md](SETUP.md).

> **What this app is.** A self-contained FastAPI web app. State lives in a single SQLite
> file (`data/mrm.db`). The only outbound network traffic is **Track B live calls** to the
> LLM endpoint you configure — everything else (dashboard, tiering, Track A, findings,
> reports) is computed locally. The app has **no built-in authentication**; put it behind
> your own access control (see §4).

---

## Deployment options at a glance

| Option | Best for | Effort | Section |
|---|---|---|---|
| Local / single VM (uvicorn) | A quick internal pilot, one user or a small team | Lowest | [§1](#1-quickest-single-vm) |
| **Docker container** | The recommended, portable baseline for any host | Low | [§2](#2-docker-the-portable-baseline) |
| Azure App Service / AKS | Banks already on Azure (pairs naturally with Azure OpenAI) | Medium | [§3.1](#31-azure) |
| AWS ECS Fargate / Beanstalk | Banks on AWS | Medium | [§3.2](#32-aws) |
| On-prem / air-gapped | No public cloud; internal LLM gateway or fully simulated | Medium | [§3.3](#33-on-prem--air-gapped) |

Whichever you pick, the two things you always configure are: **environment variables**
(the `.env` contents — see [SETUP.md §5](SETUP.md)) and **persistent storage** for
`data/mrm.db` (§5).

---

## 1. Quickest: single VM

For a small internal pilot, run it directly on a Linux or Windows VM.

```bash
pip install -r requirements.txt
# bind to all interfaces so colleagues can reach it; pick your port
uvicorn app:app --host 0.0.0.0 --port 8000
```

To keep it running after you log out, use a process manager (`systemd` on Linux, NSSM or
a Scheduled Task on Windows, or `tmux`/`screen` for a quick-and-dirty option).

A minimal **systemd** unit (`/etc/systemd/system/model-risk-studio.service`):

```ini
[Unit]
Description=Model Risk Studio
After=network.target

[Service]
WorkingDirectory=/opt/model-risk-studio
EnvironmentFile=/opt/model-risk-studio/.env
ExecStart=/opt/model-risk-studio/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
User=mrmapp

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now model-risk-studio
```

> This is fine for a handful of users. For anything wider, prefer Docker (§2) and put a
> reverse proxy + auth in front (§4).

---

## 2. Docker (the portable baseline)

A `Dockerfile` and `.dockerignore` are already in the repo. The image is based on
`python:3.12-slim` and starts uvicorn on port 8000.

### Build & run

```bash
docker build -t model-risk-studio .

docker run -d --name mrm \
  -p 8000:8000 \
  --env-file .env \
  -v "$(pwd)/data:/app/data" \
  model-risk-studio
```

- `--env-file .env` injects your provider credentials. **The `.env` file is never baked
  into the image** (it's in `.dockerignore`).
- `-v .../data:/app/data` keeps the SQLite database on the host so it survives container
  restarts and image rebuilds (§5).

### docker-compose (optional)

```yaml
services:
  mrm:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

```bash
docker compose up -d
```

### Push to a private registry

Banks deploy from an internal registry (Azure ACR, AWS ECR, Artifactory, Harbor), not
Docker Hub:

```bash
docker tag model-risk-studio registry.internal.bank.com/mrm/model-risk-studio:1.0.0
docker push registry.internal.bank.com/mrm/model-risk-studio:1.0.0
```

---

## 3. Cloud / on-prem targets

### 3.1 Azure

The natural home if the bank uses **Azure OpenAI** (set `LLM_PROVIDER=azure` — see
[SETUP.md §5](SETUP.md)). Calls to the model then stay within the Azure tenant.

**Azure App Service (containers)** — simplest:
1. Push the image to **Azure Container Registry (ACR)**.
2. Create a **Web App for Containers** pointing at that image.
3. Set the `.env` values as **App Settings** (Configuration → Application settings).
4. Set `WEBSITES_PORT=8000` so App Service routes to the right port.
5. Add a **mounted Azure Files share** at `/app/data` for persistence (§5), or move to a
   managed database (§6).
6. Restrict access via **Easy Auth (Microsoft Entra ID)** and/or VNet integration (§4).

**Azure Kubernetes Service (AKS)** — for larger or multi-app estates: deploy the image as
a Deployment + Service, store secrets in **Azure Key Vault** (via CSI driver), use a
**PersistentVolumeClaim** for `/app/data` (or a managed Postgres), and front it with an
Ingress that enforces Entra ID auth.

### 3.2 AWS

The natural home if the bank uses AWS Bedrock (via an OpenAI-compatible gateway →
`LLM_PROVIDER=custom`) or routes OpenAI through a gateway.

- **ECS Fargate** — run the image as a task/service; inject `.env` values from **AWS
  Secrets Manager** / SSM Parameter Store; mount **EFS** at `/app/data` for persistence;
  front it with an **ALB** (add Cognito/OIDC auth on the listener).
- **Elastic Beanstalk (Docker platform)** — simplest path; set env vars in the EB
  console; attach EFS for `data/`.

### 3.3 On-prem / air-gapped

- **Fully offline / simulated mode** needs no LLM endpoint at all — every screen works and
  costs nothing. Good for a no-network demo or a security review.
- **On-prem live mode** points `LLM_PROVIDER=custom` at an internal OpenAI-compatible
  model server (vLLM, Ollama, TGI, an internal gateway). No traffic leaves the network.
- Build the image where you have internet, then transfer it: `docker save` →
  `docker load` on the target host (or push to the internal registry).

---

## 4. Access control (important — the app has no auth)

Model Risk Studio ships **without** authentication; anyone who can reach the port can use
it, including the **Reset demo** action. Never expose it directly to an untrusted network.
Put one of these in front:

- **Reverse proxy + SSO** — nginx / Apache / Traefik with an OIDC or SAML module wired to
  the bank's IdP (Entra ID, Okta, PingFederate). Most common pattern.
- **Platform-native auth** — Azure App Service **Easy Auth (Entra ID)**, or an **AWS ALB**
  with Cognito/OIDC on the listener. No proxy to manage.
- **Network isolation** — at minimum, keep it on an internal VNet/subnet reachable only
  over the corporate network or VPN.

Because all state is local and there are no user accounts, authorisation is "anyone who
gets through the proxy can edit everything." If you need per-user roles or an audit trail
of who changed what, that's an application-level enhancement to scope separately.

---

## 5. Persistence

All state — model edits, findings, stored Track B runs — lives in **`data/mrm.db`**
(SQLite). It is created on first run and is **git-ignored**.

- **Container deployments:** mount a volume at `/app/data` (Docker volume, Azure Files,
  AWS EFS, or a Kubernetes PVC). Without it, edits are lost when the container is replaced.
- **Back it up** like any other data file — a periodic copy of `mrm.db` is enough.
- **Reset:** the **Reset demo** button (or deleting `mrm.db`) restores the bundled demo
  data. Don't expose Reset demo to general users in a real deployment (see §4).

---

## 6. Scaling beyond a single instance

SQLite is a **single-writer** database. It comfortably serves a typical MRM team (tens of
users, read-heavy usage), but it does **not** support multiple app instances writing to the
same file. If you need horizontal scale or high availability:

1. **Stay single-instance first.** Run **one** uvicorn worker (the default). Do *not* set
   `--workers > 1` against SQLite. Vertical scaling handles most internal MRM workloads.
2. **Move to PostgreSQL** when you genuinely need multiple instances. `database.py` is a
   thin layer storing JSON documents with standard SQL; porting it to Postgres (e.g. via
   `psycopg`, using a `JSONB` column) is a contained change — no schema migrations or ORM
   to unwind. Then you can run several replicas behind a load balancer.

For most internal deployments, **step 1 is all you need.**

---

## 7. Cost & rate limits (live mode)

Only **Track B** makes model calls. A full run ≈ **43 calls** (~25 chatbot + ~18 judge);
with `gpt-4o-mini`-class models that's typically a few US cents per run. To control spend:

- Use a **small/cheap model** for `OPENAI_JUDGE_MODEL` (it only needs to score, not chat).
- Encourage running a **subset of tests** during iteration (the test picker on the Track B
  page) and the full suite only for a formal validation.
- Set **budget alerts / quota** on the provider side (OpenAI usage limits, Azure cost
  alerts) — the app does not enforce a spend cap.

---

## 8. Pre-go-live checklist

- [ ] `.env` configured for the right provider; **/health** shows `"live_mode": true`
- [ ] Credentials supplied as platform **secrets / app settings** — never committed, never in the image
- [ ] `data/` on a **persistent, backed-up** volume (or migrated to Postgres)
- [ ] **Authentication** in front of the app (SSO / Easy Auth / ALB auth) — §4
- [ ] App reachable only over the **internal network / VPN**, not the public internet
- [ ] **Reset demo** not exposed to general users
- [ ] Provider **budget alerts / rate limits** set — §7
- [ ] Demo `seed_data.py` content reviewed/replaced; in-product **disclaimers kept intact**
- [ ] Thresholds and Track B eval sets reviewed against the bank's own policy before any reliance

---

## See also

- [SETUP.md](SETUP.md) — install, the three LLM providers, switching to live mode, troubleshooting
- [README.md](README.md) — what the tool does, the honest caveats, project structure
- [CLAUDE.md](CLAUDE.md) — architecture and conventions for developers extending the app
