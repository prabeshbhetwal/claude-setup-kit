"""TypeSafe API key for hooks.

Claude Desktop does not load ~/.zshrc, so hooks fall back to the macOS login
Keychain item `typesafe-api-key` (copied there from the shell export).
Never print or log the returned value.
"""
import os
import subprocess

KEYCHAIN_SERVICE = "typesafe-api-key"


def get_key() -> str:
    """The key from TYPESAFE_API_KEY, else the Keychain; "" when neither has it."""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if key:
        return key
    try:
        out = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


if __name__ == "__main__":
    k = get_key()
    assert k, "no TypeSafe key in env or Keychain"
    print(f"ok: key found ({len(k)} chars)")
