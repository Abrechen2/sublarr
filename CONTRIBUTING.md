# Sublarr — Development Workflow

Solo project workflow. Pragmatic, but with enough discipline to maintain a clean
Git history and avoid broken builds on `master`.
Full contributing guidelines: [sublarr.de/docs/development/contributing](https://sublarr.de/docs/development/contributing/).

---

## Branching Strategy

```
master (stable, always deployable)
  ├── feat/description    — new feature
  ├── fix/description     — bug fix
  ├── chore/description   — tooling, CI, dependencies
  ├── docs/description    — documentation only
  └── refactor/description — code restructuring without new functionality
```

### When to use a Branch + PR?

| Change | Branch + PR | Direct to master |
|--------|:-----------:|:----------------:|
| New feature | Yes | - |
| Bug fix (more than 1 file) | Yes | - |
| Refactoring | Yes | - |
| Security fix | Yes | - |
| CI/workflow changes | Yes | - |
| Version bump (`chore: bump version`) | - | Yes |
| Typo in README/docs (1–2 lines) | - | Yes |
| Hotfix (1 file, obvious) | - | Yes, with justification |

**Rule of thumb:** If it takes more than 5 minutes or touches more than 1 file → Branch.

---

## Development Flow

### 1. Preparation

```bash
git checkout master
git pull origin master
git checkout -b feat/short-description
```

### 2. Development

- Conventional Commits: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`, `security:`
- Commit messages describe WHAT and WHY — not "fix", "update", "misc"
- Multiple small commits are better than one large commit

### 3. Run tests locally (REQUIRED before push)

```bash
# Backend
cd backend && python -m pytest --tb=short -q

# Frontend
cd frontend && npm run test -- --run
cd frontend && npm run lint
```

If tests fail → fix them, don't ignore them. CI blocks the merge anyway.

### 4. Push + create PR

```bash
git push -u origin feat/short-description
gh pr create --title "feat: short description" --body "## Summary
- What was changed
- Why

## Test plan
- [ ] Backend tests green
- [ ] Frontend tests green
- [ ] Manually tested: ..."
```

### 5. Self-Review

Even as a solo dev: read through the PR diff once.

Checklist:
- [ ] No credentials, API keys, debug logs
- [ ] No `console.log` or `print()` debugging leftovers
- [ ] Commit messages are understandable
- [ ] Nothing accidentally committed: `.env`, `node_modules`, `__pycache__`

### 6. Merge

- **Merge strategy: Squash Merge** (default)
  - Keeps master history clean: 1 feature = 1 commit
  - GitHub UI: "Squash and merge"
- **Exception:** Merge commit for large features with meaningful intermediate history

### 7. Clean up

```bash
git checkout master
git pull origin master
git branch -d feat/short-description     # delete locally
```

---

## Release Flow

Releases are decoupled from daily work. Not every merge is a release.

### When to release?

- **Patch** (0.12.x): Collected after 2–5 bug fixes, or immediately for critical fixes
- **Minor** (0.x.0): After a feature milestone (e.g., all planned phases complete)
- **Major** (x.0.0): Breaking changes — not currently relevant (beta phase)

### Release Order (CRITICAL — follow exactly)

```
1. All changes merged to master
2. Update backend/VERSION
3. Update CHANGELOG.md
4. Commit: "chore: bump version to x.y.z-beta"   (direct to master OK)
5. Tag + push: git tag v0.12.3-beta && git push origin v0.12.3-beta
6. release.yml triggers automatically: CI → Docker Build → GitHub Release
```

**Rule:** Code done → version bump → tag → release. Never the other way around.

---

## Claude Code Behavior

When Claude Code works in this project, these rules apply automatically:

### Before coding
- Check current branch (`git branch --show-current`)
- If on `master` and the change is non-trivial → suggest a new branch
- If scope is unclear → use Plan Mode

### While coding
- Follow Conventional Commits
- Run tests after changes (backend and/or frontend, depending on scope)
- No changes to CI workflows in feature PRs (use a separate `chore/` branch)

### Before committing
- Check `git diff` for credentials, debug logs, unwanted files
- Stage only changed files (no `git add .`)

### Creating a PR
- Title: Conventional Commit format
- Body: Summary + Test Plan
- Wait for CI before suggesting a merge

---

## Anti-Patterns (avoid)

| Don't do | Instead |
|---|---|
| `git commit -m "fix"` | `git commit -m "fix: provider timeout on slow APIs"` |
| Push directly to master for features | Feature branch + PR |
| CI changes in feature PRs | Separate `chore/ci-*` branch |
| Release before merge | Merge all PRs, then release |
| `git add .` | Stage files explicitly |
| Skip tests | Test locally, use CI as a safety net |
| Forget version bump | Part of the release flow, not the feature |
