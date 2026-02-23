# Avengers Team + OpenClaw Integration

This package runs an asynchronous advisory-board control plane for Avengers:
- captain-america
- alex-hormozi
- brian-tracy
- april-dunford
- russell-brunson
- steve-blank

## Runtime bridge
- Executor mode: `command`
- Command: `/app/avengers_team/openclaw_exec.sh {ROLE} "{TASK}" "{RESULT}"`
- Transport: `docker exec <openclaw-avengers-container> openclaw agent --agent <id> --json`
- Session isolation supported via `OPENCLAW_SESSION_MODE=isolated`

## Queue paths
`openclaw-avengers` and `avengers_team` both mount `./data/avengers_team`:
- OpenClaw path: `/data/avengers_team`
- Control-plane path: `/workspace`

Trigger file:
- `/data/avengers_team/run_request.md`

## Start
```bash
docker compose up -d --build openclaw-avengers avengers_team
```

## Restart control plane
```bash
docker compose restart avengers_team
```

## Best Practices
- See `BEST_PRACTICES.md` for security, queue, execution, and output standards.
