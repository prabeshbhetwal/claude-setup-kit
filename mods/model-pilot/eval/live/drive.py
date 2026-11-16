#!/usr/bin/env python3
"""Drive one real Claude Code session, turn by turn, and record what ran.

Usage: drive.py --name NAME --turns turns.jsonl --out DIR [--engine PATH] [--plugin DIR]
                [--model M] [--settings JSON] [--cwd DIR] [--budget USD] [--timeout S] [--extra JSON]

Each line of turns.jsonl is {"text": "..."}. Writes DIR/NAME.json with, per turn: the
engine's result (cost, time, error), every API request the engine logged in the
transcript (model, effort, who made it), and the model-pilot log lines for the session.
"""
import argparse, glob, json, os, subprocess, sys, time, uuid
from datetime import datetime, timezone

DEFAULT_ENGINE = os.path.expanduser(
    "~/Library/Application Support/Claude/claude-code/2.1.325/485fdac4332e/claude.app/Contents/MacOS/claude")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_until_result(proc, deadline):
    events = []
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            return events, None
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        events.append(ev)
        if ev.get("type") == "result":
            return events, ev
    return events, None


def transcript_rows(session):
    root = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
    files = glob.glob(os.path.join(root, "projects", "*", session + ".jsonl"))
    rows = []
    for f in files:
        for line in open(f):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def requests_between(rows, start, end):
    out = []
    for r in rows:
        ts = r.get("timestamp") or ""
        if r.get("type") == "api-request" and start <= ts <= end:
            p = r.get("params", {})
            out.append({"ts": ts, "model": p.get("model"), "effort": (p.get("output_config") or {}).get("effort"),
                        "source": r.get("querySource")})
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--name", required=True)
    a.add_argument("--turns", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--engine", default=DEFAULT_ENGINE)
    a.add_argument("--plugin", default=None)
    a.add_argument("--model", default="claude-fable-5-2")
    a.add_argument("--settings", default=None)
    a.add_argument("--setting-sources", default=None)
    a.add_argument("--cwd", default=os.getcwd())
    a.add_argument("--budget", default="5")
    a.add_argument("--timeout", type=int, default=900)
    a.add_argument("--extra", default="[]", help="JSON list of extra engine arguments")
    o = a.parse_args()

    o.out = os.path.abspath(o.out)
    os.makedirs(o.out, exist_ok=True)
    session = str(uuid.uuid4())
    log = os.path.join(o.out, o.name + ".pilot.jsonl")
    env = dict(os.environ, MODEL_PILOT_LOG=log)
    argv = [o.engine, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--model", o.model, "--session-id", session, "--max-budget-usd", o.budget,
            "--debug-file", os.path.join(o.out, o.name + ".debug.log")]
    if o.plugin:
        argv += ["--plugin-dir", o.plugin]
    if o.settings:
        argv += ["--settings", o.settings]
    if o.setting_sources is not None:
        argv += ["--setting-sources", o.setting_sources]
    argv += json.loads(o.extra)
    turns = [json.loads(l) for l in open(o.turns) if l.strip()]

    proc = subprocess.Popen(argv, cwd=o.cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=open(os.path.join(o.out, o.name + ".stderr.txt"), "w"), text=True, bufsize=1)
    results = []
    for i, t in enumerate(turns):
        start = now_iso()
        proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": t["text"]}}) + "\n")
        proc.stdin.flush()
        events, res = read_until_result(proc, time.time() + o.timeout)
        end = now_iso()
        results.append({"turn": i, "text": t["text"][:200], "expect": t.get("expect"), "start": start, "end": end,
                        "isError": res is None or res.get("is_error", False), "costUsd": (res or {}).get("total_cost_usd"),
                        "ms": (res or {}).get("duration_ms"), "reply": ((res or {}).get("result") or "")[:600],
                        "subtype": (res or {}).get("subtype")})
        print(f"turn {i}: {'ERR' if results[-1]['isError'] else 'ok'} cost={results[-1]['costUsd']}", file=sys.stderr)
        if res is None:
            break
    proc.stdin.close()
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()

    time.sleep(1)
    rows = transcript_rows(session)
    for r in results:
        r["requests"] = requests_between(rows, r["start"], r["end"])
    pilot = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    json.dump({"name": o.name, "session": session, "argv": argv[1:], "turns": results, "pilot": pilot},
              open(os.path.join(o.out, o.name + ".json"), "w"), indent=1)
    print(os.path.join(o.out, o.name + ".json"))


if __name__ == "__main__":
    main()
