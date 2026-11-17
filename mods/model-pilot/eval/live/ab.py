#!/usr/bin/env python3
"""Side by side: the same tasks with model-pilot on and off, judged by hidden tests.

Usage: ab.py --out DIR --venv DIR [--arms off,pilot] [--only id,id] [--workers 2] [--menu claude-fable-5-2]

--venv: a virtualenv with pytest; its bin/ goes first on PATH so `python3 -m pytest` works in every session.

Each task runs in a fresh copy of a small Python project, one session per task and arm,
with the user's settings left out (both arms alike) so the comparison is routing only.
Arm "off" runs the menu model with no mod; arm "pilot" loads the mod with that menu model.
A task passes on hidden tests the session never saw, or on a reply that matches `answer`.
Cost is the engine's own total_cost_usd. Writes DIR/ab.json and prints a table.
"""
import argparse, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(os.path.dirname(HERE))
CALC = "def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    return a / b\n"
TEST = "from calc import add, div\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\ndef test_div():\n    assert div(6, 3) == 2\n"
ALLOW = ["Read", "Edit", "Write", "Grep", "Glob", "Bash(python3:*)", "Bash(python3 -m pytest:*)",
         "Bash(ls:*)", "Bash(cat:*)", "Bash(wc:*)", "Bash(grep:*)"]


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def fixture(path, task):
    os.makedirs(path, exist_ok=True)
    files = {"calc.py": CALC, "test_calc.py": TEST, **task.get("files", {})}
    for name, body in files.items():
        open(os.path.join(path, name), "w").write(body)
    git(path, "init", "-q")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "init")


def judge(task, repo, reply, py):
    if "answer" in task:
        return re.search(task["answer"], reply.strip()) is not None, reply.strip()[:60]
    hidden = os.path.join(repo + ".hidden")
    os.makedirs(hidden, exist_ok=True)
    f = os.path.join(hidden, "test_hidden_" + task["id"].replace("-", "_") + ".py")
    open(f, "w").write(task["hidden"])
    r = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", f], cwd=repo,
                       env=dict(os.environ, PYTHONPATH=repo), capture_output=True, text=True, timeout=300)
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    return r.returncode == 0, tail[:60]


def run(o, task, arm, rep=1):
    name = f"{task['id']}.{arm}.r{rep}"
    repo = os.path.join(o.out, "repos", name)
    fixture(repo, task)
    turns = os.path.join(o.out, "repos", name + ".turns.jsonl")
    open(turns, "w").write(json.dumps({"text": task["prompt"]}) + "\n")
    settings = {"permissions": {"allow": ALLOW}}
    argv = [sys.executable, os.path.join(HERE, "drive.py"), "--name", name, "--turns", turns, "--out", o.out,
            "--model", o.menu, "--cwd", repo, "--budget", "3", "--timeout", "900"]
    if arm == "full":  # the user's own settings, plugins, hooks and MCP servers
        argv += ["--setting-sources", "user,project,local", "--settings", json.dumps(settings),
                 "--extra", json.dumps(["--permission-mode", "acceptEdits"])]
    else:
        argv += ["--setting-sources", "project", "--settings", json.dumps(settings),
                 "--extra", json.dumps(["--strict-mcp-config", "--permission-mode", "acceptEdits"])]
    if arm == "pilot":
        argv += ["--plugin", MOD]
    env = dict(os.environ, PATH=os.path.join(o.venv, "bin") + os.pathsep + os.environ["PATH"])
    subprocess.run(argv, capture_output=True, text=True, env=env)
    res = json.load(open(os.path.join(o.out, name + ".json")))
    t = res["turns"][0]
    ok, why = judge(task, repo, t["reply"], os.path.join(o.venv, "bin", "python3"))
    models = sorted({r["model"] for r in t["requests"]})
    pick = next((p for p in res["pilot"] if p.get("kind") == "turn"), {})
    return {"task": task["id"], "arm": arm, "rep": rep, "usage": t.get("usage"), "pass": ok, "why": why, "costUsd": t["costUsd"] or 0, "ms": t["ms"],
            "isError": t["isError"], "models": models, "picked": pick.get("picked"), "effort": pick.get("picked_effort"),
            "judge": pick.get("judge"), "pilotCost": pick.get("cost_usd")}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--out", required=True)
    a.add_argument("--arms", default="off,pilot")
    a.add_argument("--only", default="")
    a.add_argument("--workers", type=int, default=2)
    a.add_argument("--venv", required=True)
    a.add_argument("--reps", type=int, default=1)
    a.add_argument("--menu", default="claude-fable-5-2")
    o = a.parse_args()
    tasks = json.load(open(os.path.join(HERE, "tasks.json")))
    if o.only:
        tasks = [t for t in tasks if t["id"] in o.only.split(",")]
    jobs = [(t, arm, k) for k in range(1, o.reps + 1) for t in tasks for arm in o.arms.split(",")]
    with ThreadPoolExecutor(o.workers) as ex:
        rows = list(ex.map(lambda j: run(o, *j), jobs))
    json.dump(rows, open(os.path.join(o.out, "ab.json"), "w"), indent=1)
    for r in rows:
        print(f"{r['task']:15} {r['arm']:5} {'PASS' if r['pass'] else 'FAIL'} ${r['costUsd']:.4f} {r['ms']}ms "
              f"pick={r['picked']}/{r['effort']} judge={r['judge']} ran={r['models']} :: {r['why']}")
    for arm in o.arms.split(","):
        rs = [r for r in rows if r["arm"] == arm]
        print(f"TOTAL {arm}: {sum(r['pass'] for r in rs)}/{len(rs)} pass, ${sum(r['costUsd'] for r in rs):.3f}, "
              f"{sum(r['ms'] or 0 for r in rs) / 1000:.0f}s")


if __name__ == "__main__":
    main()
