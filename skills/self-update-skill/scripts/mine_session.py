#!/usr/bin/env python3
"""mine_session.py — pull the decisions out of a Claude Code session transcript.

This is the deterministic half of `self-update-skill`. It does no judging: it finds the
transcript, extracts the four signals worth reading, and prints them as JSON. Deciding
which of them deserves to become a rule is the model's job, not this script's.

The four signals:

  decisions   every AskUserQuestion, paired with the answer the user actually picked.
              These round-trip through the transcript verbatim as `"<question>"="<answer>"`,
              so they are recoverable exactly — no paraphrase, no reconstruction.
  steers      free-text things the user typed. Corrections and shortcuts live here
              ("just use this", "there is no need for checking this"), but so does every
              ordinary instruction, so these are emitted unclassified.
  skills      every Skill invocation, in order, so a decision can be attributed to the
              skill that was running when it was made.
  skill_edits Edit/Write/MultiEdit calls whose target was inside a skill directory — what
              already changed this session, so it is not proposed a second time.

Usage
    mine_session.py                     # this session, this project
    mine_session.py --session <uuid>    # a specific session
    mine_session.py --last              # the most recently written session in this project
    mine_session.py --list              # what sessions exist for this project
    mine_session.py --report            # human-readable summary instead of JSON
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Text that arrives on the `user` channel but was not typed by a human: command scaffolding,
# local command output, interrupt notices, and the caveat banner injected on resume.
NOT_HUMAN_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<user-prompt-submit-hook>",
    "Caveat: The messages below",
    "[Request interrupted",
    "API Error",
)

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# A question the user dismissed instead of answering. Worth separating from a parse failure:
# a rejected question is the strongest evidence a skill asks something it should not ask at all.
REJECTED_MARKER = "doesn't want to proceed with this tool use"

# Skills that answer a passing question and hand control straight back. They are almost never
# the owner of a decision that follows them, so they make a misleading attribution hint.
TRANSIENT_SKILLS = {"explain-simply", "zoom-out", "find-skills", "handoff", "grill-me"}


# ── locating the transcript ──────────────────────────────────────────────────────────

def config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))


def project_slug(cwd: Path) -> str:
    """Claude Code names a project directory after its path with every non-alphanumeric
    character flattened to a dash, so /Users/me/video_gen/x becomes -Users-me-video-gen-x."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def project_dir(cwd: Path) -> Path:
    return config_dir() / "projects" / project_slug(cwd)


def find_transcript(cwd: Path, session: str | None, last: bool) -> Path:
    pdir = project_dir(cwd)
    if not pdir.is_dir():
        raise SystemExit(
            f"no transcript directory for this project: {pdir}\n"
            "Either the cwd is not where the session started, or CLAUDE_CONFIG_DIR points elsewhere."
        )
    if session:
        path = pdir / f"{session}.jsonl"
        if not path.is_file():
            raise SystemExit(f"no transcript for session {session} at {path}")
        return path
    if not last:
        sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
        if sid and (pdir / f"{sid}.jsonl").is_file():
            return pdir / f"{sid}.jsonl"
    files = sorted(pdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit(f"no .jsonl transcripts in {pdir}")
    return files[0]


# ── parsing ──────────────────────────────────────────────────────────────────────────

def read_lines(path: Path) -> list[dict]:
    out = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def content_blocks(entry: dict) -> list:
    msg = entry.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        return [c for c in content if isinstance(c, dict)]
    return []


def user_text(entry: dict) -> str | None:
    """The human-typed text of a user entry, or None if there wasn't any."""
    msg = entry.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content
                 if isinstance(c, dict) and c.get("type") == "text"]
        joined = "\n".join(p for p in parts if p)
        return joined or None
    return None


def split_answers(questions: list[str], result_text: str) -> dict[str, str]:
    """Recover the picked answers out of an AskUserQuestion tool_result.

    The result is prose with the pairs embedded as `"<question>"="<answer>"`, comma
    separated. A regex over quotes would be wrong — questions routinely contain their own
    quotation marks — so instead each known question is used as its own anchor, and an
    answer is simply the text between its anchor and the next one.
    """
    anchors = []
    for q in questions:
        needle = f'"{q}"="'
        idx = result_text.find(needle)
        if idx != -1:
            anchors.append((idx, len(needle), q))
    anchors.sort()

    answers: dict[str, str] = {}
    for i, (pos, nlen, q) in enumerate(anchors):
        start = pos + nlen
        if i + 1 < len(anchors):
            # ...<answer>", "<next question>"="...  → back off the quote and the comma-space
            end = anchors[i + 1][0] - 3
            answers[q] = result_text[start:max(start, end)]
        else:
            tail = result_text[start:]
            cut = tail.rfind('"')
            answers[q] = tail[:cut] if cut > 0 else tail
    for q, a in answers.items():
        for trailer in ('" selected preview:', '". You can now continue'):
            if trailer in a:
                a = a.split(trailer)[0]
        answers[q] = a.strip()
    return answers


def mine(entries: list[dict], include_subagents: bool) -> dict:
    asked: dict[str, dict] = {}          # tool_use_id → AskUserQuestion input
    skills: list[dict] = []              # Skill invocations, in order
    skill_edits: list[dict] = []
    steers: list[dict] = []
    decisions: list[dict] = []

    def current_skill(seq: int) -> str | None:
        """Nearest preceding Skill invocation, ignoring the lookup skills that hand control
        straight back. A hint only — a skill reached without the Skill tool leaves no trace
        here at all, which is why skill_dirs_edited exists alongside it."""
        prior = [s for s in skills
                 if s["seq"] < seq and s.get("skill") not in TRANSIENT_SKILLS]
        return prior[-1]["skill"] if prior else None

    def nearest_skill_dir(seq: int) -> str | None:
        """The skill whose files were being edited closest to this point. Usually the better
        hint of the two: work on a skill leaves edits even when it was never formally invoked."""
        if not skill_edits:
            return None
        closest = min(skill_edits, key=lambda e: abs(e["seq"] - seq))
        return closest.get("skill")

    for seq, entry in enumerate(entries):
        if entry.get("isSidechain") and not include_subagents:
            continue
        etype = entry.get("type")
        ts = entry.get("timestamp")

        if etype == "assistant":
            for block in content_blocks(entry):
                if block.get("type") != "tool_use":
                    continue
                name, inp = block.get("name"), block.get("input") or {}
                if name == "AskUserQuestion":
                    asked[block.get("id")] = {"input": inp, "seq": seq, "timestamp": ts}
                elif name == "Skill":
                    skills.append({"seq": seq, "timestamp": ts,
                                   "skill": inp.get("skill"), "args": inp.get("args")})
                elif name in EDIT_TOOLS:
                    path = inp.get("file_path") or inp.get("notebook_path") or ""
                    if "/skills/" in path or path.endswith("SKILL.md"):
                        m = re.search(r"/skills/([^/]+)/", path)
                        skill_edits.append({"seq": seq, "timestamp": ts, "tool": name,
                                            "path": path, "skill": m.group(1) if m else None})

        elif etype == "user":
            for block in content_blocks(entry):
                if block.get("type") != "tool_result":
                    continue
                call = asked.get(block.get("tool_use_id"))
                if not call:
                    continue
                raw = block.get("content")
                if isinstance(raw, list):
                    raw = " ".join(c.get("text", "") for c in raw if isinstance(c, dict))
                raw = raw if isinstance(raw, str) else json.dumps(raw)
                rejected = REJECTED_MARKER in raw
                qs = [q.get("question", "") for q in call["input"].get("questions", [])]
                answers = {} if rejected else split_answers(qs, raw)
                for q in call["input"].get("questions", []):
                    text = q.get("question", "")
                    if rejected:
                        status = "rejected"
                    elif text in answers:
                        status = "answered"
                    else:
                        status = "unparsed"
                    decisions.append({
                        "timestamp": call["timestamp"],
                        "status": status,
                        "skill_in_play": None,
                        "skill_dir_nearby": None,
                        "_seq": call["seq"],
                        "header": q.get("header"),
                        "question": text,
                        "answer": answers.get(text),
                        "options": [o.get("label") for o in q.get("options", [])],
                        "raw_result": None if status == "answered" else raw[:2000],
                    })

            if entry.get("isMeta"):
                continue
            text = user_text(entry)
            if not text:
                continue
            stripped = text.strip()
            args = re.search(r"<command-args>(.*?)</command-args>", stripped, re.S)
            if args:
                stripped, source = args.group(1).strip(), "slash-command"
            elif stripped.startswith(NOT_HUMAN_PREFIXES):
                continue
            else:
                source = "typed"
            if not stripped:
                continue
            steers.append({"timestamp": ts, "_seq": seq, "source": source, "text": stripped})

    for d in decisions:
        d["skill_in_play"] = current_skill(d["_seq"])
        d["skill_dir_nearby"] = nearest_skill_dir(d["_seq"])
        del d["_seq"]
    for st in steers:
        st["skill_in_play"] = current_skill(st.pop("_seq"))

    return {
        "skill_dirs_edited": sorted({e["skill"] for e in skill_edits if e.get("skill")}),
        "decisions": decisions,
        "steers": steers,
        "skills_in_play": skills,
        "skill_edits": skill_edits,
    }


# ── reporting ────────────────────────────────────────────────────────────────────────

def clip(text: str | None, n: int = 110) -> str:
    if not text:
        return "—"
    flat = " ".join(str(text).split())
    return flat if len(flat) <= n else flat[: n - 1] + "…"


def report(data: dict, path: Path) -> str:
    decisions = data["decisions"]
    answered = [d for d in decisions if d["status"] == "answered"]
    rejected = [d for d in decisions if d["status"] == "rejected"]
    unparsed = [d for d in decisions if d["status"] == "unparsed"]
    invoked = sorted({s["skill"] for s in data["skills_in_play"] if s.get("skill")})
    edited = data["skill_dirs_edited"]

    lines = [
        f"\u2500\u2500 SESSION MINE \u00b7 {path.name} " + "\u2500" * 40,
        f"MEASURED    {len(answered)} questions answered, {len(rejected)} rejected outright",
        f"REFERENCE   {len(data['steers'])} free-text steers \u00b7 "
        f"{len(data['skill_edits'])} edits across {len(edited)} skill(s)",
        "DETAIL",
    ]
    if edited:
        lines.append(f"  worked on   {', '.join(edited)}   \u2190 the likeliest owner of these rows")
    if invoked:
        lines.append(f"  invoked     {', '.join(invoked)}")

    if rejected:
        lines.append("  rejected    questions the user refused to answer \u2014 the sharpest evidence")
        lines.append("              a skill asks something it should decide for itself:")
        for d in rejected:
            lines.append(f"    \u00b7 [{d['header'] or '?'}] {clip(d['question'], 88)}")

    if answered:
        lines.append("  answered")
        for d in answered:
            owner = d["skill_dir_nearby"] or d["skill_in_play"] or "unattributed"
            lines.append(f"    \u00b7 [{owner}] {clip(d['question'], 80)}")
            lines.append(f"        \u2192 {clip(d['answer'], 92)}")

    if unparsed:
        lines.append("  unparsed    read raw_result in the JSON for these:")
        for d in unparsed:
            lines.append(f"    \u00b7 {clip(d['question'], 88)}")

    counts: dict[str, int] = {}
    for e in data["skill_edits"]:
        counts[e["path"]] = counts.get(e["path"], 0) + 1
    if counts:
        lines.append("  edits       (already applied this session \u2014 do not propose them again)")
        for path_str, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            suffix = f"  \u00d7{n}" if n > 1 else ""
            lines.append(f"    \u00b7 {path_str}{suffix}")

    lines += [
        "BLIND SPOT  the transcript LAGS the live conversation \u2014 the last few turns, including",
        "            anything the user said moments ago, may not be on disk yet. Read them from the",
        "            conversation itself; this script cannot.",
        "            A compacted session has lost turns, and they are gone from this file too.",
        "            Subagent turns are excluded unless --include-subagents. Attribution is a",
        "            HINT, not a fact: a skill read from disk without the Skill tool leaves no",
        "            trace here, so confirm the owner against which files were being edited.",
        "            Anything settled in another session, or out of band, cannot be seen at all.",
        "            Evidence found \u2014 never a complete record.",
    ]
    if any(not (d["skill_dir_nearby"] or d["skill_in_play"]) for d in decisions):
        lines.append("            Some rows have no owner at all \u2014 attribute those by hand.")
    lines += [
        "DECIDE      each row \u2014 a one-off, or a rule the next run should follow?",
        "            A rule earns a line in the owning skill's decided.md. A one-off earns nothing.",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", help="session uuid (default: $CLAUDE_CODE_SESSION_ID)")
    ap.add_argument("--last", action="store_true", help="most recently written session instead")
    ap.add_argument("--cwd", default=os.getcwd(), help="project directory (default: cwd)")
    ap.add_argument("--list", action="store_true", help="list this project's sessions and exit")
    ap.add_argument("--include-subagents", action="store_true",
                    help="also mine sidechain (subagent) turns")
    ap.add_argument("--report", action="store_true", help="human-readable summary instead of JSON")
    args = ap.parse_args()

    cwd = Path(args.cwd).resolve()

    if args.list:
        pdir = project_dir(cwd)
        files = sorted(pdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[:30]:
            print(f"{f.stem}  {f.stat().st_size // 1024:>7} KB")
        return 0

    path = find_transcript(cwd, args.session, args.last)
    data = mine(read_lines(path), args.include_subagents)
    data["transcript"] = str(path)
    data["project"] = str(cwd)

    if args.report:
        print(report(data, path))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
