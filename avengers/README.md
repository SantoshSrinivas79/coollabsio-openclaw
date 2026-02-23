# Avengers Advisory Board (OpenClaw Agents)

This folder defines a multi-agent advisory board:
- **Captain America** is the ONLY agent who speaks to the user.
- Five expert agents provide internal advisory outputs only.
- Captain America runs a 3-round loop (Diverge -> Converge -> Package), then synthesizes the final answer for the user.

## How to use (human workflow)
1) Start a chat/session with **Captain America**.
2) Provide an objective (what you want + context).
3) Captain America will:
   - Extract missing context (or assume defaults)
   - Delegate to experts
   - Run 3 iterations
   - Produce final deliverables + next actions

## Files
- `SOUL.md`: Shared constitution for all Avengers agents
- `USER.md`: Stable user preferences + constraints (edit this)
- `AGENTS.md`: Team rules and routing (Captain America only talks to user)
- `PROTOCOL.md`: Exact orchestration protocol and iteration loop
- `agents/*`: One folder per agent with their identity and role prompts
