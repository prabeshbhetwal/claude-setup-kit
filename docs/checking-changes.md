# Checking the kit, and checking your changes to it

The kit promises things in plain words: what starts ticked, what it asks before changing, what it schedules, how to undo it. This page explains how those promises are checked, so you can run the same checks yourself, on the kit as shipped or on your own changes.

## Run the audit

```bash
python3 lib/audit.py
```

It takes about a minute, touches nothing of yours (every install it tries runs in a throwaway home folder, with no Claude, Node or Homebrew on its path), and exits with a non-zero code if anything fails. It checks:

**That the pieces agree with each other**
- Every tool in the catalogue has a valid tier, eight fields, and is mentioned in the README.
- Every hook fragment in `lib/hooks.json` belongs to a catalogue tool, its `match` text really occurs in its command, and the script it runs exists.
- Every file `install.sh` copies exists, and every hook script is used.
- Every flag the README documents is parsed by `install.sh`, and every flag `install.sh` parses is in the README.
- The tier list in the README is the tier list in `install.sh`.
- Every link in the README points at a file that exists.
- The macOS check comes before the first question, and `python3` is not called before the prerequisite check.

**That the installer behaves**
- All scripts parse (`bash -n`, `py_compile`) and the self-tests pass; the secrets and personal-path scan is clean.
- Bad flags (`--tiers bogus`, `--only bogus`, a missing value) are refused with exit code 2; `--list` and `--help` work.
- A non-macOS run stops before it asks anything.
- Each tool that needs no prerequisites is installed into an empty home folder; `doctor.sh` must then report no failures, `settings.json` must still be valid JSON, and a second run must change nothing.
- With the token report switched off, both jobs are still scheduled (the report job then does nothing), so `--set` can turn it back on.
- With no terminal and no options, the installer stops instead of answering its own questions.

## How to check a change by hand

These are the habits that find the problems a script cannot. They come from an outside review that found eleven real problems in the installer and README that earlier checks had missed.

1. **Read the README and the script as two separate documents.** List what the README claims (what starts ticked, what is asked first, what is scheduled, what a flag does, what to run to undo it) and find the code that does it. Do not trust either one to describe the other.
2. **Trace the order things run in, for each mode.** Interactive, `--yes`, `--tiers`, `--only`, no terminal, a brand-new Mac with no Apple tools, a non-Mac. Ask of each step: what has already run, and does the thing it needs exist yet?
3. **Ask what happens when nobody can answer.** A question's default is a silent decision in a non-interactive run. A default that changes something of yours must be "no".
4. **Compare the example people will paste with the claim around it.** A copy-and-paste command must do what the sentence above it says.
5. **After moving a block, re-read the whole `if`/`else`/`fi` it moved across.** Check that the directories and variables it used are still set up on every path that reaches it.
6. **Search the README for words your change touched** (scheduled, off, asks, default, ticked, undo) and re-read each sentence. A change makes true sentences false without anyone editing them.
7. **Run it with the option turned off.** Features are usually tested on, and break off.
8. **Try it in an empty home folder:** `HOME=$(mktemp -d) ./install.sh --only <tool>`, then `./doctor.sh`, then the same install again.
9. **Say what you did not check.** If `doctor.sh`, the merge script or a hook was not read, write that down.

Where a second pair of eyes is available (a person, or a fresh Claude chat given only the README and the scripts), ask them to follow steps 1 to 3 cold. Someone who did not write the change reads what is there, not what was meant.
