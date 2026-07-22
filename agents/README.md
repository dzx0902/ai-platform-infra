# Agent Checkouts

`ai-platform-infra` keeps deployment configuration separate from business code.
For production, clone the four agent repositories next to this repository or add them as Git submodules, then set `*_AGENT_PATH` in `.env`.
