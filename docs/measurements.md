# Measurements (from the author's setup)

All from the author's own Mac on 2026-11-15. One machine, small samples.

| What | Before | After | Note |
|---|---|---|---|
| First request of a fresh `claude -p` session (Haiku, same prompt) | 70,728 tokens | 69,136 tokens | −1,592 after removing redundant skills, agents and commands; one run each |
| `/context` total | 40.7k | 39.5k | Same trim |
| Skill-list entries | 763 | 651 | Same trim; 86 skills got their descriptions back |
| Helper agent start-up cost: all-tools agent vs `haiku-lean` | ~72k | ~14k | Why the kit ships lean agents |
| Delegating a small 3-lookup job to a cheaper model vs doing it in place | ≈ same | ≈ same | **No saving.** The main chat's own context dominates. Savings come from big tool-heavy helper jobs |

**Not measured:**
- Per-tool savings for RTK, context-mode, Caveman, CodeGraph or Graphify in isolation. They are included because they cut output size by design, not because each one was benchmarked.
- The effect of the 15 Nov 2026 trim on real weekly usage. The before/after comparison (`token-compare.py`) has no after-week data until 23 Nov 2026.
- The connector-list saving in the desktop app (an **estimate** of about 3k tokens per session).

Measure your own: `python3 ~/.claude/hooks/token-scorecard.py 30`, and `python3 ~/.claude/hooks/token-compare.py` a week after installing.
