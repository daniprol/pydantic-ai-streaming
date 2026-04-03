This project uses pnpm for workspaces and as package manager.

Always use pnpm when installing dependencies and also for running commands (e.g. "pnpm dlx ..." instead of "npx ...")

For python backend we use uv for everything (e.g. "uv add ...", "uv sync", "uv run python ...").

When adding components and new tools always try to use clis instead of manually adding the files (e.g., use shadcn cli to add components)
