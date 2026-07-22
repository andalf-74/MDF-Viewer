# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`docs/requirements/*.md`** — one file per capability/domain, the source of truth for *what the app does*. Each individually-testable sentence is tagged inline with a stable ID, `REQ-<DOMAIN>-NNN`.
- **`docs/architecture.md`** — the decision log for *how* the app is built (MVC/View implementation detail). Plays the role a `docs/adr/` directory would in other repos.
- **`CLAUDE.md`** at the repo root — project overview and architecture philosophy. See `docs/agents/issue-tracker.md`'s "Issue Triage flavors" section for the taxonomy that decides which of the docs below a given issue must update.

This repo does **not** use `CONTEXT.md`, `CONTEXT-MAP.md`, or `docs/adr/` — `docs/requirements/*.md` and `docs/architecture.md` already fill those roles and predate this skill's setup here. Don't create the generic files alongside them; extend the existing ones instead.

Two more current-state maps worth checking depending on the task:

- **`docs/ui.md`** — current-state map of menus, toolbar, panels, dialogs.
- **`docs/api.md`** — current-state map of modules/classes and their public surface.

If any of these files don't exist for the area you're touching, proceed silently — don't flag their absence or suggest creating them upfront unless the work you're doing is exactly the kind that should add one (see `docs/agents/issue-tracker.md`'s "Issue Triage flavors" section for which flavor of change touches which doc).

## File structure

Single-context repo (this repo) — no `CONTEXT.md`/`docs/adr/` equivalents to lay out here; see CLAUDE.md's Project Structure section for the full directory layout and the doc set (`docs/architecture.md`, `docs/requirements/`, `docs/ui.md`, `docs/api.md`, `docs/release.md`).

## Use the requirements' vocabulary

When your output names a domain concept from `docs/requirements/*.md` (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined there. For the core model classes (`SignalData`, `SignalMetadata`, `ActiveSignal`), the definition lives in `docs/architecture.md`'s "Signal classes" section instead — that's the source of truth (module paths, field ownership), not `docs/requirements/*.md` or CLAUDE.md. Don't drift to synonyms the docs don't use.

If the concept you need isn't in the requirements yet, that's a signal — either you're inventing language the project doesn't use (reconsider), or there's a real gap. For a real gap, follow the Feature rule in `docs/agents/issue-tracker.md`: write or update the relevant `docs/requirements/*.md` file *before* implementation starts, not after.

## Flag architecture-decision conflicts

If your output contradicts an existing entry in `docs/architecture.md`'s decision log, surface it explicitly rather than silently overriding:

> _Contradicts the "[decision name]" entry in docs/architecture.md — but worth reopening because…_
