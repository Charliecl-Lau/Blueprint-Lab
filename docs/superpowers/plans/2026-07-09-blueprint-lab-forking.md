# Blueprint Lab Forking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `C:\Users\yeekw\Documents\Blueprint-Lab` as a standalone Blueprint Lab repository forked from the current Blueprint code before any migration code is changed.

**Architecture:** This plan only prepares the workspace. It protects the existing Blueprint production code and any user changes by exporting the current committed Blueprint tree into a new local repository for Blueprint Lab, then wiring that repository for an independent GitHub remote while keeping optional upstream lineage back to Blueprint.

**Tech Stack:** Git, PowerShell.

---

## File Structure

- No application files are edited by this plan.
- The output is a separate local repository at `C:\Users\yeekw\Documents\Blueprint-Lab`.
- The new repository starts from the current committed `HEAD` of `C:\Users\yeekw\Documents\Blueprint`.
- Uncommitted files in `C:\Users\yeekw\Documents\Blueprint` are not copied unless the user explicitly confirms they belong in Blueprint Lab.
- The new repository should use its own `origin` remote for Blueprint Lab. The original Blueprint remote may be added as `upstream` for lineage only.

---

### Task 1: Create the Standalone Blueprint Lab Repository

**Files:**
- No source edits.

- [ ] **Step 1: Check repository status with the safe-directory override**

Run:

```powershell
git -c safe.directory=C:/Users/yeekw/Documents/Blueprint status --short
git -c safe.directory=C:/Users/yeekw/Documents/Blueprint branch --show-current
```

Expected: the command prints the current branch and any dirty files. Do not revert, delete, or overwrite any listed work.

- [ ] **Step 2: Confirm the fork source commit**

Run:

```powershell
git -c safe.directory=C:/Users/yeekw/Documents/Blueprint rev-parse HEAD
git -c safe.directory=C:/Users/yeekw/Documents/Blueprint log -1 --oneline
```

Expected: Git prints the exact commit that will seed the standalone Blueprint Lab repository. Treat this commit as the fork point.

- [ ] **Step 3: Stop if uncommitted changes must be included**

If `status --short` showed dirty files, do not silently copy them into Blueprint Lab. Ask the user whether those files belong in Blueprint Lab.

If the user says the dirty files are unrelated, continue from committed `HEAD` only.

If the user says some dirty files belong in Blueprint Lab, first make an explicit commit in `C:\Users\yeekw\Documents\Blueprint` using the required commit-message format, then use that new commit as the fork point. Do not include unrelated dirty files.

- [ ] **Step 4: Create the standalone repository folder from committed HEAD**

Run from `C:\Users\yeekw\Documents\Blueprint`:


```powershell
if (Test-Path C:/Users/yeekw/Documents/Blueprint-Lab) { throw "C:/Users/yeekw/Documents/Blueprint-Lab already exists. Stop and inspect it before continuing." }
git -c safe.directory=C:/Users/yeekw/Documents/Blueprint archive --format=tar HEAD -o C:/tmp/blueprint-lab-seed.tar
New-Item -ItemType Directory -Path C:/Users/yeekw/Documents/Blueprint-Lab
tar -xf C:/tmp/blueprint-lab-seed.tar -C C:/Users/yeekw/Documents/Blueprint-Lab
```

Expected: `C:\Users\yeekw\Documents\Blueprint-Lab` exists and contains the committed Blueprint source tree without the original `.git` directory.

- [ ] **Step 5: Initialize Blueprint Lab as its own Git repository**

Run:

```powershell
Set-Location C:/Users/yeekw/Documents/Blueprint-Lab
git init
git checkout -b main
git add .
git commit -m "chore: initialize Blueprint Lab fork" -m "This creates Blueprint Lab as a standalone repository seeded from the current committed Blueprint source tree. The separate repository lets the research-platform migration evolve independently without changing the production Blueprint project."
```

Expected: Git creates a new repository with an initial commit on `main`.

- [ ] **Step 6: Add the original Blueprint remote as upstream**

Run:

```powershell
Set-Location C:/Users/yeekw/Documents/Blueprint-Lab
git remote add upstream https://github.com/Charliecl-Lau/Blueprint.git
git remote -v
```

Expected: `upstream` points to `https://github.com/Charliecl-Lau/Blueprint.git` for fetch and push. Do not push to `upstream`.

- [ ] **Step 7: Create or connect the Blueprint Lab origin remote**

Create a new empty GitHub repository named `Blueprint-Lab` under the `Charliecl-Lau` GitHub account. Do not initialize it with a README, license, or `.gitignore`.

After the repository exists, run:

```powershell
Set-Location C:/Users/yeekw/Documents/Blueprint-Lab
git remote add origin https://github.com/Charliecl-Lau/Blueprint-Lab.git
git remote -v
```

Expected: `origin` points to the new Blueprint Lab repository, and `upstream` points to the original Blueprint repository.

- [ ] **Step 8: Push the standalone Blueprint Lab repository**

Run:

```powershell
Set-Location C:/Users/yeekw/Documents/Blueprint-Lab
git push -u origin main
```

Expected: Git pushes the initial standalone Blueprint Lab commit to the new Blueprint Lab remote and sets `main` to track `origin/main`.

- [ ] **Step 9: Confirm the fork repository**

Run:

```powershell
Set-Location C:/Users/yeekw/Documents/Blueprint-Lab
git status --short
git branch --show-current
git remote -v
git log -1 --oneline
```

Expected:
- `git status --short` prints nothing.
- `git branch --show-current` prints `main`.
- `origin` points to the new Blueprint Lab repository.
- `upstream` points to the original Blueprint repository.
- `git log -1 --oneline` shows `chore: initialize Blueprint Lab fork`.

- [ ] **Step 10: Record commit-message rules for all later migration commits**

Every commit must have a subject and a body. Never add `Co-Authored-By` or any other attribution trailer.

Example:

```text
refactor: introduce experiment domain models

This replaces production run/control-set concepts with research
experiment and condition records so every generated assessment is
traceable to an explicit experimental condition.
```

- [ ] **Step 11: Stop**

Do not make migration source edits in this plan. After this plan is complete, execute the Blueprint Lab research-platform migration plan from `C:\Users\yeekw\Documents\Blueprint-Lab`.

---

## Self-Review

- Spec coverage: This plan creates a new standalone local repository named Blueprint Lab from the current Blueprint code and prepares it for its own GitHub remote.
- Safety: It explicitly checks dirty state and prevents unrelated uncommitted user work from being silently copied.
- Scope: Runtime migration begins in the main Blueprint Lab migration plan after this standalone repository setup is complete.
