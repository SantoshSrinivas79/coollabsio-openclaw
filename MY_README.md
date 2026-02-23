# README — OpenClaw Docker Setup (QMD + Telegram + Browser) — New Machine

## What this setup includes

* **OpenClaw gateway + UI** (nginx basic auth)
* **OpenRouter as provider** (primary model set via env)
* **Telegram channel** (allowlist mode)
* **QMD installed** (via `npm`, inside a custom image)
* **Browser sidecar** (CDP connection for automated browsing)
* **Persistent data** using bind mounts:

  * `./data/openclaw` → `/data` (OpenClaw state + workspace)
  * `./data/browser` → browser profile/config

---

## 0) Prerequisites

Install Docker + Docker Compose (v2).

Verify:

```bash
docker --version
docker compose version
```

---

## 1) Folder layout

Create a folder (e.g. `openclaw/`) with:

```
openclaw/
├─ Dockerfile.qmd
├─ docker-compose.yml
├─ docker-compose.local.yml
├─ .env
├─ Dockerfile.browser         # optional (only if you want CDP proxy on :9223)
└─ data/
   ├─ openclaw/               # persistent OpenClaw state (created automatically)
   └─ browser/                # persistent browser profile (created automatically)
```

Create the data folders (recommended):

```bash
mkdir -p data/openclaw data/browser
```

---

## 2) Configure `.env`

Open `.env` and set **your real values**.

### Critical values to set

* `OPENROUTER_API_KEY`
* `AUTH_USERNAME` / `AUTH_PASSWORD`
* `OPENCLAW_GATEWAY_TOKEN` (any random string/uuid is fine)
* `TELEGRAM_BOT_TOKEN`
* `TELEGRAM_BOT_TOKEN_CMTEAM` (recommended: separate bot token for cm_team control plane)
* `TELEGRAM_ALLOW_FROM` (your Telegram username or user id)
* `TELEGRAM_ALLOWED_USER_ID` (numeric Telegram ID for `cm_team` review commands, e.g. `977795179`)

**Security note:** do **not** commit `.env` to git. Also rotate any tokens that were ever pasted/shared.

### `cm_team` Telegram approval gate

`openclaw` and `cm_team` use different Telegram allowlist variables:

* OpenClaw bot allowlist: `TELEGRAM_ALLOW_FROM`
* `cm_team` review/approval allowlist: `TELEGRAM_ALLOWED_USER_ID`
* `cm_team` bot token: `TELEGRAM_BOT_TOKEN_CMTEAM`
* `cm_team` command namespace: `TELEGRAM_COMMAND_NAMESPACE` (default `cm`, e.g. `/cm_status`, `/cm_approve`)

Use a different token from `TELEGRAM_BOT_TOKEN` to avoid Telegram `getUpdates` collisions between OpenClaw and `cm_team`.

Set both if you use the orchestration pipeline. After editing `.env`, apply changes:

```bash
docker compose up -d cm_team
```

Verify inside `cm_team`:

```bash
docker exec cm-team-cron /bin/bash -lc 'grep TELEGRAM_ALLOWED_USER_ID /workspace/.cm_team_env.sh'
```

---

## 3) Build the QMD-enabled OpenClaw image

Your `docker-compose.yml` expects this image name:

* `openclaw:qmd`

Build it using your uploaded `Dockerfile.qmd`:

```bash
docker build -t openclaw:qmd -f Dockerfile.qmd .
```

Confirm QMD is in the image (optional but useful):

```bash
docker run --rm openclaw:qmd sh -lc "which qmd && qmd --help | head"
```

---

## 4) Start the stack

### Standard run (recommended)

```bash
docker compose up -d
```

Check containers:

```bash
docker ps
```

You should see:

* `openclaw`
* `openclaw-browser`

Open UI:

* [http://localhost:8080](http://localhost:8080)

Login using `AUTH_USERNAME` / `AUTH_PASSWORD` from `.env`.

---

## 5) Browser sidecar setup (important)

### What your files currently do

* `docker-compose.yml` sets:
  `BROWSER_CDP_URL=http://browser:9223`
* `docker-compose.local.yml` sets:
  `BROWSER_CDP_URL=http://browser:9222`

But the browser service in both compose files uses:

* `image: coollabsio/openclaw-browser:latest`
* `CHROME_CLI=--remote-debugging-port=9222`

So **9222 is the safe default** unless your browser image is proxying 9223.

### Recommended fix (pick one)

#### Option A (simplest): Use `9222` everywhere

Edit `docker-compose.yml` and change:

```yaml
- BROWSER_CDP_URL=http://browser:9223
```

to:

```yaml
- BROWSER_CDP_URL=http://browser:9222
```

Restart:

```bash
docker compose up -d
```

#### Option B (use your `Dockerfile.browser` to proxy 9223 → 9222)

Your `Dockerfile.browser` creates an nginx proxy that listens on **9223** and forwards to **9222** with a rewritten Host header.

If you want to use that, build a custom browser image:

```bash
docker build -t openclaw-browser:proxy9223 -f Dockerfile.browser .
```

Then update the browser service in `docker-compose.yml` to:

```yaml
browser:
  image: openclaw-browser:proxy9223
```

Now your `BROWSER_CDP_URL=http://browser:9223` matches correctly.

---

## 6) Telegram configuration

Your compose passes:

* `TELEGRAM_BOT_TOKEN`
* `TELEGRAM_DM_POLICY`
* `TELEGRAM_ALLOW_FROM`

In `.env` you are using:

* `TELEGRAM_DM_POLICY=allowlist`
* `TELEGRAM_ALLOW_FROM=fountainhead_79`

That means **only that allowlisted user can DM the bot**.

### Verify Telegram env is loaded

```bash
docker compose exec openclaw sh -lc 'env | grep ^TELEGRAM_'
```

### Basic test

1. Open Telegram
2. Message your bot
3. If your username matches allowlist, you should get responses.

---

## 7) Confirm persistence

This setup uses bind mounts:

* `./data/openclaw:/data`
* `./data/browser:/config`

So state persists across recreation.

Test:

```bash
docker compose down
docker compose up -d
```

Your tokens/config/workspace should remain in `./data/openclaw`.

---

## 8) QMD setup inside OpenClaw

You already installed QMD in the image. Next, you must ensure OpenClaw is configured to **use QMD as memory backend**.

### Check if QMD is available in container

```bash
docker compose exec openclaw sh -lc 'which qmd && qmd --help | head'
```

### Find the active OpenClaw config path

```bash
docker compose exec openclaw sh -lc 'openclaw models status | sed -n "1,25p"'
```

Look for a line like:

* `Config        : .../openclaw.json`

### Enable QMD in that config

Open the config file shown above (example path might be `/data/.openclaw/openclaw.json`):

```bash
docker compose exec openclaw sh
vi /data/.openclaw/openclaw.json
```

Add a memory block if it doesn’t exist:

```json
"memory": {
  "backend": "qmd",
  "qmd": {
    "includeDefaultMemory": true,
    "searchMode": "search"
  }
}
```

Restart:

```bash
docker compose restart openclaw
```

### Warm QMD (optional but recommended)

First run can download models/build index:

```bash
docker compose exec openclaw sh -lc 'qmd update && qmd embed'
```

---

## 9) OpenAI OAuth (Codex) setup (optional)

If you want `openai-codex` OAuth:

```bash
docker compose exec openclaw sh -lc 'openclaw models auth login --provider openai-codex'
```

Follow the printed URL in your browser, then paste the redirect/code back into the terminal prompt.

Verify:

```bash
docker compose exec openclaw sh -lc 'openclaw models status'
```

---

## 10) Common troubleshooting

### “Cannot find module … qmd.js”

You fixed this by using `Dockerfile.qmd` (npm install).
If it returns, rebuild:

```bash
docker build -t openclaw:qmd -f Dockerfile.qmd .
docker compose up -d --force-recreate
```

### Config changes not sticking

Make sure you’re editing the config file that `openclaw models status` reports.

### Browser tool not working

Ensure your `BROWSER_CDP_URL` matches the browser container port:

* Use `9222` (simplest), or
* Build and use the proxy browser image from `Dockerfile.browser` for `9223`

### Check logs

```bash
docker logs -f openclaw
docker logs -f openclaw-browser
```

---

## 11) Backups

Back up these folders:

* `./data/openclaw`
* `./data/browser`

They contain:

* OpenClaw state + workspace + OAuth tokens
* browser profile/session

---

## Quick start checklist

1. Copy files to new machine
2. `mkdir -p data/openclaw data/browser`
3. Edit `.env` (keys + passwords + tokens)
4. `docker build -t openclaw:qmd -f Dockerfile.qmd .`
5. Ensure `BROWSER_CDP_URL` uses `9222` unless you build the proxy browser
6. `docker compose up -d`
7. (Optional) enable QMD memory backend in config + restart
8. (Optional) do OpenAI OAuth login

Source: https://chatgpt.com/c/699029eb-23c4-83a7-b76b-6284f6e5c77d


For Docker AND Mission Control networking. Read this. 
https://chatgpt.com/c/6999cf61-7aa0-83a9-bb6b-2672c1ca3bbb
