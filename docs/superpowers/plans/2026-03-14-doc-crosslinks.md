# Sublarr Documentation Cross-Links Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure website (sublarr.de), wiki (wiki.sublarr.de), GitHub README, and wiki content all cross-reference each other with correct URLs — no broken or outdated links.

**Architecture:** Four independent file edits (README.md, index.html, two wiki content files), then one GraphQL push to sync changed wiki pages to the live Wiki.js instance.

**Tech Stack:** Markdown (README/wiki content), HTML (website), Wiki.js GraphQL API (push to live wiki), Playwright MCP (browser automation for JWT + GraphQL calls).

---

## Audit: What's wrong today

| Location | Issue | Fix |
|----------|-------|-----|
| `README.md` badge | Version `0.21.1-beta` | → `0.29.0-beta` |
| `README.md` Docker Compose example | Image `0.21.1-beta` (×2) | → `0.29.0-beta` |
| `README.md` nav + docs section | No link to website or wiki | Add `https://sublarr.de` + `https://wiki.sublarr.de` |
| `SublarrWeb/index.html` nav | No "Docs" link in navbar | Add `Docs` → `https://wiki.sublarr.de` |
| `SublarrWeb/index.html` community card | Points to `github.com/Abrechen2/sublarr/wiki` | → `https://wiki.sublarr.de` |
| `SublarrWeb/index.html` footer | No wiki link | Add `Docs` → `https://wiki.sublarr.de` |
| `SublarrWiki/content/en/home.md` | Link pill points to `https://sublarr.app` | → `https://sublarr.de` |
| `SublarrWiki/content/en/development/plugin-development.md` | Link to `https://docs.sublarr.app` | → `https://wiki.sublarr.de` |

---

## Chunk 1: Static file edits

### Task 1: Update README.md — version bumps + website/wiki links

**Files:**
- Modify: `Z:/CC/Sublarr/README.md`

- [ ] **Step 1: Version badge**

Replace:
```
[![Version](https://img.shields.io/badge/version-0.21.1--beta-teal.svg)](https://github.com/Abrechen2/sublarr/releases)
```
With:
```
[![Version](https://img.shields.io/badge/version-0.29.0--beta-teal.svg)](https://github.com/Abrechen2/sublarr/releases)
```

- [ ] **Step 2: Nav links row — add website + wiki**

Replace (line ~19):
```markdown
**[Quick Start](#-quick-start)** · **[Configuration](#️-configuration)** · **[Integrations](#-integrations)** · **[Docs](#-documentation)**
```
With:
```markdown
**[Quick Start](#-quick-start)** · **[Configuration](#️-configuration)** · **[Integrations](#-integrations)** · **[Docs](#-documentation)** · **[Website](https://sublarr.de)** · **[Wiki](https://wiki.sublarr.de)**
```

- [ ] **Step 3: Docker Compose minimal example — image tag**

Replace (first occurrence):
```yaml
    image: ghcr.io/abrechen2/sublarr:0.21.1-beta
```
With:
```yaml
    image: ghcr.io/abrechen2/sublarr:0.29.0-beta
```

- [ ] **Step 4: Docker Compose production hardening — image tag**

Replace (second occurrence):
```yaml
    image: ghcr.io/abrechen2/sublarr:0.21.1-beta
```
With:
```yaml
    image: ghcr.io/abrechen2/sublarr:0.29.0-beta
```

- [ ] **Step 5: Documentation section — add wiki row**

In the `## 📚 Documentation` table, add as the **first row** (before the existing local doc links):
```markdown
| [wiki.sublarr.de](https://wiki.sublarr.de) | Full documentation wiki — installation, user guide, API, settings, troubleshooting |
```

- [ ] **Step 6: Verify no other `0.21.1` occurrences remain**

Run: `grep -n "0\.21\.1" Z:/CC/Sublarr/README.md`
Expected: no output

---

### Task 2: Update SublarrWeb — add wiki links everywhere

**Files:**
- Modify: `Z:/CC/SublarrWeb/index.html`

- [ ] **Step 1: Add "Docs" to navbar**

In `<nav class="nav-links">`, add after the GitHub link:
```html
<a href="https://wiki.sublarr.de" class="external" target="_blank">Docs</a>
```
Result:
```html
<nav class="nav-links">
  <a href="#features">Features</a>
  <a href="#screenshots">Screenshots</a>
  <a href="#install">Install</a>
  <a href="https://github.com/Abrechen2/sublarr" class="external" target="_blank">GitHub</a>
  <a href="https://wiki.sublarr.de" class="external" target="_blank">Docs</a>
</nav>
```

- [ ] **Step 2: Fix community card "Docs" link**

Replace:
```html
<a href="https://github.com/Abrechen2/sublarr/wiki" class="community-card" target="_blank">
```
With:
```html
<a href="https://wiki.sublarr.de" class="community-card" target="_blank">
```

- [ ] **Step 3: Add "Docs" to footer links**

In `<div class="footer-links">`, add after the Releases link:
```html
<a href="https://wiki.sublarr.de" target="_blank">Docs</a>
```
Result:
```html
<div class="footer-links">
  <a href="https://github.com/Abrechen2/sublarr" target="_blank">GitHub</a>
  <a href="https://github.com/Abrechen2/sublarr/releases" target="_blank">Releases</a>
  <a href="https://wiki.sublarr.de" target="_blank">Docs</a>
  <a href="https://huggingface.co/Sublarr" target="_blank">HuggingFace</a>
  <a href="https://github.com/Abrechen2/sublarr/blob/master/LICENSE" target="_blank">GPL-3.0</a>
  <a href="https://www.paypal.com/donate?hosted_button_id=GLXYTD3FV9Y78" target="_blank">Donate</a>
</div>
```

---

### Task 3: Fix SublarrWiki content — website URL + docs URL

**Files:**
- Modify: `Z:/CC/SublarrWiki/content/en/home.md`
- Modify: `Z:/CC/SublarrWiki/content/en/development/plugin-development.md`

- [ ] **Step 1: home.md — fix link pill URL**

Replace:
```html
  <a class="link-pill" href="https://sublarr.app"><span class="lp-icon mdi mdi-web"></span>sublarr.app</a>
```
With:
```html
  <a class="link-pill" href="https://sublarr.de"><span class="lp-icon mdi mdi-web"></span>sublarr.de</a>
```

- [ ] **Step 2: plugin-development.md — fix docs URL**

Replace:
```markdown
- Documentation: [Sublarr Docs](https://docs.sublarr.app)
```
With:
```markdown
- Documentation: [Sublarr Wiki](https://wiki.sublarr.de)
```

---

## Chunk 2: Push wiki changes to live Wiki.js

The wiki disk files are NOT automatically synced to Wiki.js. After editing the two disk files above, push changes to the live wiki via GraphQL API.

**Pages to update:**
| Wiki page ID | File | Change |
|---|---|---|
| 13 | `home.md` | `sublarr.app` → `sublarr.de` link pill |
| 6 | `development/plugin-development.md` | `docs.sublarr.app` → `wiki.sublarr.de` |

### Task 4: Push home.md changes to live wiki

**Tool:** Playwright MCP browser automation → wiki.sublarr.de

- [ ] **Step 1: Navigate to wiki and extract JWT token**

```javascript
// Navigate to https://wiki.sublarr.de, then in browser console:
document.cookie.match(/jwt=([^;]+)/)[1]
```

- [ ] **Step 2: Read updated home.md content from disk**

Read: `Z:/CC/SublarrWiki/content/en/home.md`

- [ ] **Step 3: Push via GraphQL mutation**

Use page ID 13, title "Sublarr Wiki", tags []:
```javascript
const MUT = `mutation U($id:Int!,$content:String!,$description:String,$title:String!,$tags:[String]!){
  pages{update(id:$id,content:$content,description:$description,editor:"markdown",
    isPublished:true,isPrivate:false,locale:"en",tags:$tags,title:$title){
      responseResult{succeeded message}
  }}
}`;

await fetch('/graphql', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + JWT },
  body: JSON.stringify({ query: MUT, variables: {
    id: 13,
    title: "Sublarr Wiki",
    description: "Documentation for Sublarr — self-hosted subtitle manager for anime & media",
    content: /* content of home.md (strip frontmatter) */,
    tags: []
  }})
});
```

Expected: `{ "data": { "pages": { "update": { "responseResult": { "succeeded": true } } } } }`

- [ ] **Step 4: Push plugin-development.md changes to live wiki**

Use page ID 6, title "Plugin Development", tags []:
Same GraphQL mutation, content = updated plugin-development.md (strip frontmatter).

**Important:** Run sequentially (not parallel) — concurrent tag inserts cause unique constraint errors.

---

## Chunk 3: Deploy website update

After editing `SublarrWeb/index.html`, deploy to CT 130 (live) and CT 124 (internal preview).

### Task 5: Deploy updated website

- [ ] **Step 1: Deploy to CT 130 (production — sublarr.de)**

```bash
scp Z:/CC/SublarrWeb/index.html root@192.168.178.171:/tmp/sw-pub.html
ssh root@192.168.178.171 "pct push 130 /tmp/sw-pub.html /var/www/html/index.html"
```

- [ ] **Step 2: Verify live site**

```bash
curl -s https://sublarr.de | grep "wiki.sublarr.de"
```
Expected: finds the wiki link in the HTML

- [ ] **Step 3: Deploy to CT 124 (internal preview)**

```bash
scp Z:/CC/SublarrWeb/index.html root@192.168.178.171:/tmp/sw-deploy.html
ssh root@192.168.178.171 "pct push 124 /tmp/sw-deploy.html /opt/sublarr-web/index.html"
```

---

## Link Map — Final State

```
README.md (GitHub)
  ├── → https://sublarr.de           (website)
  ├── → https://wiki.sublarr.de      (full docs wiki)
  └── → local docs/ files            (detailed reference, unchanged)

sublarr.de (Website — SublarrWeb)
  ├── Nav: Docs → https://wiki.sublarr.de
  ├── Community card: Docs → https://wiki.sublarr.de
  ├── Footer: Docs → https://wiki.sublarr.de
  └── Nav: GitHub → https://github.com/Abrechen2/sublarr

wiki.sublarr.de (Wiki — SublarrWiki)
  ├── Home link-pill: Website → https://sublarr.de
  ├── Home link-pill: GitHub → https://github.com/Abrechen2/sublarr
  ├── Home link-pill: HuggingFace → https://huggingface.co/Sublarr
  └── plugin-development.md: Docs → https://wiki.sublarr.de
```

## Success Criteria

1. `grep "0\.21\.1" Z:/CC/Sublarr/README.md` → no output
2. `grep "wiki.sublarr.de" Z:/CC/SublarrWeb/index.html` → ≥3 matches (nav, card, footer)
3. `grep "sublarr.app" Z:/CC/SublarrWiki/content/en/home.md` → no output
4. `grep "docs.sublarr.app" Z:/CC/SublarrWiki/content/en/development/plugin-development.md` → no output
5. `curl -s https://sublarr.de | grep "wiki.sublarr.de"` → finds link (after deploy)
6. Wiki home page at wiki.sublarr.de shows `sublarr.de` link (not `sublarr.app`)
