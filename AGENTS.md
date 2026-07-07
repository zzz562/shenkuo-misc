# Project Rules — shenkuo-misc

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
- AI assistant: Grok Build (`grok --cwd ~/projects/shenkuo-misc`)
- GitHub: `zzz562` via SSH

## Preferences

- Explain changes clearly; prefer focused diffs over drive-by refactors.
- Run commands and verify results rather than only suggesting them.
- Match existing code style when editing within a sub-project.