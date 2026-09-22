# Personal AI Platform

Docker Compose deployment for the Workspace, Paper Radar, Daily Planner, and Finance agents.

## Quick start

```bash
cp .env.example .env
cp env/workspace.env.example env/workspace.env
cp env/paper.env.example env/paper.env
cp env/planner.env.example env/planner.env
cp env/finance.env.example env/finance.env
cp env/astrbot.env.example env/astrbot.env
docker compose up -d --build
docker compose ps
```

Finance services are intentionally not part of the first deployment. Start them later with `docker compose --profile finance up -d` and set `finance_daily_report.enabled: true` in `config/jobs.yaml`.

The four source repositories must be checked out next to this repository, or their paths must be configured through `WORKSPACE_AGENT_PATH`, `PAPER_AGENT_PATH`, `PLANNER_AGENT_PATH`, and `FINANCE_AGENT_PATH`.

Keep shared infrastructure and LLM provider values in `.env`; put Agent-specific credentials in the matching `env/*.env` file. These files are ignored by Git.

## Service endpoints

- Gateway: `http://localhost:8088/health`
- Agent Core: `http://localhost:8088/api/core/health`
- Paper: `http://localhost:8088/api/paper/health`
- Planner: `http://localhost:8088/api/planner/api/v1/health`
- Finance: `http://localhost:8088/api/finance/health`
- AstrBot: `http://localhost:6185`

Runtime data is stored in Docker named volumes. Do not commit `.env` or volume exports.

## Feishu routing

Use AstrBot as the single interactive Feishu bot. It can call `/papers`, `/paper_run`, `/plan`, `/today`, `/finance`, and `/portfolio` through the platform network.

For scheduled reports, create two separate Feishu incoming-webhook bots in two groups or two dedicated report chats. Put their webhook URLs in `env/finance.env`:

```dotenv
FEISHU_PAPER_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
FEISHU_FINANCE_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
```

The scheduler routes Paper Radar daily reports to `paper` and Finance daily reports to `finance`. Webhook bots push messages only; they do not replace the AstrBot command bot.

Paper Radar's daily schedule is defined by `paper_daily` in `config/jobs.yaml` and defaults to 08:00 Asia/Shanghai. At runtime, the scheduler reads the template from `config/jobs.yaml` and writes user changes to the `scheduler_data` Docker volume, so Feishu schedule changes do not dirty the Git checkout.

`paper_fulltext` runs separately at 10:00 Asia/Shanghai. It downloads and extracts up to three high-scoring PDFs, creates full-paper notes in the `paper_data` volume, and sends Markdown to knowledge-sync. New template jobs are merged into existing scheduler settings; user-edited schedules remain intact. Check its status with `GET /v1/jobs/paper_fulltext/diagnostics` inside the scheduler container. A `partial` status means at least one PDF or summary failed.

The API default for DeepSeek is `deepseek-flash`. Existing production `.env` files are ignored by Git, so update `DEEPSEEK_MODEL=deepseek-flash` on the server before recreating `agent-core`, `paper-agent`, `planner-agent`, and any enabled Finance services. AstrBot model providers saved in its UI must be updated there separately.

From the AstrBot Feishu bot:

```text
/paper_schedule
/paper_schedule 08:00 --llm --limit 5
/paper_schedule off
/paper_schedule on
/paper_schedule run
/paper_schedule doctor
```

The `run` action triggers the same scheduler path as the daily cron job and sends the report through the Paper webhook route.

If the daily push does not arrive, use `/paper_schedule doctor` first. On the server, inspect the same state with:

```bash
docker compose exec scheduler python - <<'PY'
import httpx
print(httpx.get("http://127.0.0.1:8082/v1/jobs/paper_daily/diagnostics", timeout=10).text)
PY

docker compose logs --tail=120 scheduler notification-service paper-agent
```

The legacy Finance Agent long-connection bot is disabled by default. Only start it when a separate interactive Finance bot is intentionally needed:

```bash
docker compose --profile native-finance-feishu up -d finance-feishu
```

## Hostinger VPS deployment

Install Docker Engine and the Docker Compose plugin on Ubuntu 24.04, then clone this repository and the four agent repositories below `/opt/ai-platform`. Create `.env` from `.env.example`, set real API keys and a strong `POSTGRES_PASSWORD`, then run `docker compose up -d --build`.

The deployment workflow is intentionally manual until `VPS_HOST`, `VPS_USER`, and `VPS_SSH_KEY` are configured as GitHub repository secrets. Production updates preserve all named volumes.
