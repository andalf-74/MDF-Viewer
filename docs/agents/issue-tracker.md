# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues at [andalf-74/MDF-Viewer](https://github.com/andalf-74/MDF-Viewer). Use the `gh` CLI for all operations.

## Issue Triage flavors

GitHub issues arrive in different flavors, and the flavor decides which docs must stay in sync when the issue closes. **Before starting work on an issue, state which flavor it is and get the user's agreement** — don't silently assume it. This is the source of truth for the taxonomy; CLAUDE.md's Development Workflow section points here.

- **Feature** → write or update the relevant `docs/requirements/*.md` file(s) *before* implementation starts.
- **Bug** → after root-causing, check whether a requirements doc needs updating too: either the requirement was silent on this case, or the code deviated from a requirement that was correct. If the fix is purely a wording correction to a requirements/architecture/ui doc with no code change (e.g. the REQ-PLOT-121 case), that edit *is* the fix — there's no separate "Documentation" flavor for this, it's a Bug variant.
- **Test-coverage** → tag the new/existing test(s) with the REQ-ID(s) they verify (`@pytest.mark.requirement("REQ-...")`). No requirements doc change unless writing the test surfaces an actual behavior gap — if it does, that part follows the Bug rule above (e.g. #91's MDF3 fixture surfacing a real `channel_tree()` unit/comment bug).
- **Investigation / Spike** → no doc changes during the investigation itself. Must close by either filing a follow-up Feature/Bug issue, or an explicit no-action note on the issue explaining why nothing further is needed — never leave it closed with no trace of the conclusion.
- **Documentation** → means the end-user manual (not `docs/requirements/`, `docs/architecture.md`, or `docs/ui.md`, which are internal). Tracked starting with #55, which will establish where it lives. No requirements/architecture doc changes, since app behavior isn't changing.
- **Refactor / Tech debt** → no requirements doc change (behavior is unchanged by definition). Add a `docs/architecture.md` decision-log entry if the restructuring reflects a real architectural decision worth recording.
- **Chore / Maintenance** → dependency bumps, CI, packaging. No requirements impact; update `docs/release.md` if it changes the release/build process.
- **Design / Architecture question** → resolve into a `docs/architecture.md` decision-log entry.

**`docs/ui.md`** update is not gated to one flavor the way requirements/architecture are — whichever flavor (Feature or Bug) actually adds, removes, or moves a menu item, toolbar button, dialog, or panel must update the relevant section of `docs/ui.md` too, in the same commit as the code change. It's the map of what the user currently sees; unlike requirements (stable invariants) it's pure current-state documentation, so it goes stale the moment a layout change lands without a matching edit — which is exactly what happened across #97/#99/#100/#101/#102 before this rule existed.

**`docs/api.md`** gets the same treatment — same reasoning, same risk of drift, just mapping the codebase's module/class structure instead of the visible UI. Whichever flavor adds a new module, or changes a class's public methods/signals/fields enough that the existing entry no longer matches, updates the relevant `api.md` entry in the same commit. A pure-internal change with no altered public surface (most Refactor/Tech debt work) doesn't need an edit.

**CHANGELOG.md** is reserved for user-visible changes only (Keep a Changelog style) — Feature and Bug entries. Test-coverage, Investigation, Refactor/Tech debt, Chore, and Design-question issues do not get a CHANGELOG entry unless they also produce a user-visible side effect.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Milestones are used actively in this repo — when listing or creating issues, prefer including `--json milestone` / grouping by milestone so current development priority is visible, matching the "Reviewing Issues" rule in `CLAUDE.md`.

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.**

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only — the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me` — the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
