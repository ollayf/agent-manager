---
name: google-drive-authoring
description: >-
  Create or update Google Docs, Sheets, or Slides through the Drive MCP
  connector (create_file / copy_file tools) without shipping broken
  formatting. Use this skill whenever you're about to write content into a
  new or existing Google Doc/Sheet/Slide deck, format a table for Google
  Docs, turn markdown into a Google Doc, or whenever the user asks you to
  "put this in a doc," "make a google doc," "write this up in sheets," or
  similar — even if they don't say "markdown" or "formatting" explicitly.
  Also use it any time you're about to reuse text you read back from an
  existing Google Doc (via read_file_content) as input to a new one — that
  specific move has a sharp edge, covered below.
---

# Google Drive Authoring

Two failure modes account for nearly every problem when writing to Google
Drive through the connector, and both are invisible from the API response
alone — the `create_file` call reports success even when the document that
comes out the other end is garbled or nobody can see it. This skill exists
to catch both **before** you tell the user it's done.

1. **Broken formatting** — bold markers and links show up as literal
   asterisks and brackets instead of rendering.
2. **Invisible file** — the doc gets created successfully but under an
   account the user can't open.

Treat "the tool call succeeded" and "the document is actually right" as two
separate claims. Only make the second claim after you've checked it.

## Failure mode 1: the escaped-markdown trap

`create_file` with `contentMimeType: text/markdown` converts real markdown
syntax (`**bold**`, `[text](url)`, tables) into native Doc formatting. This
works well — *as long as the markdown you feed it is clean.*

The trap: if you call `read_file_content` on an **existing** Google Doc to
see what's in it, the text that comes back is Google's own export of
already-rendered content, and it escapes every markdown-special character
with a backslash — `\*\*bold\*\*`, `\[text\]\(url\)`, `\_`, `\!`. That
escaping exists so Google's exporter doesn't accidentally introduce new
formatting from a stray asterisk in someone's plain-text sentence. It is a
**representation of finished output**, not a **markdown source file**.

If you copy that escaped text straight into a new `create_file` call, the
markdown parser does exactly what backslash-escaping tells it to do: treat
`\*\*` as two literal asterisks (no bold applied) and `\[text\]` as literal
brackets (no link — though the bare URL that follows may still get
auto-linked on its own, producing a doc with visible `[Workshop Name]`
followed by a separate blue link, which looks obviously broken).

**The rule:** never pipe `read_file_content` output directly into
`create_file`. If you're reusing or rebuilding content from an existing doc:

- Strip the escaping first — a regex like `\\([*\[\]()#!_])` → `\1` removes
  backslashes before markdown-special characters and recovers clean source.
- Or, better, compose the new markdown fresh rather than round-tripping
  through the export format at all.
- Before calling `create_file`, sanity-check your payload has no stray
  backslashes in front of `*`, `[`, `]`, `(`, `)`, `#`, `!`, or `_` — a
  quick `grep -c '\\\\'` on the file you're about to upload is enough to
  catch it.

This applies the same way to Sheets (CSV/markdown-table content) and any
other round-trip through this connector, not just Docs.

## Failure mode 2: nobody can see it

`create_file` creates the document under whatever Google account the Drive
connector is authenticated as. That account is not guaranteed to be the
one the user browses with — if they're signed into a different Google
account, opening the link will show "You need access," even though the
file exists and the API call reported success.

Don't assume this is broken or try to "fix" it by changing sharing
permissions — modifying access controls is not something to do
unprompted. Instead:
- If you don't already know which account the user views these docs with,
  ask once, early, rather than after generating a pile of docs they can't
  open.
- If the user confirms they own whatever account the connector uses, this
  is a non-issue — no sharing step needed, ever mention it again unless
  something actually changes.

## The verification step (do this every time, before reporting success)

The `create_file` response only proves the API call succeeded — it carries
no information about whether the markdown converted correctly. The only
way to know the doc actually looks right is to load it and look.

1. Use the browser tools (`mcp__claude-in-chrome__*` — load via ToolSearch
   if not already available: `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__tabs_create_mcp`).
2. `tabs_context_mcp` with `createIfEmpty: true` to get a tab, then
   `navigate` to the doc's `edit` URL.
3. Take a `computer` screenshot. Check specifically for:
   - Headers/labels that should be bold actually render bold, not `**text**`
   - Links render as blue/underlined clickable text, not `[text]` followed
     by a separate bare URL
   - Tables have the right number of columns and aren't visibly mangled
   - If you land on an "Access Denied" / "You need access" screen, that's
     failure mode 2, not failure mode 1 — don't mistake it for broken
     markdown, and don't try to request access yourself; tell the user.
4. Only after the screenshot confirms correct rendering, tell the user the
   doc is ready — and give them the direct link.

For long documents, spot-checking the top of the doc plus one or two rows
further down (scroll and screenshot again) is enough; you don't need to
review every row when the same `create_file` call produced all of them
from the same code path.

## Quick checklist

- [ ] Markdown payload has no stray backslashes before `* [ ] ( ) # ! _`
- [ ] If content was reused from `read_file_content`, it was cleaned first
- [ ] `create_file` call succeeded (check the response)
- [ ] Opened the doc in the browser and screenshotted it
- [ ] Bold, links, and tables visually confirmed correct in the screenshot
- [ ] No "Access Denied" screen (or if there was one, flagged to the user
      instead of silently working around it)
- [ ] Only then: report the doc as done, with its link

## Scope note: Sheets and Slides

The same connector (`create_file`) handles all three via
`contentMimeType`:
- **Docs**: `text/markdown` → converts cleanly, this is the well-trodden
  path described above.
- **Sheets**: `text/csv` (or a markdown table) → converts to
  `application/vnd.google-apps.spreadsheet`. Apply the same
  no-stray-backslashes check and the same browser-verify step before
  reporting done.
- **Slides**: markdown-to-slides conversion is much less reliable than
  Docs/Sheets — there's no clean text format for slide layout. If asked
  to build a deck, treat this as higher-risk: verify more carefully in the
  browser (check every slide, not just the first), and be upfront with the
  user if the layout doesn't come out clean, rather than assuming the
  conversion worked because the API call succeeded.
