# The two formats

Read this when you are about to write the report, or about to create or extend a `decided.md`.
`SKILL.md` points here instead of restating either one, so there is a single place to fix when a
format turns out to be wrong.

- [1 · The report](#1--the-report) — what the user reads at the end of a session
- [2 · The ledger](#2--the-ledger) — `decided.md`, the file a future run checks before asking
- [3 · The pointer](#3--the-pointer) — the line in `SKILL.md` that makes a ledger get read
- [4 · Worked example](#4--worked-example)

---

## 1 · The report

Three parts, in this order, every time. The order matters: a reader who sees a table before they
know which skill it concerns has to hold the rows in their head until they find out.

### 1a. Name the target skill first

```
## Target skill: `replicate-checklist-video`
Path     .claude/skills/replicate-checklist-video/
Ledger   references/short/decided.md — exists, 8 rows
Pointer  MISSING from SKILL.md
```

One block per skill that earned rows this session. `Ledger` says *exists / missing*, and where.
`Pointer` says whether that `SKILL.md` currently tells a future run to read the ledger — because a
ledger nothing points at is a ledger nothing reads, which is the exact way this fails in practice.

A skill that came up but produced no decisions is not listed. Silence is information; a block
saying "nothing here" is noise.

### 1b. The table — exactly three columns

| Issue | Decision | Principle |
|---|---|---|

- **Issue** — the question or friction as it actually arose, one line. Not what you wish you had
  asked; what was on screen.
- **Decision** — what the user chose, **in their words** wherever they said it out loud. Quote them.
  A paraphrase is where a rule starts drifting away from what was meant, and by the time anyone
  notices, the original wording is gone.
- **Principle** — the general rule that decision implies, written to apply to the *next* case.

**The whole value of the table is in the third column, and it is the one most likely to collapse.**
The failure mode is writing Decision and Principle as the same sentence:

| | Decision | Principle |
|---|---|---|
| ✗ collapsed | Use `holding-dji-mic-workdesk.png` | Use `holding-dji-mic-workdesk.png` |
| ✓ generalised | *"you can use this: `assets/reference/holding-dji-mic-workdesk.png`"* | Use the frame the user names. Report which contract rows it fails and proceed — never substitute a "better" frame, never offer alternatives. |

The first is a fact about one file and helps exactly once. The second is a rule, and it is what
stops the question being asked again. If you cannot write a Principle that outlives the specific
case, that row is a one-off and does not belong in the ledger at all.

**Rows the user refused to answer.** `mine_session.py` marks these `status: rejected`. They are the
sharpest signal in the whole report — a dismissed question is one the skill should have decided for
itself. Put them at the top of the table, mark the Issue cell `🚫 rejected`, and let the Principle
column say what the skill should do instead of asking.

**Rows already in the ledger.** Mark the Issue cell `⚠️ already in the ledger` and carry on — no
extra column. These are a *read-side* failure, not a missing decision: the answer was on disk and
nothing put it in front of the run. The fix is almost always a missing pointer (§3), plus a line in
the ledger's "asked and should not have been" log.

### 1c. The proposal, below the tables

Plain prose, grouped by skill, each item a diff small enough to scan. Three kinds:

- **ledger rows** → appended to `<skill>/decided.md`. The row's *Decided* cell is the **Principle**
  column, never the Decision column — the ledger stores rules, not transcript.
- **the pointer** → §3, whenever a row is added and the pointer is absent.
- **behaviour edits** to `SKILL.md` itself — only where a steer changes what the skill *does*.
  A fact the skill should *know* goes in the ledger; a step it should *take* goes in `SKILL.md`.
  Putting a fact in `SKILL.md` is how a skill file grows until nobody reads it to the end.

Then stop. Nothing is written until the user says which items to apply.

---

## 2 · The ledger

`decided.md` sits beside the skill that owns it — `<skill>/decided.md`, or under `references/<variant>/`
when the skill has variants that decide differently. A decision no skill owns goes to the global
`~/.claude/decided.md`.

Its stated job, at the top of the file, is **"the questions not to ask again"**. Four sections:

```markdown
# Decided — <skill or variant> — the questions not to ask again

Read this **before** reaching for `AskUserQuestion`. Every row below has already been put to the
user and answered.

| # | The question | Decided | When |
|---|---|---|---|
| 1 | **Driving frame** | **Use the frame the user names.** Report the contract rows it fails and proceed — do not substitute a "better" frame, do not offer alternatives. | 2026-09-15 |

## Settled elsewhere, and still true here

Not restated — one fact, one home. Read them in [`../long/decided.md`](../long/decided.md):

- **their title** → near-verbatim, except claims it makes about its own video (row 6 there)

## What is still worth asking

- **The topic and the angle**, when the source could plausibly be adapted more than one way.

## Asked and should not have been

| Asked | Where it was already answered |
|---|---|
| "walk the contract, or generate a tighter frame?" | row 1 above — *"do not offer alternatives"* |
```

**The rules that keep it honest:**

- **One fact, one home.** A row settled in a sibling ledger is *linked*, never copied. A copy is a
  second source of truth that goes stale silently, and the copy usually wins because it is the one
  being read.
- **Every row carries its date and, where it exists, the user's own words.** A rule with no
  provenance cannot be retired later, because nobody can tell whether it still reflects what the
  user wants.
- **"What is still worth asking" should shrink over time.** If it does not, the skill is not
  learning — it is just accumulating notes. When it gets down to one or two genuinely open
  questions, say so in the report; that is the skill working.
- **"Asked and should not have been" keeps the cost visible.** Name what the re-asking cost —
  a round trip, a re-render, the user repeating themselves. Without the cost it reads as tidiness
  and gets deleted in the next cleanup.

---

## 3 · The pointer

A ledger nothing points at is a ledger nothing reads. This has already happened once in the wild:
the file existed, was correct, said *"do not offer alternatives"* — and four questions it answered
were asked anyway, because the `SKILL.md` delivered at invocation never mentioned it.

So whenever a ledger row is added and the owning `SKILL.md` has no pointer, propose one. Near the
top, above the workflow, where it cannot be missed:

```markdown
> **Before you ask the user anything, read [`decided.md`](decided.md).** It lists the questions
> already put to them and answered. Asking one of them again costs a round trip and their patience.
```

Adjust the path for variants. Keep it to two lines — it competes for attention with the skill's
actual content, and a paragraph here is a paragraph nobody reads.

---

## 4 · Worked example

From the 2026-09-14/15 checklist rebuild, as the report should have looked:

```markdown
## Target skill: `replicate-checklist-video`
Path     .claude/skills/replicate-checklist-video/
Ledger   references/short/decided.md — exists, 8 rows
Pointer  MISSING from SKILL.md

| Issue | Decision | Principle |
|---|---|---|
| 🚫 rejected — where the six non-track decisions should live | Dismissed without answering | Decisions that hold across variants live in one variant's ledger and are *linked* from the others. Do not ask where a row goes; place it and say where it went. |
| ⚠️ already in the ledger — which driving frame to use | *"you can use this: `assets/reference/holding-dji-mic-workdesk.png`"* | Use the frame the user names. Report which contract rows it fails and proceed — never substitute, never offer alternatives. |
| Runtime band: source is 48.4s, over the 40s `standard` ceiling | *"Source parity, 1.15×"* | Keep the source's item count and per-item pacing; let runtime land where it lands and set `video_type` to match. Never drop items or compress dwell to hit a band. |
| Whether to reproduce the source's asterisk styling in the title | *"Reproduce their styling"* | Carry the source's title styling across verbatim, including punctuation and emoji, unless it makes a claim about the video that is not true of ours. |

### Proposal

**`replicate-checklist-video/references/short/decided.md`** — three new rows (9–11), carrying the
Principle text above. Row 9 also gets a line in *Asked and should not have been*, naming its cost:
one round trip re-litigating a frame the user had already chosen twice.

**`replicate-checklist-video/SKILL.md`** — add the pointer at the top. This is the fix for the
⚠️ row: the ledger held the frame answer and nothing directed the run to it.

**No behaviour edits proposed.** All four rows are facts the skill should know, not steps it should
take.
```
