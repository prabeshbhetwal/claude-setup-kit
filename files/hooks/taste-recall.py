#!/usr/bin/env python3
"""UserPromptSubmit hook: bring back the user's approved taste rules that fit this prompt (~/.claude/taste/rules.json).
BM25 pre-filter, UI gate, Jev confirms any BM25 hit (1.5 s cap). At most 4 rules, 600 chars.
Silent when nothing fits. Fails open: any error prints nothing. Logic: ~/.claude/monitor/bin/taste_store.py.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.expanduser("~/.claude/monitor/bin"))


def main():
    t0 = time.time()
    try:
        import taste_store as T
        if not os.path.exists(T.RULES):
            return
        prompt = json.load(sys.stdin).get("prompt", "")
        rules = T.recall(prompt)
        if not rules:
            return
        text = T.note(rules)
        T.log_recall([r["id"] for r in rules], len(text), int(1000 * (time.time() - t0)))
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}))
    except Exception:
        return


if __name__ == "__main__":
    main()
