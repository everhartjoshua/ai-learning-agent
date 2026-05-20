# ── Start a new piece of work ───────────────────────────────
git checkout main
git pull                                  # always sync before branching
git checkout -b feat/short-description    # create + switch in one step

# ── Save work-in-progress (any time during editing) ─────────
git status                                # see what changed
git add <files>                           # or: git add .  for everything
git commit -m "Short imperative message"

# ── Push the branch for the first time ──────────────────────
git push -u origin feat/short-description

# ── Push subsequent commits on the same branch ──────────────
git push                                  # -u only needed once

# ── After the PR is merged on GitHub ────────────────────────
git checkout main
git pull                                  # bring the merged commit local
git branch -d feat/short-description      # delete LOCAL branch
                                          # remote branch is auto-deleted by GitHub

# ── Common "I messed up" recovery ───────────────────────────
git status                                # FIRST: see what state you're in
git log --oneline -5                      # see recent commits
git reflog                                # see EVERYTHING you've done (safety net)

# Committed to wrong branch (e.g. main):
git branch feature-name                   # mark the commit on a new branch
git reset --hard HEAD~1                   # rewind the wrong branch
git checkout feature-name                 # switch to the new branch
git push -u origin feature-name           # push it

# Need to throw away local changes (uncommitted):
git restore .                             # discard unstaged changes
git checkout -- .                         # older syntax, same effect