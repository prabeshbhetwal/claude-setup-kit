"""Shared Jev (TypeSafe) gate for hooks: one fast call, fail-open, every decision logged.

Used by the Cognee recall filter, the Cognee save gate and jev-weekly.py.
- Policy: ~/.claude/jev/policy.json (thresholds, skip_paths, enabled). Edit there, not here.
- Log:    ~/.claude/jev/decisions.jsonl (site, question, p, kept, item preview). jev-weekly.py
          reads it to report calibration and suggest thresholds; nothing auto-tunes.
Fail-open: no key, timeout, HTTP error, secret-looking input or a skipped path -> None,
and the caller keeps its normal behaviour. Never prints or logs the API key.
"""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import queue
import threading
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
DIR = HOME / ".claude/jev"
POLICY = DIR / "policy.json"
LOG = DIR / "decisions.jsonl"
DEFAULTS = {
    "enabled": True,
    "timeout_s": 3.0,
    "recall_min": 0.50,   # drop recalled memory entries below this relevance
    "save_min": 0.25,     # skip storing prompts/answers below this durability
    "codegraph_min": 0.40,  # skip CodeGraph injection when the prompt is not about code
    "shadow_flag": 0.70,  # shadow sites: p at or above this counts as a flag in the weekly report
    "skip_paths": [],     # cwd prefixes never sent to TypeSafe (client/confidential repos)
    "sites_off": [],      # sites the user did not agree to send (install.sh asks): house-rules-recall, house-rules-mine
}

_loader = importlib.machinery.SourceFileLoader("jev_cli", str(HOME / ".local/bin/jev"))
_jev = importlib.util.module_from_spec(importlib.util.spec_from_loader("jev_cli", _loader))
_loader.exec_module(_jev)


def policy() -> dict:
    try:
        raw = json.loads(POLICY.read_text())
    except (OSError, ValueError):
        return {**DEFAULTS, "unreadable": True}  # consent is recorded there: without it, optional sites stay off
    if not isinstance(raw, dict):  # [] or null is no policy at all: send nothing
        return {**DEFAULTS, "unreadable": True, "enabled": False}
    return {**DEFAULTS, **raw}


def _allowed(pol: dict, cwd: str, site: str = "") -> bool:
    if pol.get("unreadable") and site not in ("", "cli"):
        return False  # policy.json missing or corrupt: never send for a hook or plugin on a guess
    return pol["enabled"] is True and site not in pol.get("sites_off", []) and not skipped(pol, cwd)


def skipped(pol: dict, cwd: str) -> bool:
    """cwd is inside a skip_paths entry (the folder itself or below it, not a sibling sharing its prefix)."""
    cwd = os.path.realpath(cwd or os.getcwd())
    roots = [os.path.realpath(os.path.expanduser(p)) for p in pol.get("skip_paths", []) if p]
    return any(cwd == r or cwd.startswith(r.rstrip(os.sep) + os.sep) for r in roots)


def _post(body: dict, timeout: float) -> dict:
    key = _jev.get_key()
    if not key:
        raise RuntimeError("no key")
    req = urllib.request.Request(_jev.URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_jev.TLS) as res:
        return json.load(res)


def log(site: str, question: str, item: str, p: float, kept: bool, **extra) -> None:
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        rec = {"ts": int(time.time()), "site": site, "q": question[:120], "p": round(p, 3), "kept": kept,
               "id": hashlib.sha1(item.encode()).hexdigest()[:12], "item": item[:240], **extra}
        if LOG.exists() and LOG.stat().st_size > 5_000_000:  # bounded: it keeps previews of commands and emails
            LOG.replace(DIR / "decisions.jsonl.1")
        with LOG.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def noul(site: str, question: str, items: list[str], context: str = "", cwd: str = "") -> list[float] | None:
    """P(yes) per item, in order, from one parallel batch of calls; None means "don't gate"."""
    pol = policy()
    if not items:
        return None
    if not _allowed(pol, cwd, site):
        return _failopen(site, "disabled by policy or skip_paths", cwd)
    if _jev.SECRET.search("\n".join(items) + context):
        return _failopen(site, "credential-looking input not sent", cwd)
    batches = [list(range(i, min(i + _jev.BATCH, len(items)))) for i in range(0, len(items), _jev.BATCH)]

    def run(idx):
        state = {"items": {str(i): items[i] for i in idx}}
        if context:
            state["context"] = context
        qs = {str(i): _jev.question("noul", question, i, {}, []) for i in idx}
        return _post({"state": state, "model": _jev.MODEL, "questions": qs}, pol["timeout_s"])["answers"]

    todo, done = queue.Queue(), queue.Queue()
    for b in batches:
        todo.put(b)

    def worker():
        while not todo.empty():
            try:
                done.put(run(todo.get_nowait()))
            except queue.Empty:
                return
            except Exception as e:
                done.put(e)

    # daemon threads, not a `with ThreadPoolExecutor`: leaving that block waits for a stalled request, so the deadline would not hold
    for _ in range(min(4, len(batches))):
        threading.Thread(target=worker, daemon=True).start()
    deadline = time.monotonic() + pol["timeout_s"] + 0.5
    try:
        answers = {}
        for _ in batches:
            got = done.get(timeout=max(0.0, deadline - time.monotonic()))
            if isinstance(got, Exception):
                raise got
            answers.update(got)
        return [float(answers[str(i)]["noul"]) for i in range(len(items))]
    except Exception as e:
        return _failopen(site, f"{type(e).__name__}: {str(e)[:160]}", cwd)


def _failopen(site: str, reason: str, cwd: str = "") -> None:
    """Record why a gate fell open (no Jev answer) in failopen.log, so silent skips stay diagnosable."""
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        f = DIR / "failopen.log"
        if f.exists() and f.stat().st_size > 1_000_000:
            f.replace(DIR / "failopen.log.1")
        with f.open("a") as fh:
            fh.write(json.dumps({"ts": int(time.time()), "site": site, "reason": reason, "pid": os.getpid(),
                                 "cwd": cwd or os.getcwd()}) + "\n")
    except OSError:
        pass
    return None


def scored(site: str, question: str, items: list[str], threshold_key: str, context: str = "",
           cwd: str = "") -> list[float] | None:
    """P(yes) per item, each decision logged against policy[threshold_key]. None means don't gate."""
    probs = noul(site, question, items, context, cwd)
    if probs is not None:
        t = policy()[threshold_key]
        for item, p in zip(items, probs):
            log(site, question, item, p, p >= t)
    return probs


def keep(site: str, question: str, items: list[str], threshold_key: str, context: str = "",
         cwd: str = "") -> list[bool] | None:
    """Which items pass policy[threshold_key]. None means keep everything."""
    probs = scored(site, question, items, threshold_key, context, cwd)
    return None if probs is None else [p >= policy()[threshold_key] for p in probs]


def _cert_count() -> str:
    try:
        return f"{len(_jev.TLS.get_ca_certs())} CA certs loaded"
    except NotImplementedError:
        return "system trust store (truststore)"


def doctor() -> tuple[bool, list[str]]:
    """(ok, report lines): interpreter, TLS certs, key source, one live call. Never prints the key."""
    import subprocess
    import sys
    lines = [f"python      {sys.executable} {sys.version.split()[0]}",
             f"tls certs   {_cert_count()}"]
    src = "env TYPESAFE_API_KEY" if os.environ.get("TYPESAFE_API_KEY", "").strip() else ""
    if not src:
        try:
            r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", "typesafe-api-key", "-w"],
                               capture_output=True, text=True, timeout=5)
            src = "macOS Keychain" if r.returncode == 0 and r.stdout.strip() else \
                f"NONE (Keychain: {r.stderr.strip()[:120] or 'item not found'})"
        except Exception as e:
            src = f"NONE (Keychain unreadable: {type(e).__name__})"
    lines.append(f"key         {src}")
    pol = policy()
    lines.append(f"policy      enabled={pol['enabled']} recall_min={pol['recall_min']} save_min={pol['save_min']}")
    t = time.time()
    try:
        _post({"model": _jev.MODEL, "state": {"items": {"0": "x"}},
               "questions": {"0": {"type": "noul", "instructions": "Is items[0] the letter x?"}}}, pol["timeout_s"] + 5)
        lines.append(f"api call    OK in {time.time() - t:.2f}s")
        return True, lines
    except Exception as e:
        hint = (" -> TLS: this Python has no CA certs and /etc/ssl/cert.pem was not usable" if "CERTIFICATE" in str(e)
                else " -> key missing or refused" if "401" in str(e) or "403" in str(e) or str(e) == "no key"
                else " -> network blocked (sandbox/proxy/firewall?)" if "URLError" in type(e).__name__ or "timed out" in str(e)
                else "")
        lines.append(f"api call    FAIL {type(e).__name__}: {str(e)[:160]}{hint}")
        return False, lines


def _test() -> None:
    """Offline: policy shapes and the timeout deadline. Run it with a throwaway HOME."""
    import tempfile
    global POLICY, DIR, _post
    DIR = Path(tempfile.mkdtemp())
    POLICY = DIR / "policy.json"
    for text, on in (("[]", False), ("null", False), ('{"enabled": "false"}', False), ('{"enabled": false}', False), ('{"enabled": null}', False),
                     ("{}", True), ('{"enabled": true}', True)):  # absent key keeps the default (on); only a real true is on
        POLICY.write_text(text)
        assert _allowed(policy(), "/", "x") is on, f"policy {text}: allowed should be {on}"
    POLICY.write_text('{"timeout_s": 0.5}')
    _post = lambda body, timeout: time.sleep(3) or {"answers": {}}  # noqa: E731  (a stalled request)
    t0 = time.monotonic()
    assert noul("t", "q?", ["a"]) is None
    assert time.monotonic() - t0 < 2, "timeout_s must be a deadline, not a hint: a stalled request held noul for 3s"
    _post = lambda body, timeout: {"answers": {"0": {"noul": 0.7}}}  # noqa: E731
    assert noul("t", "q?", ["a"]) == [0.7]
    print("jev_lib test ok")


def _cli_scored() -> None:
    """For non-Python hooks: stdin {site, question, items, key, context?, cwd?} -> stdout probs list or null."""
    import sys
    try:
        a = json.loads(sys.stdin.read())
        print(json.dumps(scored(a["site"], a["question"], a["items"], a["key"], a.get("context", ""),
                                a.get("cwd", ""))))
    except Exception:
        print("null")


if __name__ == "__main__" and len(__import__("sys").argv) > 1 and __import__("sys").argv[1] == "scored":
    _cli_scored()
elif __name__ == "__main__" and len(__import__("sys").argv) > 1 and __import__("sys").argv[1] == "test":
    _test()
elif __name__ == "__main__" and len(__import__("sys").argv) > 1 and __import__("sys").argv[1] == "doctor":
    _ok, _lines = doctor()
    print("\n".join(_lines) + ("\njev doctor: OK" if _ok else "\njev doctor: FAIL"))
    raise SystemExit(0 if _ok else 1)
elif __name__ == "__main__":
    q ="Is this memory relevant to the user's current prompt?"
    ctx = "User prompt: how do I restart the Cognee server with a real TMPDIR?"
    items = ["Cognee server restart needs TMPDIR=$(getconf DARWIN_USER_TEMP_DIR) or LanceDB fails.",
             "Indeed sent job alert email 191dd714195513bb.",
             "BreakLog.setOutcome takes a BreakPromptOutcome."]
    probs = noul("selftest", q, items, ctx)
    assert probs is not None, "Jev unreachable (key/network) - gate would fail open"
    assert probs[0] > probs[1] and probs[0] > probs[2], f"relevance ordering wrong: {probs}"
    print("jev_lib selftest ok", [round(p, 2) for p in probs])
