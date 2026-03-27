---
name: No Co-Authored-By in commits
description: Never add Co-Authored-By Claude attribution to git commits
type: feedback
---

Never add `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` (or any Claude attribution) to commit messages.

**Why:** User explicitly does not want Claude attribution in commits.

**How to apply:** All commits in any project for this user — omit the Co-Authored-By trailer entirely.
