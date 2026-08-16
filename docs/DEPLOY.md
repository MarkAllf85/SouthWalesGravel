---
name: deploy
description: Publishing South Wales Gravel Routes to GitHub Pages
type: reference
updated: 2026-08-16
---

# Deploying

The repository is https://github.com/MarkAllf85/SouthWalesGravel and it is public. Public means anyone with the link, or who stumbles across the repository, can see every route. Nothing is indexed or linked from anywhere, so in practice the audience is whoever you send the link to.

A workflow at `.github/workflows/pages.yml` publishes the `site/` folder only, so the raw exports in `data/` and these documents stay in the repository but out of the served site. That is why the site URL is clean rather than ending in `/site/`.

## Why Claude cannot push this

Claude reaches GitHub through a proxy that only injects credentials for repositories attached to the session. `SouthWalesGravel` is not one of them, so the push is refused before it reaches GitHub:

    remote: access denied by the git proxy: MarkAllf85/SouthWalesGravel is not in
    this session's authorized repository set

Reading works, because the repository is public. Writing does not. Attaching a repository mid-session is not something Claude can do for itself. Either attach it on your side and ask Claude to retry, or run the push yourself with the commands below.

## Pushing it yourself

The repository already has one commit containing a README. These commands adopt that history without disturbing any of your files, then commit everything on top of it.

Open a terminal in this folder and run:

    git init -b main
    git remote add origin https://github.com/MarkAllf85/SouthWalesGravel.git
    git fetch origin
    git reset origin/main
    git add -A
    git commit -m "South Wales Gravel Routes: interactive map, ingest pipeline and 26 routes"
    git push -u origin main

`git reset origin/main` moves the branch pointer onto the remote commit and leaves your working tree completely alone, so nothing is overwritten or lost. It is the step that avoids the unrelated-histories error.

Then in the repository on GitHub, open Settings, Pages, and set Source to **GitHub Actions**. The workflow runs on the next push, and the URL appears in the Actions log and on the Pages settings screen. It will be:

    https://markallf85.github.io/SouthWalesGravel/

## Every time after

    python scripts\build.py
    git add -A
    git commit -m "Add <route name>"
    git push

Pages redeploys in about a minute.

## Before you push, check the privacy audit still passes

Any change to the route files should be followed by the exclusion audit. Nothing should come within 200 m of either zone. See `docs/WORKFLOW.md` for the full pipeline and `docs/DECISIONS.md` entries 13 and 14 for why.

## A note on OneDrive

This folder is inside OneDrive. Git and OneDrive both watch the same files, and OneDrive will happily sync the `.git` directory, which is wasted bandwidth and an occasional source of lock contention. It works, but if the repository starts behaving strangely the first thing to try is moving the project out of OneDrive and letting git be the sync mechanism instead.

Do not let a Claude session run git write commands against this folder. The device bridge cannot delete files, and git deletes constantly, so it leaves orphaned lock files that stop Windows git entirely. That happened once already and the wreckage is in `_to_delete\broken-git`.
