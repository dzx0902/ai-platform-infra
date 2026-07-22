# Agent Environment Files

The root `.env` is limited to platform infrastructure, shared LLM providers, and repository paths. Each Agent has a separate environment file for its private credentials and feature-specific settings.

Before the first deployment, create these untracked files:

```bash
cp env/workspace.env.example env/workspace.env
cp env/paper.env.example env/paper.env
cp env/planner.env.example env/planner.env
cp env/finance.env.example env/finance.env
cp env/astrbot.env.example env/astrbot.env
```

The Notion URL page ID is `3978473f-2546-8025-bb1a-ec75d5819e74`. It is retained as `NOTION_DATABASE_PAGE_ID` for reference. The Planner API must use `NOTION_DATA_SOURCE_ID`, which should be copied from a successful Notion schema check rather than guessed from a browser URL.
