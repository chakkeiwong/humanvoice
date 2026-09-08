# Git Commit and Push Workflow for Agents

This guide explains how to commit and push changes when working on repositories that have authentication pre-configured.

## Prerequisites

The repository should already be cloned and authenticated. Check with:

```bash
git remote -v
git config user.name
git config user.email
```

## Three-Step Workflow

### 1. Stage Your Changes

```bash
# Navigate to repository root
cd /path/to/your/repo

# Check what changed
git status

# Stage specific files (recommended)
git add path/to/file1.py
git add path/to/file2.py

# OR stage all changes (review carefully first)
git add -A

# Review what's staged
git status --short
git diff --cached --stat
```

**Important:** Exclude temporary/generated files before staging:
```bash
# Reset accidentally staged files
git reset HEAD validation_results/
git reset HEAD __pycache__/
git reset HEAD *.pyc
```

### 2. Commit with Descriptive Message

```bash
git commit -m "Brief summary in imperative mood (max 50 chars)

Detailed explanation of changes:
- What changed and why
- Impact on the system
- Any important context

Test status: [all passing | X tests added | etc]

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

**Commit message best practices:**
- **First line:** Imperative mood, <50 characters
  - ✓ "Add token validation preprocessing"
  - ✗ "Added some validation stuff"
- **Body:** Blank line, then details
- **Include:** Test status, breaking changes, related issues
- **Trailer:** Always add Co-Authored-By line

**Examples:**

```bash
# Simple fix
git commit -m "Fix regex pattern for JSON extraction

The closing fence didn't require newline, causing extraction to fail.
Changed \n\`\`\` to \s*\`\`\` in both patterns.

All 219 tests passing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

```bash
# Feature addition
git commit -m "Add blueprint validation command for token ceiling checks

NEW COMMAND: hv validate-blueprint checks subsections fit within 8192
token ceiling before drafting.

- Conservative 4.0 tokens/word with 20% variance
- Safe ceiling: 7372 tokens (90% of max)
- Suggests split sizes for oversized subsections

Production requirement: 100% success rate for 300K users.

Tests: 6 new tests added, all passing (225 total).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

### 3. Push to Remote

```bash
# Push to main branch
git push origin main

# OR push to feature branch
git push origin feature-branch-name
```

**Expected output:**
```
To github.com:username/repo.git
   abc1234..def5678  main -> main
```

No authentication prompts should appear if tokens are configured correctly.

### 4. Verify Success

```bash
# Check remote received your commit
git log --oneline origin/main -5

# Verify working tree is clean
git status
```

## Troubleshooting

### Authentication Required
If you see "Authentication failed" or username/password prompts:

```bash
# Check remote URL uses HTTPS
git remote -v

# Should show: https://github.com/username/repo.git
# NOT: git@github.com:username/repo.git
```

The system admin needs to configure Git credentials. Don't attempt to enter tokens manually.

### Merge Conflicts

```bash
# Pull latest changes first
git pull origin main

# Resolve conflicts in editor, then:
git add resolved-file.py
git commit -m "Merge remote changes"
git push origin main
```

### Accidentally Committed Large Files

```bash
# Remove from staging before commit
git reset HEAD large-file.dat

# Remove from last commit (if not pushed yet)
git reset --soft HEAD~1
git reset HEAD large-file.dat
git commit -m "your message"
```

## Common Patterns

### Work on Feature Branch

```bash
# Create and switch to feature branch
git checkout -b feature-name

# Make changes, commit
git add .
git commit -m "message"

# Push feature branch
git push origin feature-name

# Later: merge to main (after review/approval)
git checkout main
git merge feature-name
git push origin main
```

### Check What Will Be Pushed

```bash
# See commits not yet on remote
git log origin/main..HEAD

# See diff of changes
git diff origin/main..HEAD
```

### Amend Last Commit (before push)

```bash
# Fix typo in commit message
git commit --amend -m "corrected message"

# Add forgotten file to last commit
git add forgotten-file.py
git commit --amend --no-edit
```

⚠️ **Never amend commits already pushed to shared branches**

## Repository-Specific Notes

Different repositories may have:
- **Branch protection:** Require PRs instead of direct push to main
- **CI/CD checks:** Wait for tests to pass before merging
- **Code review:** Require approval from maintainers
- **.gitignore patterns:** Project-specific files to exclude

Always check the project's CONTRIBUTING.md or README.md for specific workflows.

## Quick Reference

```bash
# Status check
git status

# Stage and commit
git add -A
git commit -m "Summary\n\nDetails\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

# Push
git push origin main

# Verify
git log --oneline origin/main -3
```

---

**For humanvoice repository specifically:** https://github.com/chakkeiwong/humanvoice
