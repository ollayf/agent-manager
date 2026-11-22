"""Bounded file classification. Never open, execute, parse, or extract an asset.

Extensions give intent; signatures give evidence. Unknown types stay visible.
The catalog is deliberately finite: exhaustive inventory is possible, universal
format recognition is not. No external MIME tool or platform database is used.
"""
from pathlib import PurePosixPath
import re
import unicodedata

HEADER_BYTES = 8192
LARGE_FILE_BYTES = 5 * 1024 * 1024
TOTAL_ADDED_BYTES = 20 * 1024 * 1024

# One extension vocabulary, shared by detection, documentation, and census tests.
EXTENSIONS = {
    "source": "py pyi js jsx ts tsx mjs cjs c h cc cpp hpp cs java kt kts go rs rb php swift m mm sh bash zsh fish ps1 bat cmd lua r pl ex exs erl hs scala clj cljs dart vue svelte sql graphql gql proto tf tfvars scss sass less css html htm xml xsl xslt toml yaml yml ini cfg conf cmake gradle properties env",
    "text": "txt md markdown rst adoc org tex bib json jsonl ndjson csv tsv lock gitignore gitattributes editorconfig dockerignore npmignore nvmrc python-version tool-versions",
    "video": "mp4 m4v mov qt mkv webm avi wmv flv f4v mpeg mpg mpe m2v mpv mts m2ts ts vob ogv 3gp 3g2 mxf rm rmvb divx asf hevc h264 h265 y4m",
    "audio": "mp3 wav wave flac aac m4a m4b m4p ogg oga opus aif aiff aifc wma amr au snd caf mid midi ac3 eac3 dts ape alac pcm aiffc mka ra ram",
    "image": "png jpg jpeg jpe gif webp avif heic heif bmp dib tif tiff svg svgz ico icns psd psb ai eps exr hdr raw dng cr2 cr3 nef arw orf rw2 tga jp2 jxl pbm pgm ppm pnm",
    "document": "pdf doc docx dot dotx docm xls xlsx xlsm xlsb xlt xltx ppt pptx pptm pot potx pps ppsx odt ods odp rtf pages numbers key epub mobi azw azw3 djvu ps",
    "archive": "zip tar gz tgz bz2 tbz tbz2 xz txz zst zstd 7z rar lz lzma lzo cab iso dmg img deb rpm apk ipa war ear jar pak bundle br z",
    "executable": "exe dll so dylib a lib o obj wasm bin com msi app elf class dex pyc pyo beam",
    "database": "db sqlite sqlite3 db3 mdb accdb dbf wal journal dump bak",
    "dataset": "npy npz parquet arrow feather h5 hdf5 hdf mat fits nc netcdf fcs sav dta rds rdata",
    "model": "pt pth ckpt safetensors onnx pb tflite gguf ggml weights model mlmodel coreml",
    "serialized": "pkl pickle joblib marshal",
    "font": "ttf otf woff woff2 eot pfa pfb",
    "notebook": "ipynb",
    "log": "log trace har",
    "certificate": "pem crt cer der p12 pfx key keystore jks",
}
# Ambiguous suffixes are conservatively classified; .ts source beats transport
# stream intent, .key is signing material rather than a presentation by default.
OVERRIDES = {"ts": "source", "key": "certificate"}
SUFFIX_CATEGORY = {}
for category, suffixes in EXTENSIONS.items():
    for suffix in suffixes.split():
        SUFFIX_CATEGORY.setdefault("." + suffix, category)
SUFFIX_CATEGORY.update({"." + suffix: category for suffix, category in OVERRIDES.items()})
PLAIN_NAMES = frozenset({"readme", "license", "licence", "copying", "notice", "authors",
                         "changelog", "makefile", "dockerfile", "containerfile", "gemfile",
                         "rakefile", "procfile", "justfile", "brewfile", "go.sum", "go.mod"})
GENERATED_PARTS = frozenset({"node_modules", "__pycache__", ".venv", "venv", "dist",
                            "build", "coverage", ".cache", ".pytest_cache", ".mypy_cache",
                            ".next", "target", "vendor"})
REASONS = {
    "video": "Video asset can be accidental raw footage or contain private material.",
    "audio": "Audio asset can be accidental recording or contain private material.",
    "image": "Image asset may contain private data or unintended screenshots/metadata.",
    "media_container": "Media container cannot be resolved to audio/video from its header alone.",
    "document": "Document asset may contain private content, metadata, or active content.",
    "archive": "Archive/package contents are not inspected and may hide secrets or generated files.",
    "executable": "Executable or compiled artifact cannot be reviewed as source.",
    "database": "Database/backup can contain private records or credentials.",
    "dataset": "Binary dataset can contain private data and is not inspected for secrets.",
    "model": "Model/checkpoint can be large or contain serialized executable objects.",
    "serialized": "Serialized object may contain private data or execute code when loaded.",
    "font": "Font is a binary asset; confirm provenance, licensing, and necessity.",
    "notebook": "Notebook may retain cell outputs, embedded media, or credentials.",
    "log": "Log/trace can contain credentials, requests, or personal information.",
    "certificate": "Certificate/key material requires inspection for private signing material.",
    "unknown_binary": "Unrecognized binary content cannot be safely reviewed as text.",
    "unknown_text": "Unrecognized filename/type needs an explanation before inclusion.",
    "symlink": "Symlink target and intent require review; the target is not read.",
    "submodule": "Submodule contents are outside the parent repository scan.",
    "unreadable": "File type/content could not be inspected.",
    "special": "Nonregular filesystem object is not opened or scanned.",
}
ASSET_CATEGORIES = frozenset(REASONS)

# (format, category, signature, offset, compatible declared categories).
# Shared containers retain the declared subtype only when explicitly compatible.
SIGNATURES = (
    ("png", "image", b"\x89PNG\r\n\x1a\n", 0, ()),
    ("jpeg", "image", b"\xff\xd8\xff", 0, ()),
    ("gif87", "image", b"GIF87a", 0, ()),
    ("gif89", "image", b"GIF89a", 0, ()),
    ("tiff-le", "image", b"II\x2a\x00", 0, ()),
    ("tiff-be", "image", b"MM\x00\x2a", 0, ()),
    ("bmp", "image", b"BM", 0, ()),
    ("photoshop", "image", b"8BPS", 0, ()),
    ("openexr", "image", b"\x76\x2f\x31\x01", 0, ()),
    ("icon", "image", b"\x00\x00\x01\x00", 0, ()),
    ("jpeg-xl", "image", b"\xff\x0a", 0, ()),
    ("flac", "audio", b"fLaC", 0, ()),
    ("mp3-id3", "audio", b"ID3", 0, ()),
    ("midi", "audio", b"MThd", 0, ()),
    ("amr", "audio", b"#!AMR", 0, ()),
    ("au", "audio", b".snd", 0, ()),
    ("caf", "audio", b"caff", 0, ()),
    ("ogg", "media_container", b"OggS", 0, ("audio", "video")),
    ("ebml", "media_container", b"\x1a\x45\xdf\xa3", 0, ("audio", "video")),
    ("asf", "media_container", bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c"), 0, ("audio", "video")),
    ("flv", "video", b"FLV", 0, ()),
    ("mpeg-program", "video", b"\x00\x00\x01\xba", 0, ()),
    ("mpeg-sequence", "video", b"\x00\x00\x01\xb3", 0, ()),
    ("realmedia", "media_container", b".RMF", 0, ("audio", "video")),
    ("pdf", "document", b"%PDF-", 0, ()),
    ("postscript", "document", b"%!PS", 0, ("image",)),
    ("ole-compound", "document", bytes.fromhex("d0cf11e0a1b11ae1"), 0, ("document", "executable", "database")),
    ("zip", "archive", b"PK\x03\x04", 0, ("document", "dataset", "executable")),
    ("zip-empty", "archive", b"PK\x05\x06", 0, ("document", "dataset", "executable")),
    ("zip-spanned", "archive", b"PK\x07\x08", 0, ("document", "dataset", "executable")),
    ("gzip", "archive", b"\x1f\x8b", 0, ("image",)),
    ("bzip2", "archive", b"BZh", 0, ()),
    ("xz", "archive", b"\xfd7zXZ\x00", 0, ()),
    ("zstd", "archive", b"\x28\xb5\x2f\xfd", 0, ()),
    ("7zip", "archive", b"7z\xbc\xaf\x27\x1c", 0, ()),
    ("rar", "archive", b"Rar!\x1a\x07", 0, ()),
    ("tar", "archive", b"ustar", 257, ()),
    ("cab", "archive", b"MSCF", 0, ()),
    ("rpm", "archive", b"\xed\xab\xee\xdb", 0, ()),
    ("ar-package", "archive", b"!<arch>\n", 0, ("executable",)),
    ("elf", "executable", b"\x7fELF", 0, ()),
    ("dos-pe", "executable", b"MZ", 0, ()),
    ("macho-le", "executable", b"\xcf\xfa\xed\xfe", 0, ()),
    ("macho-be", "executable", b"\xfe\xed\xfa\xcf", 0, ()),
    ("macho32-le", "executable", b"\xce\xfa\xed\xfe", 0, ()),
    ("macho32-be", "executable", b"\xfe\xed\xfa\xce", 0, ()),
    ("java-or-fat-macho", "executable", b"\xca\xfe\xba\xbe", 0, ()),
    ("wasm", "executable", b"\x00asm", 0, ()),
    ("dex", "executable", b"dex\n", 0, ()),
    ("sqlite", "database", b"SQLite format 3\x00", 0, ()),
    ("numpy", "dataset", b"\x93NUMPY", 0, ()),
    ("parquet", "dataset", b"PAR1", 0, ()),
    ("hdf5", "dataset", b"\x89HDF\r\n\x1a\n", 0, ()),
    ("arrow", "dataset", b"ARROW1", 0, ()),
    ("netcdf", "dataset", b"CDF\x01", 0, ()),
    ("gguf", "model", b"GGUF", 0, ()),
    ("tflite", "model", b"TFL3", 4, ()),
    ("woff", "font", b"wOFF", 0, ()),
    ("woff2", "font", b"wOF2", 0, ()),
    ("otf", "font", b"OTTO", 0, ()),
    ("ttf", "font", b"\x00\x01\x00\x00", 0, ()),
)

# Only formats with unambiguous suffix equivalence get a within-category check;
# shared containers (ZIP, ISO media, TIFF/raw) deliberately stay out of this map.
FORMAT_SUFFIXES = {
    "png": {".png"}, "jpeg": {".jpg", ".jpeg", ".jpe"},
    "gif87": {".gif"}, "gif89": {".gif"}, "webp": {".webp"},
    "flac": {".flac"}, "wav": {".wav", ".wave"}, "avi": {".avi"},
    "pdf": {".pdf"}, "svg": {".svg"}, "sqlite": {".sqlite", ".sqlite3", ".db", ".db3"},
    "woff": {".woff"}, "woff2": {".woff2"}, "otf": {".otf"}, "ttf": {".ttf"},
}


def text_content(head):
    """Recognize common Unicode text without treating NUL-containing binary as text."""
    encodings = ((b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
                 (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"))
    encoding = next((enc for prefix, enc in encodings if head.startswith(prefix)), "utf-8-sig")
    try:
        # A prefix may stop mid-codepoint; an incremental decoder handles this
        # without turning an otherwise valid UTF-8 file into an unknown binary.
        import codecs
        text = codecs.getincrementaldecoder(encoding)().decode(head, final=False)
    except (UnicodeError, TypeError):
        return None
    if any(ord(c) < 32 and c not in "\t\r\n\f" for c in text):
        return None
    return text


def signature(head, declared):
    for name, category, prefix, offset, compatible in SIGNATURES:
        if head[offset:offset + len(prefix)] == prefix:
            return name, declared if declared in compatible else category, compatible
    if len(head) >= 12 and head[:4] == b"RIFF":
        kind = {b"WAVE": ("wav", "audio"), b"AVI ": ("avi", "video"),
                b"WEBP": ("webp", "image")}.get(head[8:12])
        if kind:
            return *kind, ()
    if head[:4] == b"FORM" and head[8:12] in {b"AIFF", b"AIFC"}:
        return "aiff", "audio", ()
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12].lower()
        if brand in {b"avif", b"avis", b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
            return "iso-image", "image", ()
        if brand in {b"m4a ", b"m4b ", b"f4a ", b"f4b "}:
            return "iso-audio", "audio", ()
        return "iso-media", declared if declared in {"audio", "video"} else "media_container", ("audio", "video")
    if len(head) > 376 and head[0] == head[188] == head[376] == 0x47:
        return "mpeg-transport", "video", ()
    if len(head) >= 2 and head[0] == 0xff and (head[1] & 0xfe) in {0xfa, 0xf2}:
        return "mpeg-audio-frame", "audio", ()
    if len(head) >= 2 and head[0] == 0xff and (head[1] & 0xf6) == 0xf0:
        return "aac-adts", "audio", ()
    if len(head) >= 2 and head[0] == 0x80 and head[1] in {2, 3, 4, 5}:
        return "pickle", "serialized", ("model", "dataset")
    text = text_content(head)
    if text is not None:
        start = text.lstrip()
        if re.match(r"(?:<\?xml[^>]*>\s*)?(?:<!--.*?-->\s*)*<svg(?:\s|>)", start, re.S | re.I):
            return "svg", "image", ()
        if start.startswith("{\\rtf"):
            return "rtf", "document", ()
        if start.startswith("#!"):
            return "script", "source" if declared == "source" else "executable", ("source",)
    return None


def classify(path, source, head, size, mode, added, coverage):
    p = PurePosixPath(path)
    name = p.name.lower()
    suffix = p.suffix.lower()
    declared = SUFFIX_CATEGORY.get(suffix)
    if declared is None and name.startswith("."):
        declared = SUFFIX_CATEGORY.get(name)
    if declared is None and suffix in {".example", ".sample", ".template", ".dist"}:
        base = name[:-len(suffix)]
        declared = SUFFIX_CATEGORY.get(PurePosixPath(base).suffix.lower()) or SUFFIX_CATEGORY.get(base)
    if name in PLAIN_NAMES or name.startswith(("dockerfile.", "makefile.")):
        declared = "source" if "file" in name else "text"
    detected = signature(head, declared) if head is not None and mode not in {"120000", "160000", "special"} else None
    category = (detected[1] if detected else declared)
    if mode in {"120000", "160000", "special"}:
        category = {"120000": "symlink", "160000": "submodule", "special": "special"}[mode]
    elif head is None:
        category = "unreadable"
    elif category is None:
        category = "unknown_text" if text_content(head) is not None else "unknown_binary"
    elif not detected and text_content(head) is None and category in {"source", "text"}:
        category = "unknown_binary"
    warnings = []

    def warn(code, reason, action):
        warnings.append({"severity": "review", "code": code, "reason": reason, "action": action})

    if category in ASSET_CATEGORIES:
        warn("file-type-review", REASONS[category],
             "Confirm this file belongs in the commit; review its contents/provenance and privacy, or keep it out of staging. Do not execute or deserialize it for inspection.")
    mismatch = detected and declared and detected[1] != declared and declared not in detected[2]
    if detected and detected[0] in FORMAT_SUFFIXES and declared == detected[1] and suffix:
        mismatch = mismatch or suffix not in FORMAT_SUFFIXES[detected[0]]
    if mismatch:
        warn("file-extension-mismatch", "Content signature disagrees with the declared file category.",
             "Inspect the real format and explain or correct the misleading extension.")
    if category == "unknown_binary" and declared in {"source", "text"}:
        warn("binary-disguised-as-text", "A source/text filename contains non-text bytes.",
             "Inspect the actual format; do not accept this as reviewed source code.")
    if size is not None and size > LARGE_FILE_BYTES:
        warn("large-file-review", "File exceeds the 5 MiB review threshold.",
             "Confirm size is intentional; consider external asset storage or the repository's LFS policy.")
    if any(part.lower() in GENERATED_PARTS for part in p.parts) or name.endswith((".min.js", ".min.css", ".map", "~", ".swp", ".tmp")) or name in {".ds_store", "thumbs.db"}:
        warn("generated-file-review", "Filename suggests generated, vendored, cached, or temporary content.",
             "Confirm repository policy requires this artifact; otherwise keep it out of staging and update ignore rules.")
    if mode == "100755":
        warn("executable-mode-review", "File is marked executable.",
             "Confirm this permission is needed and inspect what would run.")
    if any(unicodedata.category(c) in {"Cc", "Cf"} for c in path) or any(part.startswith("-") or part.endswith((" ", ".")) for part in p.parts):
        warn("unusual-filename-review", "Path contains control/format characters or misleading/shell-sensitive components.",
             "Review the JSON-escaped path; rename if accidental and use shell quoting plus -- when staging.")
    if any(re.match(r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", part, re.I)
           or any(c in part for c in '<>:"|?*') for part in p.parts):
        warn("nonportable-filename-review", "Path contains a reserved name or characters unsupported on common filesystems.",
             "Confirm cross-platform compatibility or choose a portable filename.")
    if head is not None and size and len(head) < min(size, HEADER_BYTES):
        warn("short-read-review", "The available header is shorter than expected for this file size.",
             "Rerun after resolving concurrent edits or read failures.")
    return {"path": path, "source": source, "added": added, "size_bytes": size,
            "mode": mode, "extension": suffix, "declared_category": declared,
            "category": category, "detected_format": detected[0] if detected else None,
            "basis": "signature" if detected else "extension" if declared and head is not None else "fallback",
            "inspection": {"bytes_inspected": min(len(head), HEADER_BYTES) if head is not None else 0,
                           "coverage": coverage, "embedded_contents_scanned": False},
            "warnings": warnings}
