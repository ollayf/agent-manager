---
name: self-update-skill
description: >-
  Mine the session you are in for every decision the user actually made, and turn the ones that
  generalise into permanent rules inside the skills that caused them — so the next run asks fewer
  questions, and never the same one twice. Use this whenever a skill's own behaviour is the subject
  rather than the work it produces: "update the skill with what we learned", "self update",
  "improve the skill from this session", "harvest this session", "what did we decide", "add this to
  the skill", "remember this decision", "make the skill smarter", "fewer questions next time",
  "write this down so you stop asking". Reach for it especially the moment the user pushes back on
  being asked something — "stop asking me this", "you already asked me that", "I told you this
  already", "why are you asking again", "just use it, don't overthink it" — because that sentence
  is the signal that a decision exists with nowhere to live. It reads the transcript with a script
  rather than from memory, reports what it found as a fixed Issue / Decision / Principle table
  before proposing anything, and writes nothing until the user approves. Do NOT use it to author a
  brand-new skill (that is `skill-creator`), to maintain CLAUDE.md (that is `claude-md-improver` or
  `/revise-claude-md`), or to write a handoff for the next session (that is `handoff`).
---

# Self-Update Skill

A skill that asks the same question every time it runs is not a skill, it is a form. The answers
exist — the user gave them, out loud, often more than once — they just had nowhere to live, so they
died with the session.

This skill is the machine that gives them somewhere to live. It reads a finished session, finds the
decisions, works out which of them are **rules** rather than one-offs, and writes those rules into
the skill that will need them next. Over time each skill converges on asking only the things that
genuinely vary.

**What it owns:** mining a session for decisions; the `decided.md` ledger format; installing the
pointer that makes a ledger actually get read.

**What it does not own:** creating new skills (`skill-creator`), CLAUDE.md upkeep
(`claude-md-improver`), the memory system, and — importantly — **the read side at runtime.** This
skill does not stand guard over future sessions. The pointer it writes into `SKILL.md` does that.

---

## 1 · Mine the transcript

```bash
python3 "$SKILL_DIR"/scripts/mine_session.py --report      # human summary
python3 "$SKILL_DIR"/scripts/mine_session.py               # JSON, for working with
```

Run it from the project directory the session belongs to (`$SKILL_DIR` is this skill's own
directory, given to you at invocation). It defaults to the current session
(`$CLAUDE_CODE_SESSION_ID`); `--session <uuid>`, `--last` and `--list` cover the rest.

Use the script rather than recalling the session yourself. Not because your memory is bad, but
because `AskUserQuestion` answers round-trip through the transcript **verbatim** — the user's exact
words, not your summary of them — and exact words are what the Principle column has to be built
from. Memory paraphrases, and a paraphrased rule drifts.

What it hands back:

| | |
|---|---|
| `decisions` | every question put to the user, with `status: answered / rejected / unparsed` |
| `steers` | free-text the user typed, unclassified — the corrections live here |
| `skills_in_play` | `Skill` invocations in order |
| `skill_edits` | edits already made to skill files this session |

**`status: rejected` is the most valuable thing in the output.** The user dismissed the question
instead of answering it. That is not a missing answer — it is the user saying the question should
not have been asked, which is precisely the thing this skill exists to fix.

**Two things the script cannot see, so you must.** The transcript lags the live conversation: the
last few turns, including something the user said a minute ago, may not be on disk yet — read those
from the conversation itself. And if no transcript is found at all, say so plainly and fall back to
reading the conversation, rather than reporting an empty session as if it were a quiet one.

## 2 · Attribute each decision to a skill

The script's attribution is a **hint**, and it says so. A skill read from disk without the `Skill`
tool leaves no trace in the transcript, so `skill_dirs_edited` — which skills were actually being
edited — is usually the better evidence than which skill was formally invoked.

Three cases:

- **A skill owns it** → its `decided.md`.
- **No skill owns it** — a preference about how you work generally → the global `~/.claude/decided.md`.
- **The skill lives in a plugin cache** (`plugins/cache/…`) → **not editable**; the cache is
  overwritten on update. Record it globally and say why.

When two skills could own a row, ask *"which one would be wrong if this changed?"* and put it there.

## 3 · Report — fixed format, before proposing anything

Read [`references/ledger-format.md`](references/ledger-format.md) §1 and follow it exactly. In
outline:

1. **`## Target skill: <name>`** — one block per skill, stating where its ledger is and whether its
   `SKILL.md` carries a pointer to it.
2. **A three-column table: `Issue | Decision | Principle`.** Decision quotes the user. Principle is
   the general rule that decision implies, written to apply to the *next* case.
3. Rejected rows at the top, marked `🚫 rejected`. Rows already in the ledger marked
   `⚠️ already in the ledger` in place.

The reference explains the one failure this format keeps having — Decision and Principle written as
the same sentence, which turns a rule back into a fact about one file. Read it before writing the
table, not after.

**The report comes first and comes whole.** The user is deciding what becomes permanent law for a
skill; they need to see the evidence before the recommendation, not underneath it.

## 4 · Propose — below the table, in plain language

Grouped by skill. Three kinds of change, each a scannable diff:

- **ledger rows** → append to `<skill>/decided.md`, creating it from the template
  ([`ledger-format.md`](references/ledger-format.md) §2) if absent. The *Decided* cell takes the
  **Principle** text, not the Decision text — the ledger stores rules, not transcript.
- **the pointer** → [`ledger-format.md`](references/ledger-format.md) §3, whenever a row is added
  and the owning `SKILL.md` has none. Do not skip this as housekeeping: a ledger nothing points at
  is a ledger nothing reads, and that is how a correct file sat on disk while four questions it
  answered got asked anyway.
- **behaviour edits** to `SKILL.md` — only where a steer changes what the skill *does*. A fact it
  should *know* belongs in the ledger. Facts pushed into `SKILL.md` are how a skill file grows past
  the point anyone reads it to the end.

**Be willing to propose nothing.** A session where the user answered four questions that were all
genuinely open produced no rules, and saying so is a real result. Rows that do not generalise are
noise in a ledger, and noise is what stops the ledger being read.

Skip anything already in `skill_edits` — it was applied during the session.

## 5 · Apply only what is approved

Nothing is written before the user says which items to apply. They are authoring permanent
instructions for their own tools; a misread steer becomes a law that silently misdirects every
future run.

If the skills tree is a git repo, **do not commit.** Print the exact `git add` / `git commit`
commands and stop.

---

## When the ledger is working

Two things should be true after a few rounds, and both are worth reporting when you see them:

- **"What is still worth asking" shrinks.** If it never shrinks, rows are being added that were
  never really questions — the ledger is accumulating notes instead of retiring decisions.
- **"Asked and should not have been" stays empty.** A new entry there means the read side failed,
  not the write side. Check the pointer before you check the rows.
