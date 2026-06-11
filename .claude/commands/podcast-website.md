# Podcast Website Updater (public Cloudflare site)

Regenerates AutoBrief episode pages from newsletter HTML + audio and pushes to
the **public** site repo (`ruthships/autobrief-site`). Cloudflare Pages is
Git-connected to that repo, so a push to `main` auto-deploys to
**https://autobriefpodcast.ai**.

## How to invoke

Run from the **autobrief-site** repo directory after a newsletter is on GitHub (or locally synced):

```
/podcast-website
/podcast-website episode=10
```

---

## Repos (do not mix these up)

| Repo | Path | Branch | Purpose |
|------|------|--------|---------|
| **Content** | `~/Code/02-ai-podcast-newsletter` | `main` | Newsletters + source audio (`ruthships/ai-podcast`) |
| **Public site** | `~/Code/autobrief-site` | `main` | Cloudflare-hosted public site (`ruthships/autobrief-site`) |

> The old McKinsey Deployer repo (`~/Code/03-ai-podcast-website`, `McK-Private`)
> is **no longer the publish target**. Everything publishes to the public
> Cloudflare site now.

Set at the start of every run:

```bash
CONTENT_REPO=~/Code/02-ai-podcast-newsletter
SITE_REPO=~/Code/autobrief-site
```

---

## Site layout (important)

The public site is served by Cloudflare from the **`public/`** subdirectory
(declared in `wrangler.jsonc` → `assets.directory`). So:

- Static pages live in `public/` (e.g. `public/index.html`, `public/episode-N.html`)
- Audio lives in `public/episodes/`
- Newsletters (generator input) live in `newsletters/` at the repo root (not served)
- `scripts/generate_episodes.py` writes into `public/`

**Cloudflare hard limit: every asset must be ≤ 25 MiB.** `scripts/prepare_audio.py`
enforces this by re-encoding any oversized episode to 128 kbps. Always run it
before generating/committing.

---

## Step 1 — Pull latest from both repos

**Pre-flight: check for a dirty working tree first.**

```bash
cd $SITE_REPO
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
DIRTY=$(git status --porcelain)
echo "branch: $CURRENT_BRANCH | dirty: $([ -n "$DIRTY" ] && echo yes || echo no)"
```

- **Clean tree** → `git checkout main` and continue.
- **Dirty tree** → STOP and ask the user how to proceed (commit/stash, or run from a throwaway worktree of `main`). Do not silently stash or switch branches out from under uncommitted work.

Once clean:

```bash
cd $CONTENT_REPO && git pull origin main
cd $SITE_REPO && git checkout main && git pull origin main
```

If either pull fails or has conflicts, stop and tell the user.

---

## Step 2 — Identify the episode to update

If `episode=N` was passed, use that number. Otherwise find the newest newsletter:

```bash
ls -t $CONTENT_REPO/newsletters/ai-podcast-episode-*.html | head -1
```

Extract episode number + date from the filename, e.g.
`ai-podcast-episode-10-2026-06-10.html` → Episode 10, June 10 2026.

Confirm with the user:
> "Updating the public site for **Episode [N]** ([date]). Correct?"

---

## Step 3 — Sync inputs into the site repo

### Newsletter

```bash
cp $CONTENT_REPO/newsletters/ai-podcast-episode-[N]-*.html $SITE_REPO/newsletters/
```

### Audio

The generator discovers audio by filename pattern:
`The AI News Podcast - Episode [N] - [Month DD YYYY].(mp3|m4a)`

`/podcast-postprocess` already writes the content repo's `episodes/` file in this
exact title-case form, so normally copy it across as-is:

```bash
cp "$CONTENT_REPO/episodes/The AI News Podcast - Episode [N] - [Month DD YYYY].mp3" \
   "$SITE_REPO/public/episodes/"
```

Only legacy episodes (ep1–8) used the old kebab name; if that's all that exists,
copy it and rename to the title-case form above using the episode date.

### Enforce the 25 MiB asset limit

```bash
cd $SITE_REPO && python3 scripts/prepare_audio.py
```

This re-encodes any oversized file to 128 kbps in place (idempotent — leaves
already-small files untouched).

---

## Step 4 — Regenerate site pages

```bash
cd $SITE_REPO
python3 scripts/generate_episodes.py
```

Rebuilds:
- `public/episode-N.html` — deep-dive page (theme, summary, story sections, audio player)
- `public/index.html` — homepage hero + latest episode card
- `public/episodes.html` — full listing

Hero images come from `https://raw.githubusercontent.com/ruthships/ai-podcast/main/assets/epN_hero.jpg`.
If they 404, push assets to the content repo first (`/podcast-email` Step 6).

---

## Step 5 — Verify output

Read `public/episode-N.html` and confirm:

- [ ] Theme title matches the newsletter's `<!-- EPISODE_THEME: ... -->` marker
- [ ] Summary paragraph present (not placeholder)
- [ ] Story sections match newsletter headlines (typically 3–6)
- [ ] Audio player points to `episodes/The AI News Podcast - Episode N - ...`
- [ ] No `documentation.html` links anywhere (public site omits that page)
- [ ] Hero/thumbnail URL returns 200

Optional local preview:

```bash
cd $SITE_REPO/public && python3 -m http.server 8080
# http://localhost:8080/episode-N.html
```

---

## Step 6 — Human review checkpoint

Present a summary (episode page theme, index updated, listing updated, preview
link) and ask:

> "Ready to commit and push to `main`? This auto-deploys to autobriefpodcast.ai via Cloudflare."

**Do not push until the user explicitly approves.**

---

## Step 7 — Commit and push (triggers Cloudflare deploy)

Only commit website-related files.

```bash
cd $SITE_REPO
git add newsletters/ public/episodes/ public/episode-*.html public/index.html public/episodes.html
git commit -m "Episode [N] — update public site from newsletter [YYYY-MM-DD]"
git push origin main
```

If the push is large (audio), increase the buffer:

```bash
git -c http.postBuffer=524288000 push origin main
```

---

## Step 8 — Final confirmation

Tell the user:

- Cloudflare auto-build starts on push; live in ~1–2 min.
- Episode page: `https://autobriefpodcast.ai/episode-N.html`
- Homepage now features Episode N as the latest brief.
- Check the deploy status in the Cloudflare dashboard → Workers & Pages → `autobrief-site` → Deployments if anything looks off.

---

## Inputs this skill expects (from upstream `/podcast-email`)

| Input | Location |
|-------|----------|
| Newsletter HTML | `$CONTENT_REPO/newsletters/ai-podcast-episode-N-*.html` |
| Hero + story images | `ruthships/ai-podcast` GitHub assets (raw URLs in HTML) |
| Episode audio | `$CONTENT_REPO/episodes/` |

## Outputs

| Output | Location |
|--------|----------|
| Episode deep-dive page | `public/episode-N.html` |
| Updated homepage | `public/index.html` |
| Updated listing | `public/episodes.html` |
| Live site | `https://autobriefpodcast.ai` |

---

## Error handling

| Situation | Action |
|-----------|--------|
| No newsletter for episode N | Stop — run `/podcast-email` first |
| No matching audio file | Stop — ask user to add audio to `$CONTENT_REPO/episodes/` |
| Audio > 25 MiB after copy | `scripts/prepare_audio.py` handles it; if it still fails, re-encode manually to ≤128 kbps |
| Cloudflare build fails "Asset too large" | An asset exceeds 25 MiB — run `scripts/prepare_audio.py`, recommit |
| Generator finds 0 story sections | Check newsletter HTML; parser expects `heading_block block-1` + `paragraph_block block-2` pairs after `<!-- HEADLINE` |
| Hero image 404 | Push `epN_hero.jpg` to content repo assets |
| Push rejected / timeout | Retry with `http.postBuffer=524288000` |
