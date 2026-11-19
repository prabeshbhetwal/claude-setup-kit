"""Fixture checks for setup-monitor and house rules: python3 setup-monitor.py selftest. No network."""
import json
import os
import tempfile
import time

import monitor_collect as C
import monitor_markers as M
import monitor_scan as S


def line(**o):
    return json.dumps(o) + "\n"


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


def fixture(d, t0):
    u = lambda n, cr, cc, out: {"input_tokens": n, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cc, "output_tokens": out}
    rows = [
        line(type="user", timestamp=iso(t0), cwd="/srv/proj", message={"role": "user", "content": "make the hero section less busy"}),
        line(type="attachment", timestamp=iso(t0 + 1), attachment={"type": "hook_additional_context", "hookEvent": "UserPromptSubmit", "content": ["x" * 398]}),
        line(type="assistant", timestamp=iso(t0 + 2), message={"id": "m1", "model": "claude-opus-5-5", "usage": u(10, 0, 100_000, 50),
             "content": [{"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "/srv/proj/Hero.tsx"}}]}),
        line(type="assistant", timestamp=iso(t0 + 2), message={"id": "m1", "model": "claude-opus-5-5", "usage": u(10, 0, 100_000, 60), "content": []}),
        line(type="user", timestamp=iso(t0 + 3), message={"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": False, "content": "ok"}]}),
        line(type="assistant", timestamp=iso(t0 + 4), message={"id": "m2", "model": "claude-opus-5-5", "usage": u(10, 100_000, 0, 40),
             "content": [{"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "npm test"}}]}),
        line(type="user", timestamp=iso(t0 + 5), message={"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "is_error": True, "content": "1 failed"}]}),
        line(type="user", timestamp=iso(t0 + 6), message={"role": "user", "content": "<task-notification>done</task-notification>"}),
        line(type="user", timestamp=iso(t0 + 7), message={"role": "user", "content": [{"type": "text", "text": "no, that's wrong, keep the old spacing"}]}),
        line(type="assistant", timestamp=iso(t0 + 8), message={"id": "m3", "model": "claude-sonnet-5-5", "usage": u(10, 100_000, 0, 20),
             "content": [{"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": "npm test"}}]}),
        line(type="user", timestamp=iso(t0 + 9), message={"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t3", "is_error": False, "content": "Fact-Forcing Gate: blocked"}]}),
        line(type="system", subtype="compact_boundary", timestamp=iso(t0 + 10)),
    ]
    p = os.path.join(d, "sess.jsonl")
    open(p, "w").writelines(rows)
    return p


def run():
    with tempfile.TemporaryDirectory() as d:
        t0 = time.time() - 3600
        p = fixture(d, t0)
        r = S.scan(p, t0 - 10)
        assert len(r["reqs"]) == 3 and r["reqs"]["m1"][2]["output_tokens"] == 60, r["reqs"]
        assert [t[1][:4] for t in r["turns"]] == ["make", "no, "], r["turns"]
        assert r["turns"][0][2] == 400 and r["req_turn"] == {"m1": 0, "m2": 0, "m3": 1}
        assert S.is_correction(r["turns"][1][1]) and not S.is_correction(r["turns"][0][1])
        # opus: 10 in + 60 out + 100k 1-hour cache write (2x of $4/M)
        assert abs(S.cost("claude-opus-5-5", {"input_tokens": 10, "output_tokens": 60, "cache_creation_input_tokens": 100_000}) - 0.80124) < 1e-6
        W, cwds = C.collect(t0 - 10, files=[p])
        wk = C.week_of(t0)
        rec = M.markers(W[wk], {"rtk_saved": 5, "ctx_kept_bytes": 40, "jev_failopen": 0, "git": (10, 1)}, wk)
        m = rec["markers"]
        assert rec["n"]["turns"] == 2 and rec["n"]["sessions_work"] == 1 and cwds == {"/srv/proj"}
        assert m["Q1"] == 50.0 and m["Q3"] == 33.33 and m["Q4"] == 33.33 and m["Q5"] == 50.0 and m["Q6"] == 1.0, m
        assert m["T1"] == 100_010 and m["T8"] == 50.0 and m["T9"] == 50 and m["G1"] == 10.0 and m["S2"] == 10, m
        assert m["C6"] < 100 and m["C4"] > 0.8
        assert C.is_headless("/private/var/folders/x/T/tmp1") and C.is_headless("/a/scratch-2026-11-14-x") and not C.is_headless("/srv/p")
        weeks = {wk: rec}
        assert "| Q1 |" in M.weekly_md(wk, weeks, []) and "n small" in M.weekly_md(wk, weeks, [])
        house_rules_checks(d)
    print("ok")


def house_rules_checks(d):
    os.environ["HOUSE_RULES_HOME"] = d
    import importlib
    import house_rules_store as T
    importlib.reload(T)
    rules = [{"id": "r1", "rule": "Avoid purple gradients and neon glows on landing pages.", "tags": ["colour", "ui"],
              "keywords": ["purple", "gradient", "neon", "landing"], "status": "active"},
             {"id": "r2", "rule": "Commit messages in plain English, no emoji.", "tags": ["workflow"], "keywords": ["commit", "message"], "status": "active"}]
    hit = T.recall("redesign the landing page hero, maybe a gradient background", rules, use_jev=False)
    assert [r["id"] for r in hit] == ["r1"], hit
    assert T.recall("what is the weather in sydney today", rules, use_jev=False) == []
    assert T.recall("ok", rules, use_jev=False) == []
    assert len(T.note(hit)) < 600
    assert "<path>" in T.redact("see /srv/me/app/src/Hero.tsx now") and "<email>" in T.redact("mail a" + "@b.com")  # split so the repo scan sees no address
    assert T.week_markers(0, time.time() + 1, 10)["P1"] == 0.0
    jev_child_checks(d, T)


FAKE_JEV = """import concurrent.futures, json, time
def policy(): return {{"skip_paths": [{skip!r}]}}
def skipped(pol, cwd): return cwd.startswith(pol["skip_paths"][0])
def noul(site, q, items, ctx="", cwd=""):  # an executor like the real jev_lib: its worker is joined at exit
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        pool.submit(time.sleep, {delay}).result()
    open({sent!r}, "a").write(json.dumps(items) + "\\n")
    return [0.9] * len(items)
"""


def jev_child_checks(d, T):
    """Jev runs in a child: skip_paths sentences never reach it, and a slow Jev cannot hold the prompt."""
    import subprocess
    import sys
    sent, fast, slow = (os.path.join(d, x) for x in ("sent.jsonl", "fast", "slow"))
    for folder, delay in ((fast, 0), (slow, 10)):
        os.makedirs(folder)
        open(os.path.join(folder, "jev_lib.py"), "w").write(FAKE_JEV.format(skip="/srv/client", delay=delay, sent=sent))
    T.JEV_DIR = fast
    probs = T.jev_probs("house-rules-mine", "q", ["keep it calm", "client secret plan", "no folder"], "", timeout=20,
                        cwds=["/srv/mine", "/srv/client/app", ""])
    assert probs == [0.9, None, None], probs
    assert open(sent).read().strip() == json.dumps(["keep it calm"]), "skip_paths or unknown-folder item sent"
    # whole process (as the recall hook runs it) must exit near the 1.5 s cap with a 10 s Jev
    code = (f"import sys; sys.path.insert(0, {os.path.dirname(os.path.abspath(T.__file__))!r}); import house_rules_store as T; "
            f"T.JEV_DIR = {slow!r}; print(T.jev_probs('house-rules-recall', 'q', ['a'], ''))")
    t = time.time()
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30).stdout.strip()
    took = time.time() - t
    assert out == "None" and took < 2.5, (out, took)
