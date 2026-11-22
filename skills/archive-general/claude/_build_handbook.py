from pathlib import Path
from html import escape
import hashlib
import json
import sys

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL))
import storage


def default_target():
    """This machine's default target from its own config (never hardcoded in the repo)."""
    try:
        config = storage.load_config()
    except Exception:
        return None
    name = config.get('default')
    target = config.get('targets', {}).get(name) if name else None
    return dict(target, name=name) if target else None


TARGET = default_target()
if TARGET:
    _bits = [f'target <code>{escape(TARGET["name"])}</code>', f'archive folder <code>{escape(str(TARGET.get("root", "")))}</code>']
    if TARGET.get('filesystem'): _bits.append(escape(str(TARGET['filesystem'])))
    if TARGET.get('volume_uuid'): _bits.append(f'pinned volume UUID <code>{escape(str(TARGET["volume_uuid"]))}</code>')
    TARGET_NOTE = '<strong>Your default target:</strong> ' + ', '.join(_bits) + '. It is the default for new projects; reconnect removable media before using it.'
    TARGET_DEFAULT = f'This machine’s default for new projects: <code>{escape(str(TARGET.get("root", "")))}/</code>.'
else:
    TARGET_NOTE = '<strong>No default target registered on this machine.</strong> Run <code>archive.py target add … --default</code>.'
    TARGET_DEFAULT = 'This machine has no default target yet; new projects need <code>--target</code>.'
OUT = SKILL / 'claude/handbook'
OUT.mkdir(exist_ok=True)
report_path = SKILL / 'claude/drive-api-validation.json'
if not report_path.exists(): report_path = SKILL / 'claude/general-validation.json'
report = json.loads(report_path.read_text()) if report_path.exists() else {}

chapters = [
 ('index.html','The big picture','Start with the idea'),
 ('workflow.html','Archive, read & restore','Follow one file'),
 ('storage.html','Files & folders','Find everything'),
 ('security.html','Safety & security','Understand the protections'),
 ('checks.html','The check catalogue','Inspect specific checks'),
 ('recovery.html','Recovery & upgrades','Handle interruptions'),
 ('evidence.html','Evidence & limits','Know what was verified'),
]

def cmd(text):
    if text.startswith('python3 '):
        text = 'S=~/.claude/skills/archive-general/archive.py\n' + text
    return '<pre><code>' + escape(text) + '</code></pre>'

def heading(num, title):
    return f'<div class="section-title"><span class="section-num">{num:02d}</span><h2>{title}</h2></div>'

pages = {}

states = [('repo','Working project','Your normal editable file.'),('cache','iCloud folder on Mac','The archive’s local bytes.'),('cloud','iCloud upload','Reported by macOS.'),('record','Manifest entry','The receipt for the file.')]
state_html = ''.join(f'<div class="state" data-state="{key}"><span class="small-label">{title}</span><span class="light" aria-hidden="true"></span><b>—</b><p>{note}</p></div>' for key,title,note in states)
progress = ''.join(f'<button type="button" data-stage="{i}" aria-label="Show archive step {i+1}">{i+1:02d}</button>' for i in range(7))
pages['workflow.html'] = ('Follow the file.<br><em>See every handoff.</em>', 'Archiving, reading and restoring have different effects. Start with the archive walkthrough, then switch to the operation you need.', '''
<noscript><div class="note"><p>The numbered archive steps below remain readable without JavaScript. Enable it to use the interactive walkthrough and operation tabs.</p></div></noscript>
<div data-tabs>
 <div class="tabs js-only" role="tablist" aria-label="File operation">
  <button role="tab" id="archive-tab" aria-controls="archive" aria-selected="true">Archive</button>
  <button role="tab" id="read-tab" aria-controls="read" aria-selected="false">Read</button>
  <button role="tab" id="restore-tab" aria-controls="restore" aria-selected="false">Restore</button>
 </div>
 <section class="tab-panel" id="archive" role="tabpanel" aria-labelledby="archive-tab">
  <div class="mode-heading"><h2>Archive a new file</h2><span class="pill refuse">Removes the working copy</span></div>
  <p>Example: a new, ordinary <code>data/august.csv</code>. Use Next to see where its bytes and record are at each step.</p>
  <div class="sim js-only" id="archive-simulation">
   <div class="sim-bar"><span>Interactive illustration</span><span>No commands run</span></div>
   <div class="sim-stage">
    <div class="sim-progress" aria-label="Archive stages">''' + progress + '''</div>
    <div aria-live="polite" aria-atomic="true"><h3 data-sim-title>Choose the file</h3><p class="sim-description" data-sim-description></p>''' + '<div class="state-grid">' + state_html + '''</div><p class="sim-notice" data-sim-note></p></div>
    <div class="sim-controls"><button class="button secondary" type="button" data-prev>← Previous</button><span class="stage-number" data-sim-count></span><button class="button" type="button" data-next>Next step →</button></div>
   </div>
  </div>
  <ol class="step-list">
   <li><div><strong>Choose and check.</strong><p>Resolve the project, honor its rules, and skip live files. Refuse unsafe paths, collisions and insufficient space.</p></div></li>
   <li><div><strong>Copy, flush and verify.</strong><p>Write a temporary archive copy, flush it to disk and compare SHA-256 hashes. Compressed data also gets a full decompression check before acceptance.</p></div></li>
   <li><div><strong>Record before removing.</strong><p>Give the copy its final name, write and flush its manifest entry, then check that the source did not change. Only then remove the working file.</p></div></li>
   <li><div><strong>Save the map and tidy folders.</strong><p>Update the summary, manifest mirror and registry. Eligible emptied folders move into <code>_archive/</code>.</p></div></li>
   <li><div><strong>Upload, then evict.</strong><p>Check macOS’s upload status. Request eviction for uploaded files and report what became dataless and how disk-free space changed.</p></div></li>
  </ol>
  <details><summary>What happens when I sync the same folder again?</summary><p>New files are archived. A local file identical to its existing archived version can finish archiving. A changed file stays local unless you explicitly approve <code>--update</code>. Updating moves the previous archive copy into <code>.versions/</code>.</p></details>
  <details><summary>Show the archive commands</summary>''' + cmd('S=~/.claude/skills/archive-general/archive.py\npython3 "$S" status data/\npython3 "$S" sync data/august.csv\npython3 "$S" upload-status\n# Once upload is confirmed:\npython3 "$S" evict') + '''<p>These are examples. The buttons in this guide do not execute them.</p></details>
 </section>
 <section class="tab-panel" id="read" role="tabpanel" aria-labelledby="read-tab">
  <div class="mode-heading"><h2>Look while it stays archived</h2><span class="pill pass">Keeps the archive record</span></div>
  <ol class="step-list">
   <li><div><strong>Find the entry.</strong><p>The script checks the manifest or the older v1 table. A path under <code>_archive/</code> maps back to the same project path.</p></div></li>
   <li><div><strong>Ordinary file: print its location.</strong><p><code>read</code> prints the archive path. The agent opens that path to read the contents; iCloud may download the bytes on access.</p></div></li>
   <li><div><strong>Compressed file: choose the size of the read.</strong><p><code>read --head 5</code> streams a sample without writing a decompressed temp copy. Plain <code>read</code> can create one; above 10,000,000,000 original bytes, it requires <code>--full</code>.</p></div></li>
  </ol>
  <div class="note blue"><p><strong>A sample is a sample.</strong> The compressed parts are checked, which can cause iCloud to download or cache those parts. Stopping after the first few lines does not verify the full decompressed stream. A reused full-read temp copy is accepted by size, so it is not a fresh integrity audit.</p></div>
  <details><summary>Show the read commands</summary>''' + cmd('python3 "$S" read data/august.csv\npython3 "$S" read --head 5 data/large.csv\n# Only when a full large decompression is actually needed:\npython3 "$S" read --full data/large.csv') + '''</details>
 </section>
 <section class="tab-panel" id="restore" role="tabpanel" aria-labelledby="restore-tab">
  <div class="mode-heading"><h2>Bring it back for editing</h2><span class="pill refuse">Consumes the active archive copy</span></div>
  <ol class="step-list">
   <li><div><strong>Protect the destination.</strong><p>Refuse if a local file or link already takes that path. Check the archive copy, format and available space.</p></div></li>
   <li><div><strong>Restore through a temporary file.</strong><p>Copy or decompress, verify the result, restore the recorded mode and modification time for format 2, then rename it into place.</p></div></li>
   <li><div><strong>Retire the active archive entry.</strong><p>Remove its record and archive copy. Save the indexes before moving any parked folders back.</p></div></li>
  </ol>
  <div class="note"><p><strong>Choose the smallest scope you need.</strong> Restoring a folder restores its archived files below it. Restoring one report keeps its archived siblings in iCloud. An older v1 directory entry must be restored as that whole directory.</p></div>
  <details><summary>Show the restore command</summary>''' + cmd('python3 "$S" restore session/analysis/report.md') + '''<p>After success, edit the file in your normal project path. The active iCloud archive copy is deleted as part of the restore.</p></details>
 </section>
</div>
''')

pages['storage.html'] = ('One place for the bytes.<br><em>A few small maps.</em>', 'The file structure mirrors your project. The maps connect each archived path to its data and original metadata.', '''
<div class="file-map">
 <article><div class="map-header"><span>Inside your project</span><span>Local checkout</span></div>
<pre class="tree">project/
├─ src/                 <span class="location">live files</span>
├─ ICLOUD.md            <span class="location">human summary</span>
├─ ICLOUD.manifest.jsonl <span class="location">file receipts</span>
└─ _archive/
   └─ data/2026-08/     <span class="location">folder skeleton</span></pre></article>
 <article><div class="map-header"><span>Inside iCloud Drive</span><span>claude-archive/</span></div>
<pre class="tree">claude-archive/
├─ REGISTRY.md
├─ registry/&lt;repo-id&gt;.json
└─ repos/&lt;project path&gt;/ <span class="location">one archive root</span>
   ├─ files/&lt;path&gt;      <span class="location">ordinary files</span>
   ├─ .big/&lt;path&gt;/      <span class="location">compressed parts</span>
   ├─ .versions/&lt;path&gt;/ <span class="location">replaced copies</span>
   └─ .manifest.jsonl   <span class="location">manifest mirror</span></pre></article>
</div>
<p class="source-note">Default base: <code>~/Library/Mobile Documents/com~apple~CloudDocs/claude-archive/</code>. Projects under your home use their home-relative path; projects outside it use <code>repos/_abs/</code>. Older roots can still be flat until upgraded.</p>
<section class="section">''' + heading(1, 'What each map remembers') + '''
<div class="table-wrap"><table><thead><tr><th>Map</th><th>What it contains</th><th>Why it exists</th></tr></thead><tbody>
<tr><td><code>ICLOUD.md</code></td><td>A readable summary, the archive root, the park setting, and any older v1 rows.</td><td>You and the agent can discover archived files without guessing.</td></tr>
<tr><td><code>ICLOUD.manifest.jsonl</code></td><td>Each file’s path, size, SHA-256, original time and mode, storage format, and writer version.</td><td>The script can check and restore each file. During changes it acts as an append-only journal; a save compacts it.</td></tr>
<tr><td><code>.manifest.jsonl</code></td><td>The saved manifest text beside the archive.</td><td>A newer generation can be adopted when a checkout is missing its indexes or another writer saved later.</td></tr>
<tr><td>The registry</td><td>Project identity, Mac hostname, current and old archive roots, versions, counts and import origins.</td><td>Find archives across projects and follow paths after a recorded move.</td></tr>
</tbody></table></div>
<p class="caption">Use the script to change these maps. It preserves human prose in the index and unknown registry keys. A checkout’s parked-folder setting stays local; it is not adopted from the cloud mirror.</p>
</section>
<section class="section">''' + heading(2, 'What “parked folders” actually means') + '''
<div class="two-col"><article>
 <h3>The empty structure stays visible</h3><p>When a folder’s files are archived, the eligible empty structure can move to <code>_archive/&lt;same path&gt;</code>. Archived file bytes remain in iCloud.</p><p>The mover creates the destination folder and removes the empty source one folder at a time. It only carries Finder’s <code>.DS_Store</code> metadata.</p>
</article><article>
 <h3>Working folders stay usable</h3><p>A folder holding any live file stays. A <code>.keep</code> file pins its folder. Recent changes, open handles, links pointing into it and excluded paths can also keep a folder in place.</p><p>If the project already uses <code>_archive/</code> for its own files, the script reports the conflict and leaves folders in place.</p>
</article></div>
<div class="note blue"><p><code>read _archive/data/2026-08/report.csv</code> means the same archived path as <code>read data/2026-08/report.csv</code>. The prefix is a navigation aid; it does not mean the report’s bytes are stored in that parked folder.</p></div>
<p class="caption">Older checkouts keep folders in place until a whole-project upgrade enables parking. <code>tidy --plan</code> previews moves in a checkout that already has a park setting.</p>
</section>
<section class="section">''' + heading(3, 'Three formats, one versioned reader') + '''
<div class="two-col"><div><h3>Format 1 — older entries</h3><p>An entry can be a whole file, a whole directory, or a compressed pack. Its row lives in the first index table. The built-in reader understands these published forms.</p></div><div><h3>Format 2 — each file gets a receipt</h3><p>Ordinary files are stored as-is. Files above 49,000,000,000 bytes, or explicitly packed files, use compressed parts. The record says both <code>format: 2</code> and who wrote it, such as <code>by: 2.3.1</code>.</p></div></div>
<p class="source-note">The 49,000,000,000-byte packing threshold is about 45.6 GiB. The script displays binary sizes with a “GB” label, which explains some different-looking size figures in the recovered text.</p>
<details><summary>How the project root is chosen</summary><p>Starting at the current directory, the code chooses the highest ancestor with an archive index or manifest. Otherwise it uses Git’s top level; otherwise the highest ancestor with <code>CLAUDE.md</code>. It stops the ancestor search at your home directory or filesystem root. Always check the printed <code>repo:</code> line.</p><p><code>--repo DIR</code> provides an explicit project location; the script still uses Git’s top level if that directory is in a Git checkout.</p></details>
<p class="caption" style="margin-top:20px">Git tracking is deliberately ignored for archiving: a tracked file that is archived appears deleted in <code>git status</code>. This guide does not commit or push those changes.</p>
<p>Format 3 adds direct Google Drive object IDs and verified cloud receipts while keeping the same logical folder hierarchy. Existing format-1/2 filesystem archives keep their layout and target.</p></section>
''')

pages['security.html'] = ('Several layers protect a move.<br><em>Each has a boundary.</em>', 'Most protections prevent data loss: choosing the wrong file, overwriting a copy, or losing the record during an interruption. Access control and privacy also depend on the surrounding system.', '''
<div class="boundary-grid">
 <article class="boundary-block"><span class="small-label">The script enforces</span><h3>Checks around each file change</h3><p>Paths, copies, hashes, collisions, disk space, locks and the durable record are checked in code. A failed condition can refuse the file, skip a live file, or keep a folder in place.</p></article>
 <article class="boundary-block limit"><span class="small-label">The agent must honor</span><h3>Your intent and approval</h3><p>The skill tells the agent to ask about vague scopes, changed files, protection overrides and migration plans. Those are behavioral rules; a person running the CLI can supply the override flags directly.</p></article>
</div>
<section class="section">''' + heading(1, 'Protect the scope before touching data') + '''
<div class="split-rule"><h3>The right project</h3><div><p>Root detection avoids creating a separate archive just because a nested folder has its own instructions. Each archive’s manifest must identify the expected project.</p><a class="caption" href="checks.html?phase=scope">Inspect scope and identity checks →</a></div></div>
<div class="split-rule"><h3>The right paths</h3><div><p>Paths outside the project, protected Git/index paths, unsafe record names and symlink traversal are refused. Folder walks skip links and protected names rather than following them.</p><p>The no-delete guard scans three project instruction files for matching prohibitions. It is a text-pattern check, so the agent still needs to read and respect the project’s full instructions.</p></div></div>
<div class="split-rule"><h3>Your decision</h3><div><p>A changed local file is left alone without <code>--update</code>. Existing local restore targets are never intentionally overwritten. The agent must show a protected-rule refusal and obtain an explicit override before passing <code>--allow-protected</code>.</p></div></div>
</section>
<section class="section">''' + heading(2, 'Verify the bytes and preserve the receipt') + '''
<div class="two-col"><article><h3>Content checks</h3><p>SHA-256 is a fingerprint of a file’s bytes. The script compares the destination with the expected fingerprint before removing the source. Packed files have part hashes and a full decompression check when created.</p><p>Restoring verifies the output against its record. For a dataless raw archive file, the ordinary check uses existence and size; <code>status --deep</code> can fetch and hash the bytes. Reading a short sample and reusing a cached read have narrower checks; see the catalogue.</p></article><article><h3>Order matters</h3><p>A file’s manifest entry is appended and flushed before its working copy is removed. Temporary output names, saved generations and end-of-run index updates make interrupted states inspectable.</p><p>The source’s size and modification time are checked again after copying. If it changed, the local source is retained and the refusal is reported.</p></article></div>
<div class="note blue"><p><strong>Hashes detect mismatches with a trusted record.</strong> They do not encrypt data or authenticate a record that an attacker can also rewrite. A frozen release’s checksum protects comparison with the recorded expected bytes; it is not a digital signature from an external authority.</p></div>
</section>
<section class="section">''' + heading(3, 'Coordinate writers and avoid disturbing live work') + '''
<div class="two-col"><article><h3>A lock for cooperating writers</h3><p>A per-project <code>flock</code> serializes participating writes on this Mac. Each file operation rereads state while holding it. Registry updates take a separate registry lock.</p><p>A newer cloud manifest must be saved locally before new records are added. Otherwise the next load could discard those new entries while adopting the newer mirror.</p><p class="caption">The lock is advisory and local. It cannot stop an unrelated editor, and it is not a distributed lock across Macs. Missing original release code also limits verification of older locking behavior.</p></article><article><h3>Live files and folders stay put</h3><p>Recent writes, open handles, busy markers and database sidecars can skip a file. Folder movement checks age, open handles, the current working directory, inbound symlinks and exclusions.</p><p>A folder is removed using <code>rmdir</code>, which fails when something appeared in it after planning. Normal user files never ride along with a folder move.</p><p class="caption">If <code>lsof</code> fails, folder moves are blocked. The file live guard currently treats that failure as no known open handles, while its other checks still run.</p></article></div>
</section>
<section class="section">''' + heading(4, 'Understand access, privacy and cloud status') + '''
<div class="table-wrap"><table><thead><tr><th>Protection</th><th>What this code provides</th><th>Boundary</th></tr></thead><tbody>
<tr><td>Read-only archive files</td><td>Raw archived files are set to mode <code>0444</code>.</td><td>Helps prevent ordinary edits. A sufficiently privileged user can change permissions or delete files.</td></tr>
<tr><td>Confidentiality</td><td>No extra encryption layer is implemented. Ordinary files are stored in their normal format; compression preserves readability after decompression.</td><td>Device permissions, account access and cloud security settings are managed outside this script.</td></tr>
<tr><td>Metadata visibility</td><td>Indexes store names, paths, hashes, sizes, times and versions. Registry entries include the project path and Mac hostname.</td><td>Compression and hashing do not hide those details.</td></tr>
<tr><td>Upload and eviction</td><td>A Swift helper queries macOS upload state, requests eviction only for reported uploaded files, and the script checks dataless state afterward.</td><td>The 2026-10-18 rebuild tests used local sandboxes. They did not verify a real iCloud upload or eviction.</td></tr>
<tr><td>Retained older copies</td><td><code>sync --update</code> keeps the displaced archive copy in <code>.versions/</code>.</td><td>Those versions share the archive location. The script does not create a separate, independent backup.</td></tr>
</tbody></table></div>
</section>
''')

pages['recovery.html'] = ('Inspect the state.<br><em>Repair what is certain.</em>', 'An interrupted run can leave a partial file, an unrecorded copy, or an index that needs updating. The first step is to describe what is actually on disk.', '''
<div class="trace diagram">
 <div class="box"><span class="small-label">First</span><h3>verify</h3><p>Take the lock, inspect the records and copies, and report findings without making repairs.</p></div><div class="arrow" aria-hidden="true">→</div>
 <div class="box"><span class="small-label">Then</span><h3>Review the findings</h3><p>Separate a known interrupted operation from differing data or a genuinely missing copy.</p></div><div class="arrow" aria-hidden="true">→</div>
 <div class="box"><span class="small-label">Where supported</span><h3>verify --fix</h3><p>Run the code’s specific repairs. Recheck the resulting archive and report anything unresolved.</p></div>
</div>
<section class="section">''' + heading(1, 'What can be repaired automatically?') + '''
<div class="table-wrap"><table class="result-table"><thead><tr><th>Finding</th><th>What the code found</th><th>What --fix can do</th></tr></thead><tbody>
<tr><td><code>[interrupted]</code><br><code>[complete-archive]</code></td><td>Both copies exist; the local copy matches the expected archived data after the archive checks.</td><td>Remove the matching local copy to finish archiving.</td></tr>
<tr><td><code>[missing-remote]</code></td><td>The archive copy is missing, but a local file exists.</td><td>Drop the stale record or v1 row. Keep the local file.</td></tr>
<tr><td><code>[orphan]</code></td><td>The archive contains something with no record.</td><td>Remove it only if it matches the local copy. Unknown or differing data is left alone.</td></tr>
<tr><td><code>[half-upgraded]</code></td><td>A v1 entry has started moving into format 2 areas.</td><td>Resume its upgrade, verifying and recording what moved.</td></tr>
<tr><td><code>[manifest]</code><br><code>[index]</code><br><code>[mirror]</code></td><td>A torn final journal line or an index/mirror that needs rewriting.</td><td>Discard the torn tail or regenerate the recorded maps. A moved root can be settled through the registry.</td></tr>
<tr><td><code>[leftover]</code></td><td>Recognized partial output, restore temp files or index temp files.</td><td>Remove the recognized leftover outputs.</td></tr>
<tr><td><code>[park-setting]</code></td><td>One local copy of the park setting is missing.</td><td>Rewrite the setting copies. It does not run the folder-parking operation.</td></tr>
</tbody></table></div>
<div class="note"><p><strong><code>--fix</code> is a writer.</strong> It can remove duplicate/temporary copies, drop stale records, rewrite indexes, and finish a partial legacy upgrade. Its scope is broader than “only delete byte-identical duplicates.” Read its findings first.</p></div>
</section>
<section class="section">''' + heading(2, 'What waits for a person?') + '''
<div class="two-col"><article>
 <div class="definition"><h3>Different contents or corrupt copies</h3><p><code>[changed]</code>, <code>[conflict]</code> and <code>[corrupt]</code> need investigation. The fixer does not choose which differing file should win.</p></div>
 <div class="definition"><h3>No known copy</h3><p><code>[lost]</code> means neither expected copy is present. The fixer cannot recreate missing bytes. An unknown format requires a suitable reader.</p></div>
</article><article>
 <div class="definition"><h3>Ghosts and conflict copies</h3><p>Leftovers at an old archive root and names such as <code>ICLOUD 2.md</code> are reported for comparison. They are not automatically deleted.</p></div>
 <div class="definition"><h3>Files inside the parked tree</h3><p><code>[parked-file]</code> is reported and left alone. Folder parking uses <code>tidy</code>; a normal <code>verify --fix</code> does not park folder trees.</p></div>
</article></div>
</section>
<section class="section">''' + heading(3, 'Upgrade in a deliberate order') + '''
<ol class="step-list">
 <li><div><strong>Discover and plan.</strong><p>Use status/registry to locate the requested archive. <code>upgrade --plan</code> describes conversions, folder parking, relocation, refusals and space/upload costs. Honor an approval you have already given for that scope.</p></div></li>
 <li><div><strong>Convert entries and save the setting.</strong><p>Convert v1 entries file by file. Retain each old row until the new records and required folder structure are settled. A park step saves the local folder name before actual folder moves.</p></div></li>
 <li><div><strong>Relocate last.</strong><p>A root move waits for reported uploads, records the intended target, then renames the root once. The registry keeps its old location. A pending upload can refuse or defer a move rather than keep waiting forever.</p></div></li>
 <li><div><strong>Verify and report.</strong><p>Check each upgraded project, its upload state, and any eviction result. <code>--all</code> spans registered archives, so confirm the planned project list carefully.</p></div></li>
</ol>
<details><summary>What about an archive made by hand?</summary><p><code>import --kind mirror</code> checks the listed paths, sizes and optional MD5 values before adopting files. <code>import --kind split</code> checks compressed parts and the full stream before and after moving them. The agent shows a plan and checks authorization first.</p><p>A mismatch is reported. The agent must not edit an old manifest to make it pass; <code>--accept-mismatch</code> applies only to explicitly approved named mirror-import files.</p></details>
<details><summary>What does --via-history do?</summary><p>For a read or restore fallback, the script chooses the matching authentic frozen release, checks its recorded SHA-256 sums, and runs it with an absolute file path. This rebuild only has its own frozen 2.3.1. Original releases were unavailable, so their historical fallback readers cannot be run until authentic files are supplied.</p></details>
</section>
''')


# Check names are explanations of actual guards, not test totals.
checks = []
def check(name, phase, response, trigger, effect, purpose, source):
    checks.append(dict(name=name, phase=phase, response=response, trigger=trigger, effect=effect, purpose=purpose, source=source))
check('The correct project root', 'scope archive restore read', 'report', 'The current directory is nested below an index, Git root or CLAUDE.md.', 'Resolve the highest archive index/manifest first, then Git, then the highest CLAUDE.md. Print repo: for the agent to check.', 'A month folder with its own instructions should not silently split one project’s archive.', 'archive.py · find_repo')
check('Archive belongs to this project', 'scope archive restore upgrade', 'refuse', 'The archive mirror names a different project ID.', 'Refuse to write into that archive root.', 'Two projects sharing a nested path must not overwrite each other’s records.', 'archive.py · Store.__init__')
check('Paths stay inside the project', 'scope archive restore read', 'refuse', 'An explicit path resolves outside the selected project, or the whole project root is named where disallowed.', 'Refuse the path before archiving/restoring it.', 'Limits the operation to the intended project. Stored record paths also reject absolute paths and parent traversal.', 'archive.py · checked_rel / stored_rel')
check('Git and archive index paths are protected', 'scope archive import', 'refuse', 'A direct path or imported record tries to target .git, ICLOUD.md or ICLOUD.manifest.jsonl.', 'Refuse protected paths; folder collection skips protected names, including a submodule’s .git file.', 'Keeps archive bookkeeping and Git metadata out of the archive payload.', 'archive.py · checked_rel / stored_rel / sync_command')
check('Names can be represented safely', 'scope archive restore import', 'refuse', 'A path contains a backtick, forbidden control characters or an unsafe stored-record path.', 'Refuse ambiguous or unsafe names. Normalize supported Unicode names to NFC.', 'Avoids table corruption and unsafe record resolution.', 'archive.py · checked_rel / stored_rel')
check('A symlink is not followed into user data', 'scope archive import', 'refuse', 'A link is named directly or an import source is a link; path parents can also contain links.', 'Refuse direct/imported links and symlink traversal. Links encountered during ordinary folder collection are skipped and reported.', 'Avoids archiving a link target outside the intended files.', 'archive.py · checked_rel / sync_command / mirror_plan / mirror_import')
check('Case-only collisions are refused', 'scope archive import', 'refuse', 'A path differs only in letter case from another selected path, recorded path or archive destination.', 'Refuse the collision instead of treating the names as safely distinct.', 'iCloud paths cannot safely depend on case-only distinctions.', 'archive.py · sync_command / sync_one / mirror_plan')
check('A no-delete rule needs an explicit override', 'scope archive', 'refuse', 'A matching prohibition appears in CLAUDE.md, AGENTS.md or .claude/CLAUDE.md at the project root.', 'Quote the matching lines and refuse unless --allow-protected is supplied. The agent must obtain your explicit override first.', 'Archiving removes the working file, so project removal rules matter.', 'archive.py · check_protection; SKILL.md · rule 3')
check('The requested scope is actually authorized', 'scope archive upgrade import', 'rule', 'The request is vague, or a plan/protection override needs a user decision.', 'The agent asks about vague archive paths and checks authorization for import/upgrade plans and protected overrides. Existing explicit approval is honored.', 'A behavioral rule controls the agent’s choices; the CLI alone cannot establish your intent.', 'SKILL.md · rules 1 / 3 / import; archive-icloud-upgrade/SKILL.md · procedure')
check('Recently modified files stay local', 'archive', 'skip', 'A file’s modification time is younger than the default 10 minutes, or it becomes young before the locked operation.', 'Skip it. The agent must not lower --min-age to bypass a running job.', 'Reduces the chance of capturing a file while it is being written.', 'archive.py · live_reason / sync_one')
check('Known open file handles keep a file local', 'archive', 'skip', 'lsof reports that a process has the file open.', 'Skip the file and report it. A file-level lsof failure currently yields no known handles; other guards still apply.', 'Avoids disturbing another program’s active file, within the limits of the process query.', 'archive.py · lsof_paths / live_reason')
check('Busy-folder markers keep a file local', 'archive', 'skip', 'The file’s immediate directory contains a name ending .cursor, or containing .partial-, .tmp- or .restoring-.', 'Skip files in that directory as live.', 'Recognizes common signs of an unfinished writer or transfer.', 'archive.py · BUSY / live_reason')
check('SQLite-style sidecars keep a database local', 'archive', 'skip', 'The file has a -wal, -shm or -journal companion, or is itself such a sidecar.', 'Skip it while the database may be active.', 'A database and its live sidecars should not be separated during archiving.', 'archive.py · live_reason')
check('Files inside a v1 entry are not archived again', 'archive', 'skip', 'A selected file is already covered by an older whole-file or whole-directory v1 row.', 'Skip that file as inside a v1 entry.', 'Prevents overlapping v1 and format-2 claims over the same data.', 'archive.py · sync_command / sync_one')
check('A v1 entry cannot occupy a v2 storage area', 'archive import', 'refuse', 'An older row sits under reserved storage names such as files, .big or .versions.', 'Refuse sync/import until that overlap is resolved through the supported workflow.', 'Those names have storage meanings in format 2.', 'archive.py · Store.check_v1_overlap')
check('Changed local files need --update', 'archive', 'report', 'The local SHA-256 differs from the file’s existing archive record.', 'Keep it local and report changed unless --update was explicitly approved. An update retains the previous archive copy in .versions/.', 'A routine sync must not silently replace an older archived version.', 'archive.py · sync_one; SKILL.md · rule 5')
check('An unrecorded archive destination is checked', 'archive', 'refuse', 'An archive file/pack exists at the destination without a matching active record.', 'Adopt an identical raw file after checking its hash; refuse other existing data instead of overwriting it.', 'Supports a safe rerun after a crash while preserving unknown or different copies.', 'archive.py · sync_one')
check('There is room for the copy or decompression', 'archive restore read upgrade', 'refuse', 'The relevant volume has less than the required bytes plus the configured margin; the default margin is 1 GiB.', 'Refuse up front. New archive partials are removed if copying fails, including a reported disk-full failure.', 'Avoids starting an operation with obviously insufficient space. The check is an estimate, not a reservation.', 'archive.py · ensure_free / estimate_packed / sync_one')
check('A raw copy has the expected SHA-256', 'archive restore', 'refuse', 'The destination’s fingerprint differs from the expected source/record fingerprint.', 'Reject the copy and remove the temporary output; do not accept it as the successful result.', 'Checks content, rather than relying only on the filename or size.', 'archive.py · copy_verified / restore_one')
check('A compressed pack’s parts and stream match', 'archive restore read', 'refuse', 'A part is missing, linked, the wrong size or hash, or disagrees with MANIFEST.json and SHA256SUMS.', 'Refuse the invalid pack. Creation and full decompression also check the complete original size and hash; a head-only read stops early.', 'Checks both the compressed containers and the reconstructed file where a full stream is processed.', 'archive.py · read_pack / pack_file / unpack / decompress_parts')
check('The source did not change during copying', 'archive', 'refuse', 'The source size or modification time differs after the copy and durable record were written.', 'Keep the local source and report that the verified archive copy was retained.', 'A writer racing the copy should not have its newer local work removed.', 'archive.py · sync_one')
check('The receipt is durable before local removal', 'archive', 'repair', 'A file is about to be removed from the working project after a successful copy.', 'Append its record and fsync before unlinking the source. Compact changed state into the indexes and mirror, including a failed run that already made durable changes.', 'Allows later verification to reconstruct an interrupted state.', 'archive.py · Store.append / sync_one / sync_command')
check('A newer cloud generation is settled first', 'archive restore import upgrade', 'repair', 'The mirror is adopted because the checkout is missing its maps or its saved generation is older.', 'Save the adopted state locally under the lock before changing it. Read-only commands can report it without saving.', 'Newly appended records must not be discarded by a later reload of the newer mirror.', 'archive.py · Store.__init__ / Store.settle')
check('Cooperating writers take a project lock', 'archive restore import upgrade', 'wait', 'Another participating process on this Mac holds the same project lock.', 'Wait up to the configured timeout (120 seconds by default), then refuse if the lock cannot be obtained.', 'Serializes participating file changes. This advisory local lock does not coordinate separate Macs.', 'archive.py · lock / sync_one / restore_one')
check('Restore will not overwrite a local path', 'restore', 'refuse', 'A file or link already exists at the destination, including one that appears during the operation.', 'Refuse before replacing that local path; a new temporary restore output is cleaned up on failure.', 'Preserves local work rather than guessing that the archive should win.', 'archive.py · restore_one')
check('The expected archive copy must exist', 'restore archive verify', 'refuse', 'An active record points to a missing or invalid archive copy.', 'Refuse restore/finishing that copy and direct the user toward verify. Verification distinguishes a local-only file from a lost file.', 'A record by itself is not proof that the data still exists.', 'archive.py · check_remote / restore_one / verify_command')
check('Restored bytes and metadata match the record', 'restore', 'refuse', 'A restored format-2 file has the wrong size or SHA-256.', 'Reject the output. On success restore the recorded mode and mtime before the final rename.', 'Brings back the recorded bytes and original file metadata.', 'archive.py · restore_one')
check('Unknown record formats are not guessed', 'read restore archive verify', 'refuse', 'An active per-file record uses a format this engine does not understand.', 'Refuse relevant reads/restores/updates with an update-the-skill message; status and verify report unknown-format.', 'A future storage layout needs the correct reader.', 'archive.py · supported / record_states / verify_command')
check('A large compressed read needs --full', 'read', 'refuse', 'A compressed file’s original size exceeds 10,000,000,000 bytes and a full read was requested without --full.', 'Refuse that full read and suggest read --head N. An explicitly approved --full can decompress to a temp file after checking space.', 'Avoids accidentally spending huge amounts of local disk on a quick inspection.', 'archive.py · read_command')
check('A mirror import belongs to a manifest row', 'import', 'refuse', 'A foreign file is not covered by any supplied CSV row, or a destination collides with local/archived data.', 'Refuse that file. Rows marked deleted are skipped; with no CSV, the foreign relative path is used.', 'An import should adopt the mapped archive files without overwriting project data.', 'archive.py · mirror_plan')
check('A mirror import matches size and MD5', 'import', 'refuse', 'A supplied size or MD5 differs from the actual foreign file.', 'Keep the mismatching source. A named --accept-mismatch can accept that MD5 mismatch only after your explicit confirmation; both values are recorded.', 'Preserves the old manifest as evidence. MD5 is used for legacy comparison; the new record also has SHA-256.', 'archive.py · mirror_import')
check('An iCloud import placeholder is not the data', 'import', 'refuse', 'A mirror import encounters an evicted .name.icloud placeholder.', 'Refuse it and request download first. Empty-tree cleanup preserves such placeholders.', 'A placeholder must not be mistaken for the original file or disposable litter.', 'archive.py · mirror_plan / remove_empty_tree')
check('A split import checks before and after moving', 'import', 'refuse', 'A part hash, part size or full decompressed size/hash differs from the split manifest.', 'Refuse a failed preflight before moving. A failed post-move stream check reports that the parts moved but remain unrecorded; inspect with verify.', 'Detects invalid compressed inputs and preserves a resumable import plan.', 'archive.py · split_metadata / split_import')
check('Import origins and interrupted moves are tracked', 'import', 'repair', 'A mirror journal or split import plan shows a move interrupted before all recording finished.', 'Resume the known move, check it and retain imported_from provenance. CSV rows gain an imported_to column rather than being deleted.', 'Retains a trail back to the foreign archive and supports retry after a crash.', 'archive.py · resume_import / mirror_import / split_import / write_import_csv')
check('A folder with live content stays in place', 'folders', 'keep', 'A project folder still holds a file or link, or a child that has to stay live.', 'Keep that folder. An empty folder with no archived history does not park by itself; empty children can follow a qualifying parent.', 'Only structure emptied by archiving is eligible to park.', 'archive.py · FolderPlan.__init__')
check('A .keep file pins its folder', 'archive folders', 'keep', 'A folder contains .keep.', 'Keep the marker locally and keep its folder. Directly naming .keep, .DS_Store or a .name.icloud file for sync is refused.', 'Supports jobs that expect an existing output folder.', 'archive.py · sync_command / FolderPlan.__init__')
check('Folder age uses a ledger of this run’s changes', 'folders', 'keep', 'A folder was recently changed before the run, or a change cannot be explained by the run’s own ledger.', 'Keep the folder. Track before/after mtimes and external changes; restore parent times touched by bookkeeping moves.', 'Distinguishes another program’s work from the script removing or restoring its own files.', 'archive.py · Ledger / FolderPlan.guard / FolderPlan.apply')
check('Open folders and working directories stay put', 'folders', 'keep', 'A process has something open in a folder, works in it, or it contains the script’s own working directory.', 'Mark that path and its ancestors as in use and keep them.', 'Avoids moving a directory another process currently depends on.', 'archive.py · FolderPlan.__init__ / FolderPlan.guard')
check('A failed folder lsof query blocks all moves', 'folders', 'refuse', 'The folder process query is missing, times out or returns an unexpected failure.', 'Block all folder moves for that plan rather than assuming nothing is open.', 'For folder moves, an unavailable process check is treated as uncertainty that stops the move.', 'archive.py · lsof_paths / tidy_plan')
check('Linked or excluded folders stay in place', 'folders', 'keep', 'A project symlink points into the folder, or the folder contains an excluded path.', 'Keep the affected folder/ancestors and report the reason.', 'Avoids breaking known links and respects the scope’s exclusions.', 'archive.py · FolderPlan.__init__ / FolderPlan.guard')
check('The park-folder name must be available', 'folders upgrade', 'keep', 'The requested park name is occupied by real files, an incompatible case variant, a link, or recorded archive paths.', 'Keep folders in place and explain why. An approved upgrade can plan a different plain --park-dir name.', 'Avoids taking over the project’s existing _archive/ content.', 'archive.py · Store.taken / validate_park_name / upgrade_plan')
check('A racing file makes rmdir fail', 'folders', 'keep', 'A file appears in a source folder after the movement plan was made.', 'rmdir refuses the nonempty source. Report that it did not move and remove a newly created empty twin if possible.', 'Normal files are not swept into the park tree by a whole-tree rename or recursive deletion.', 'archive.py · FolderPlan.apply')
check('Unexpected parked files are left alone', 'folders verify', 'report', 'A normal file or link is found inside the parked folder structure.', 'Report parked-file. The folder mover and verifier do not move or delete that user file.', 'Makes unexpected content visible without choosing a destination for it.', 'archive.py · FolderPlan / verify_command')
check('Moved folders are checked on disk', 'folders', 'report', 'A reported folder move is missing from its destination or still exists at its source.', 'Report the post-check problem instead of claiming a clean move.', 'Checks the actual result rather than trusting the in-memory plan.', 'archive.py · FolderPlan.problems / RunReport.summary')
check('Upload status gates eviction and relocation', 'cloud upgrade', 'wait', 'macOS does not report archive files as uploaded/evicted.', 'The helper will not evict a reported not-uploaded file. A non-park upgrade waits before changing the root, and may refuse or defer relocation when uploads remain pending.', 'A root rename during upload can leave confusing ghost paths. Upload completion is also required before claiming disk can be reclaimed.', 'icloud_status.swift; archive.py · pending_upload / wait_uploaded / upgrade_archive')
check('Eviction is checked from dataless state', 'cloud', 'report', 'An eviction request returns but some archive paths still have local bytes.', 'Wait up to 30 seconds for dataless state, report remaining local paths, and show the observed disk-free change.', 'A request succeeding is not the same as confirming that local storage was released.', 'archive.py · cloud_command')
check('Differing and unknown copies need review', 'verify', 'report', 'Verification finds changed/conflicting data, corruption, a ghost root, an unknown orphan or an iCloud conflict copy.', 'Report it and preserve uncertain contents. Automatic orphan removal is limited to a matching local copy.', 'The fixer must not pick a winner among competing or unexplained files.', 'archive.py · verify_command / orphan_items')
check('Stale and interrupted state has specific repairs', 'verify', 'repair', 'Verification finds a known interrupted copy, torn journal tail, stale map, local-only file, recognized temp output or half-complete legacy conversion.', 'With --fix, apply only the corresponding supported repair. This can remove duplicates/partials, drop records, rewrite maps or finish that conversion.', 'Recovery is based on the observed copies and recorded state, not a blanket cleanup.', 'archive.py · verify_command')
check('History code must match its recorded checksums', 'read restore', 'refuse', 'A --via-history release is unavailable, has unsafe checksum paths, lacks required entries or differs from SHA256SUMS.', 'Refuse to run it. For a valid release, run the frozen reader with an absolute target path.', 'Detects code changes relative to the expected release bytes. Authentic missing historical code is required; it is not fabricated.', 'archive.py · via_history')


# Current target checks supplement the inherited file/folder checks.
check('A registered target is available and has the right identity', 'scope archive read restore verify import upgrade', 'refuse', 'The root is offline, moved, linked, unmarked, or has a different identity marker.', 'Refuse before classifying absent archive data or making repairs. Never create a fallback directory.', 'A disconnected drive must not become a missing-data cleanup.', 'storage.py · Target.available')
check('The mounted external volume UUID matches', 'scope archive restore verify', 'refuse', 'A different external volume is mounted at the recorded path.', 'Compare the live filesystem volume UUID with the registered UUID; refuse a mismatch.', 'A familiar volume name does not establish disk identity.', 'storage.py · volume_uuid / Target.available')
check('A project stays bound to its recorded target', 'scope archive restore read', 'refuse', 'The default changed or --target conflicts with the manifest descriptor.', 'Use the recorded target; refuse a conflicting explicit selection.', 'Changing a default does not migrate existing archives.', 'archive.py · configure_session; storage.py · select_target')
check('Archive and project roots cannot contain each other', 'scope archive import', 'refuse', 'The archive root is inside the project or the project is inside its archive.', 'Refuse the overlap before archiving.', 'Avoids recursively archiving archive data and bookkeeping.', 'storage.py · Target.check_repo')
check('Archive storage paths do not traverse symlinks', 'scope archive read restore import upgrade', 'refuse', 'An archive data, mirror or publication path traverses a symbolic link.', 'Refuse before writing or reading the unintended destination.', 'Protects the archive side as well as the project side.', 'archive.py · guard_archive_path / publish')
check('Fallback publication creates a fresh destination', 'archive restore import upgrade', 'refuse', 'Exclusive rename is unsupported or a move crosses filesystems.', 'Create with O_EXCL/mkdir, copy and hash, flush a receipt, then remove only verified source contents. Existing destinations are refused.', 'ExFAT publication is recoverable but not an atomic directory rename.', 'storage.py · publish_verified / exclusive_copy')
check('Publication recovery recognizes its own created object', 'verify', 'repair', 'A receipt describes a partial or complete destination after interruption.', 'Check the content fingerprint and object tag/device before an allowed repair. Preserve unknown or nonempty uncertain partial directories.', 'ExFAT inode numbers can change after metadata writes; a replacement must not be deleted on an inode assumption.', 'storage.py · repair_publication / publication_tag')
check('Unresolved publication sources remain available', 'verify', 'report', 'A pending receipt still needs its partial source for repair.', 'Protect that source from generic leftover cleanup.', 'Recovery must not erase its own only known input.', 'archive.py · verify_command')
check('AppleDouble metadata cannot consume ordinary user files', 'archive', 'skip', 'A user file has a literal ._ path component or an ordinary ._ sibling.', 'Keep both conflicting paths local. Skip genuine paired AppleDouble metadata only after identifying its header.', 'macOS/ExFAT can treat ._ names as metadata companions and remove them with the base file.', 'storage.py · apple_double; archive.py · reserved_metadata_collision')
check('Provider capabilities determine upload claims', 'cloud archive upgrade', 'report', 'The target is local/SSD, native iCloud, a Google Drive folder or direct API target.', 'Local needs no upload. iCloud uses its helper. The mounted Google folder reports upload unknown; direct API verifies the cloud bytes and maps before source removal.', 'A filesystem copy does not establish remote cloud durability.', 'archive.py · cloud_command / upgrade_archive / RunReport.summary')
for item in checks:
    item['source'] = item['source'].replace('archive-icloud-upgrade/SKILL.md · procedure','references/recovery-and-upgrade.md').replace('SKILL.md · rules 1 / 3 / import','SKILL.md · Archive and sync / Import')
    if item['name'] == 'Known open file handles keep a file local':
        item['effect'] = 'Skip a known open file. Registered targets also skip/refuse when lsof cannot answer; explicit legacy-environment compatibility keeps the older permissive file behavior.'
    if item['name'] == 'Git and archive index paths are protected':
        item['trigger'] += ' Generic ARCHIVE.md and ARCHIVE.manifest.jsonl are protected too.'
    if item['name'] == 'Upload status gates eviction and relocation':
        item['trigger'] = 'A native iCloud target has pending uploads; Google Drive has no supported remote confirmation.'
        item['effect'] = 'iCloud waits before data relocation and gates eviction on upload. Google data conversions/relocations and eviction are refused. Local targets have no cloud wait.'


check('Direct Drive pins the account, folder and marker', 'scope cloud archive restore verify', 'refuse', 'The credential resolves to another account, the root/marker moved, or access is unavailable.', 'Refuse the operation; do not remove original files or guess another destination.', 'Account and folder identity matter even when there is no mounted volume.', 'drive_api.py · validate_target')
check('Resumed uploads retain their file ID and query acknowledged bytes', 'archive cloud', 'repair', 'The upload was interrupted, its reply was lost, or its session expired.', 'Keep the preallocated ID and private session journal; query the server range, resume, or restart the expired session without creating duplicate file objects.', 'Network completion cannot be inferred from the bytes the client tried to send.', 'drive_api.py · Client.upload / acknowledged')
check('Cloud SHA-256 precedes local removal', 'archive cloud restore', 'refuse', 'The remote size/hash differs, or Google does not expose SHA-256.', 'Compare the expected size/hash and location; download-and-hash when needed. Keep the original on mismatch.', 'A successful upload response alone is insufficient.', 'drive_api.py · Client.verify')
check('Cloud maps must also be verified before removing the source', 'archive cloud', 'repair', 'Data uploaded but writing its local or cloud receipt failed.', 'Retain the source and operation journal. Resume the supported transaction.', 'A surviving file needs a usable map for recovery.', 'drive_archive.py · Store.save / archive_one')
check('Direct restore owns its output before consuming cloud copies', 'restore verify', 'refuse', 'A destination appears, a restored file is replaced, or returned bytes differ.', 'Refuse overwrite; use the object tag and hash for recovery; keep uncertain cloud copies.', 'The restored file must exist and be verified before the active cloud copy goes to Trash.', 'drive_archive.py · restore_one / fetch')
check('Real manifest edits are distinguished from metadata-only versions', 'archive cloud', 'refuse', 'The mirror ID or its contents change since the command loaded it.', 'Refuse an observed competing content change. Allow a metadata-only version increment when the trusted manifest hash is unchanged.', 'Google versions include metadata changes; comparing only the version can cause false refusals.', 'drive_archive.py · Store.save')

responses={'refuse':'Refuse','skip':'Skip file','keep':'Keep folder / path','report':'Report','repair':'Record / repair','wait':'Wait / gate','rule':'Agent rule'}
phase_labels=[('scope','Scope & identity'),('archive','Archive'),('read','Read'),('restore','Restore'),('folders','Folders'),('import','Import'),('upgrade','Upgrade'),('verify','Verify'),('cloud','Upload & eviction')]
check_html=''
for number,item in enumerate(checks,1):
    check_html+=f'''<details class="check" data-check data-phase="{item['phase']}" data-response="{item['response']}" id="check-{number}">
<summary><span class="check-number">{number:02d}</span><span class="check-title">{escape(item['name'])}</span><span class="pill {item['response']}">{responses[item['response']]}</span></summary>
<div class="check-detail"><div class="two-col"><div><span class="small-label">What is checked</span><p>{escape(item['trigger'])}</p></div><div><span class="small-label">What happens</span><p>{escape(item['effect'])}</p></div></div><span class="small-label" style="margin-top:15px">Why it matters</span><p>{escape(item['purpose'])}</p><p class="source-note">{escape(item['source'])}</p></div></details>'''
phase_options=''.join(f'<option value="{key}">{label}</option>' for key,label in phase_labels)
response_options=''.join(f'<option value="{key}">{label}</option>' for key,label in responses.items())
pages['checks.html'] = ('What gets checked.<br><em>What happens next.</em>', f'{len(checks)} named checks from the rebuilt engine and skill instructions. Search a situation, filter an operation, and open a check to see its trigger and response.', '''
<div class="filters js-only"><div class="filter-grid">
<label for="check-search">Search the checks<input id="check-search" type="search" placeholder="Try: symlink, hash, upload…" autocomplete="off"></label>
<label for="check-phase">Operation<select id="check-phase" aria-label="Operation"><option value="">All operations</option>''' + phase_options + '''</select></label>
<label for="check-response">Response<select id="check-response" aria-label="Response"><option value="">All responses</option>''' + response_options + '''</select></label>
</div><div class="filter-footer"><span id="check-count" role="status" aria-live="polite"></span><button class="reset" id="check-reset" type="button">Reset filters</button></div></div>
<noscript><p class="note">All checks appear below. Enable JavaScript for search and filters.</p></noscript>
<p class="caption">“Refuse” stops that unsafe operation. “Skip” leaves a live file local. “Keep” leaves folder structure in place. “Agent rule” is a behavior the skill asks the agent to follow. One check can apply to several operations; this is not the mutation-test count.</p>
<div id="check-list">''' + check_html + '''</div><div class="empty" id="check-empty" hidden><h3>No matching checks</h3><p>Try fewer words or reset the filters.</p></div>
''')

# Reconcile the earlier handbook against Archive General 3.1.3.
def amend(page, replacements, prefix='', suffix=''):
    title, lead, body = pages[page]
    for before, after in replacements:
        if page == 'workflow.html' and before == '<ol class="step-list">':
            body = body.replace(before, after, 1)
            continue
        title, lead, body = (v.replace(before, after) for v in (title, lead, body))
    pages[page] = (title, lead, prefix + body + suffix)

provider_table='''<div class="table-wrap"><table><thead><tr><th>Target</th><th>What success establishes</th><th>Upload / eviction</th></tr></thead><tbody>
<tr><td>SSD / local disk</td><td>A checked filesystem copy and record, followed by working-file removal. Another volume can take bytes off the project disk.</td><td>No cloud upload or eviction needed. Same-volume moves may reclaim little space.</td></tr>
<tr><td>Native iCloud</td><td>A checked copy in the Mac’s iCloud folder.</td><td>Check upload with the Swift helper; evict only uploaded files. Copy success alone does not confirm upload.</td></tr>
<tr><td>Google Drive API</td><td>A resumable upload whose remote bytes and archive record are verified before local removal.</td><td>Cloud verification supported. No mounted-folder eviction needed.</td></tr>
<tr><td>Google Drive folder</td><td>A checked copy in the mounted/synced folder.</td><td>Remote upload is unknown. Automatic eviction is unsupported. Check the Drive app separately.</td></tr>
</tbody></table></div>'''
pages['index.html'] = ('One archive skill.<br><em>Your choice of drive.</em>', 'Archive General moves the files you name to a registered storage target, keeps a map in your project, and checks the copy before removing the working file.', '''
<div class="diagram intro-art"><div class="diagram-title"><span>The system in one picture</span><span>Archive General 3.1.3</span></div><div class="trace">
<div class="box"><span class="icon">01</span><h3>Your project</h3><p>Live files stay here. ARCHIVE.md and the manifest remember archived paths.</p></div><div class="arrow">→</div>
<div class="box"><span class="icon">02</span><h3>Your registered target</h3><p>An SSD, local disk, native iCloud folder, Google Drive folder or direct Drive API target holds the bytes.</p></div><div class="arrow">↔</div>
<div class="box"><span class="icon">03</span><h3>A durable receipt</h3><p>Hashes, original mode/time, target identity, storage format and writer version support verification and restore.</p></div></div></div>
<section class="section">''' + heading(1,'One skill, all capabilities') + '''
<p><code>archive-general</code> handles setup, archive/sync, reading, restore, verify/recovery, import and upgrade. The relevant references live inside the same skill. <code>archive.py</code> runs every operation; <code>storage.py</code> checks drive identity and filesystem publication.</p>
<div class="note blue"><p>''' + TARGET_NOTE + ''' Direct Drive is a separate target and never migrates existing archives implicitly.</p></div>
''' + provider_table + '''</section>
<div class="link-grid"><a href="workflow.html"><span class="small-label">Follow the bytes</span><h3>Watch a file move</h3><p>Choose a provider and see each copy, receipt and removal step.</p></a><a href="security.html"><span class="small-label">Understand protection</span><h3>Safety and its limits</h3><p>Drive identity, hashes, live files, publication and recovery.</p></a><a href="checks.html"><span class="small-label">Get specific</span><h3>Search the checks</h3><p>Filter actual checks by operation and response.</p></a></div>
<section class="section">''' + heading(2,'Archive, read and restore') + '''<dl class="glossary"><dt>Archive</dt><dd>Verify a copy on the selected target, record it durably, then remove the working file.</dd><dt>Read</dt><dd>Inspect archived bytes in place or sample a compressed stream. No restoration.</dd><dt>Restore</dt><dd>Verify the returned bytes, restore metadata, then remove the active archive copy and record.</dd><dt>Evict</dt><dd>On native iCloud only, request removal of uploaded cached bytes while keeping a downloadable path.</dd></dl></section>
''')

amend('workflow.html', [], prefix='<div class="note green"><p><strong>Direct Google Drive:</strong> upload resumably, verify the actual cloud file, save and verify the archive record, then remove the unchanged local original. Choose the API walkthrough below. No mounted-folder eviction is needed.</p></div>')
amend('workflow.html', [
('Example: a new, ordinary <code>data/august.csv</code>. Use Next to see where its bytes and record are at each step.', 'Choose a target type for this illustration. No archive commands run. The identity checks happen before any data change.'),
('<div class="sim js-only" id="archive-simulation">', '<label class="js-only" for="provider-select">Storage target</label><select class="js-only" id="provider-select"><option value="local">SSD / local disk</option><option value="icloud">Native iCloud</option><option value="google-drive">Google Drive folder</option><option value="google-drive-api">Google Drive API</option></select><div class="sim js-only" id="archive-simulation">'),
('<ol class="step-list">','<p class="caption">Without JavaScript: the first four numbered steps below apply to all providers. The last step describes native iCloud only. Google upload remains unknown and eviction is unsupported.</p><ol class="step-list">'),
('rename', 'publish'),
('siblings in iCloud', 'siblings on the target'),
('active iCloud archive copy', 'active archive copy'),
('# Once upload is confirmed:', '# Native iCloud only, once upload is confirmed:'),
], prefix='<div class="note blue"><p><strong>Before the file moves:</strong> validate the registered root, identity marker and external volume UUID. The manifest binds the project to that target. An offline or wrong drive stops the operation.</p></div>')

amend('storage.html', [
('ICLOUD.manifest.jsonl','ARCHIVE.manifest.jsonl'),('ICLOUD.md','ARCHIVE.md'),
('Inside iCloud Drive','On the selected target'),('claude-archive/','Archives/'),
('Default base: <code>~/Library/Mobile Documents/com~apple~CloudDocs/Archives/</code>.',TARGET_DEFAULT),
('Archived file bytes remain in iCloud.','Archived file bytes remain on the target.'),
('Files above 49,000,000,000 bytes, or explicitly packed files, use compressed parts.', 'Explicitly packed files use compressed parts. Local/SSD targets have no default raw limit; native iCloud keeps the conservative 49,000,000,000-byte raw limit.'),
('by: 2.3.1','by: 3.1.3'),
('A checkout’s parked-folder setting stays local; it is not adopted from the cloud mirror.','A checkout’s parked-folder setting stays local; it is not adopted from the archive mirror.'),
], suffix='''<section class="section">''' + heading(4,'Two identity records, one physical skill') + '''
<p>Machine-local <code>~/.config/archive-general/targets.json</code> selects named targets. Each target’s <code>.archive-general-target.json</code> proves which archive root it is; removable disks also have a pinned volume UUID. The project manifest and registry store its target descriptor.</p>
<p>Both agents use the same physical <code>skills/archive-general/</code> source. Historical code lives outside the discoverable skill tree in <code>config/shared/archive-general-history/</code>, reached through <code>.history</code>. The old iCloud command path is a compatibility wrapper with no separate SKILL.md.</p>
<div class="note"><p><strong>Legacy indexes remain supported.</strong> Existing projects keep <code>ICLOUD.md</code> and <code>ICLOUD.manifest.jsonl</code>. New projects use the generic names. Do not rename maps or rearrange the archive manually.</p></div></section>''')

amend('security.html', [
('The file live guard currently treats that failure as no known open handles, while its other checks still run.', 'Registered targets also stop a file operation when lsof cannot answer. Explicit legacy-environment compatibility retains the older permissive file guard.'),
('Raw archived files are set to mode <code>0444</code>.','Raw archived files are set to mode <code>0444</code> where the filesystem supports it.'),
('Helps prevent ordinary edits. A sufficiently privileged user can change permissions or delete files.','ExFAT does not enforce normal Unix permissions. Original file mode and time are stored in the manifest and reapplied on restore to a supporting filesystem.'),
('The 2026-10-18 rebuild tests used local sandboxes. They did not verify a real iCloud upload or eviction.','Direct Drive now has live API tests. The earlier actual-SSD results are preserved; the SSD was offline during this release hardware recheck. Native iCloud upload/eviction remains untested.'),
], prefix='''<div class="note blue"><p><strong>The right drive comes first.</strong> Recheck target marker and external volume UUID before writes and source removal. Refuse offline targets, conflicting project bindings, overlapping roots and archive-side symlink traversal.</p></div>''', suffix='''<section class="section">''' + heading(5,'What ExFAT changed') + '''
<div class="two-col"><article><h3>Publication can be a checked copy</h3><p>ExFAT rejected the exclusive rename used on the internal filesystem. The fallback exclusively creates its destination, streams and hashes the data, flushes it and a recovery receipt, then removes only known matching source contents.</p><p>This is not an atomic directory rename. Interruption can leave partials or duplicates. Recovery preserves a nonempty uncertain directory for inspection.</p></article><article><h3>Identity and metadata need care</h3><p>ExFAT file inode numbers changed after metadata writes in testing. A random publication tag attached to the created object and the device identity help recovery distinguish its partial from a replacement.</p><p>macOS also manages paired AppleDouble <code>._</code> files. Literal user <code>._</code> names and conflicting siblings stay local to avoid metadata aliasing. ACLs, Finder tags and every filesystem-specific flag are not universally preserved.</p></article></div></section>''')

amend('recovery.html', [
('Take the lock, inspect the records and copies, and report findings without making repairs.','Validate the target identity, take the lock, inspect records and copies, and report findings without making repairs.'),
('Remove the recognized leftover outputs.','Remove recognized outputs only when they are not protected inputs of an unresolved publication.'),
('A root move waits for reported uploads, records the intended target, then renames the root once. The registry keeps its old location. A pending upload can refuse or defer a move rather than keep waiting forever.', 'Local roots need no upload wait. Native iCloud waits for reported uploads. A checked move uses exclusive rename or journaled copy, with the registry retaining the old location. Google archive-data conversion and relocation are refused because remote upload cannot be confirmed.'),
('This rebuild only has its own frozen 2.3.1. Original releases were unavailable, so their historical fallback readers cannot be run until authentic files are supplied.', 'Authentic 2.3.1 is retained unchanged; 3.1.3 freezes the complete runtime including storage.py and the Swift helper. Earlier original releases are unavailable, so those historical executable tests remain skipped.'),
], prefix='''<div class="note"><p><strong>Offline is a refusal, not lost data.</strong> Reconnect the correct target and pass <code>target doctor</code> before verification. Do not replace its marker, create a lookalike directory or discard records.</p></div>''', suffix='''<section class="section">''' + heading(4,'Publication receipts') + '''
<p><code>[publication]</code> findings describe a checked move interrupted on a filesystem without exclusive rename. Recovery checks expected bytes and the destination object’s publication tag/device. It can remove a known incomplete file or finish known matching state; it retains replaced objects and uncertain nonempty directory contents.</p><p>Use the supported verifier and import/upgrade resume paths. Hand deletion of receipts, partials or source directories can remove the evidence needed to finish safely.</p></section>''')

# The evidence page is generated from the final recorded run, never optimistic constants.
test = report.get('pytest', {})
mutation = report.get('mutations', {})
forward = report.get('forward', {})
pages['evidence.html'] = ('Test results.<br><em>Clear practical limits.</em>', 'Validation for Archive General 3.1.3, recorded 25 October 2026. The full report and machine-readable evidence sit beside this handbook.', '''
<div class="metrics"><article class="metric"><span class="small-label">Behavioral cases passed</span><strong>''' + str(test.get('passed','Pending')) + '''</strong><p>''' + str(test.get('skipped','—')) + ''' skipped; missing history or offline SSD</p></article><article class="metric"><span class="small-label">Broken guards caught</span><strong>''' + str(mutation.get('killed','Pending')) + '''</strong><p>''' + str(mutation.get('skipped','—')) + ''' historical mutations skipped</p></article><article class="metric"><span class="small-label">Fresh-session workflows</span><strong>''' + str(forward.get('passed','Pending')) + '''</strong><p>live direct Drive archive/read/scoped restore</p></article></div>
<section class="section">''' + heading(1,'What ran') + '''<div class="table-wrap"><table><thead><tr><th>Evidence</th><th>Coverage</th><th>Boundary</th></tr></thead><tbody>
<tr><td>Actual ExFAT SSD (earlier 3.0.0 release)</td><td>Raw/packed bytes, Unicode/empty files, metadata restored to the internal filesystem, update retention, scoped restore, cross-device imports, legacy upgrade, injected interruptions, corruption and concurrent writers.</td><td>Earlier disposable tests passed. The SSD is offline for this release recheck; those 13 hardware cases are skipped, not passing evidence for 3.1.3.</td></tr>
<tr><td>Local provider fixtures</td><td>Target switching, wrong marker/UUID, unavailable roots, source/destination collisions, symlinks, process-query failures and recovery ownership checks.</td><td>UUID mismatch and offline conditions simulated. Mounted-folder fixtures have no upload service. Direct API has separate live Google tests.</td></tr>
<tr><td>Frozen 2.3.1</td><td>Authentic old runtime writes an archive; current runtime adopts, reads, upgrades and restores it. The frozen reader fallback is exercised.</td><td>Earlier original executables remain unavailable; no replacements were fabricated.</td></tr>
<tr><td>Independent agent workflows</td><td>Fresh agents used the single skill and saved their answers; final disk state and command logs were scored.</td><td>The independent direct Drive workflow is behavior evidence, not a universal correctness guarantee. Its initial refusal recovered safely and led to a regression fix.</td></tr>
</tbody></table></div><p><a href="../drive-api-report.md">Read the direct Drive report →</a> · <a href="../general-report.md">Earlier SSD report →</a> · <a href="../drive-api-validation.json">Current validation record →</a> · <a href="../general-appendices.md">Collected tests and mutation pairings →</a></p></section>
<section class="section">''' + heading(2,'What is not established') + '''
<div class="definition"><h3>Live cloud upload and eviction</h3><p>Live direct Drive uploads, checksums, interruption/resume, reading and restore were tested. Native iCloud upload/eviction remains untested. Mounted Google-folder upload status stays unknown. Migrating existing filesystem archives into API mode is refused until a separate migration is implemented and authorized.</p></div>
<div class="definition"><h3>Every possible disk or race failure</h3><p>Injected process interruptions and corruption are repeatable evidence. They do not simulate sudden power loss, failing hardware, every controller cache or arbitrary concurrent editors. Local advisory locks coordinate cooperating writers on this Mac.</p></div>
<div class="definition"><h3>Privacy and filesystem metadata</h3><p>The archive adds no encryption. Hashes rely on trusted records. ExFAT cannot enforce Unix read-only permissions; ACLs, tags and every filesystem-specific attribute are not universally guaranteed. Uncertain partial directories are retained for review.</p></div>
<div class="definition"><h3>Original transcription</h3><p>The recovered recording’s 3,019 visible editor lines remain preserved. The main appendix still differs from its embedded checksum prefix, so exact byte-for-byte recovery is uncertified. This updated skill is a separately tested implementation.</p></div>
</section><section class="section">''' + heading(3,'Historical evidence is preserved') + '''<p>The original reconstruction recorded 155 passed tests, 104 historical skips, 52 caught mutations and 11 passed agent scenarios. Its recovered guide, reports and authentic 2.3.1 frozen bytes were preserved. These earlier numbers and the 3.0.0 SSD results remain historical evidence, separate from the current 3.1.3 validation above.</p></section>''')

logo='''<svg width="35" height="35" viewBox="0 0 36 36" fill="none" aria-hidden="true"><path d="M4 11V7h11l4 4h13v19H4V11Z" stroke="#d9e3df" stroke-width="1.5"/><path d="M4 15h28" stroke="#6e8c9a"/><path d="m13 22 4 4 7-8" stroke="#e6a486" stroke-width="1.7"/></svg>'''
for index,(filename,label,description) in enumerate(chapters):
    title,lead,body=pages[filename]
    nav=''.join(f'<a href="{name}"'+(' aria-current="page"' if name==filename else '')+f'><span>{num:02d}</span>{escape(text)}</a>' for num,(name,text,_) in enumerate(chapters,1))
    prev = chapters[index-1] if index else None
    nex = chapters[index+1] if index < len(chapters)-1 else None
    footer=('<a href="'+prev[0]+'"><span>Previous chapter</span><strong>← '+escape(prev[1])+'</strong></a>' if prev else '<span>Begin with the idea.<br>Explore the details at your pace.</span>')
    footer+=('<a href="'+nex[0]+'"><span>Next chapter</span><strong>'+escape(nex[1])+' →</strong></a>' if nex else '<a href="index.html"><span>Back to the start</span><strong>The big picture ↗</strong></a>')
    doc=f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="{escape(lead,quote=True)}"><meta name="color-scheme" content="light"><title>{escape(label)} — Archive General Field Guide</title><link rel="icon" href="data:,"><link rel="stylesheet" href="style.css"><script defer src="guide.js"></script></head>
<body><a class="skip-link" href="#main">Skip to content</a>
<aside class="rail"><a class="brand" href="index.html">{logo}<span>Archive General<br>Field guide</span></a><div class="edition">Edition 3.1.3<br>How it works</div><button class="mobile-menu" type="button" data-menu aria-expanded="false" aria-controls="chapter-nav">Contents</button><nav id="chapter-nav" aria-label="Chapters">{nav}</nav><div class="rail-bottom"><strong>A local, offline guide</strong>Examples and diagrams only.<br>No archive commands are run.<a href="evidence.html">Evidence & known limits ↗</a></div></aside>
<div class="content"><header class="topline"><span>FIELD NOTES / {index+1:02d} OF 07</span><span class="version-info"><i class="dot" aria-hidden="true"></i>VERSION 3.1.3 · VERIFIED 25 OCT 2026</span></header><main class="page" id="main"><header class="hero"><div class="eyebrow">{index+1:02d} / {escape(description)}</div><h1>{title}</h1><p class="lead">{lead}</p></header>{body}<nav class="page-footer" aria-label="Chapter navigation">{footer}</nav><footer class="copyright"><span>ARCHIVE GENERAL / REGISTERED STORAGE</span><span>EXPLANATION & TEST RECORD: 25 OCT 2026</span></footer></main></div></body></html>'''
    (OUT/filename).write_text(doc+'\n')
(OUT/'checks-reference.json').write_text(json.dumps(dict(version='3.1.3',inspected='2026-10-25',checks=checks),indent=2)+'\n')
print('Built',len(chapters),'pages and',len(checks),'named checks')
