# Project Rules — whaletrail-lab

Personal lab and long-term Grok collaboration space on Mac Mini.

## Conventions

- Use `main` as the default branch.
- Commit messages: imperative mood, concise subject (e.g. `add: gold backtest script`).
- Keep secrets out of the repo — use `.env` (gitignored) or `configs/` references only.
- Place new work in the appropriate top-level folder:
  - `notes/` — observations, reading notes
  - `experiments/` — prototypes and spikes
  - `tools/` — reusable scripts
  - `configs/` — setup docs and config backups
  - `projects/` — sub-projects that outgrow experiments
  - `archive/` — inactive but worth keeping

## Environment

- Primary machine: Mac Mini (darwin, aarch64)
- AI assistant: Grok Build (`grok --cwd ~/projects/whaletrail-lab`)
- GitHub: `zzz562` via SSH

## Preferences

- Explain changes clearly; prefer focused diffs over drive-by refactors.
- Run commands and verify results rather than only suggesting them.
- Match existing code style when editing within a sub-project.

## Source of truth and sync rules

- Mac mini `~/Projects/whaletrail-lab` is the primary development workspace.
- MacBook `~/github_code/whaletrail-lab` is a read-only/sync mirror by default; do not develop there unless explicitly switching roles.
- Push completed Mac mini work to `origin/main`; refresh MacBook with `git fetch && git reset --hard origin/main && git clean -fd` after saving any local notes.
- Do not commit runtime logs, local caches, `.venv`, `results/`, or `data_cache/`.
- Legacy `projects/gold-paper/` has been removed; WhaleTrail is the only active trading/backtest system.
