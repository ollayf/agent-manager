#!/usr/bin/env python3
"""Send text and local files to the owner's private Telegram chat."""

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ACCOUNT = "telegram-me"
TOKEN_SERVICE = "telegram-me-bot-token"
CHAT_SERVICE = "telegram-me-chat-id"
MAX_UPLOAD_BYTES = 50_000_000
MAX_TEXT_CHARS = 3900
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class SendError(Exception):
    pass


ENV_NAMES = {TOKEN_SERVICE: "TELEGRAM_ME_BOT_TOKEN", CHAT_SERVICE: "TELEGRAM_ME_CHAT_ID"}


def secret(service):
    """Environment first (any OS), then macOS Keychain."""
    env_name = ENV_NAMES.get(service)
    value = os.environ.get(env_name, "").strip() if env_name else ""
    if value:
        return value
    if not shutil.which("security"):
        raise SendError(f"Set {env_name} (no macOS Keychain on this system)")
    result = subprocess.run(
        ["security", "find-generic-password", "-a", ACCOUNT, "-s", service, "-w"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise SendError(f"Set {env_name} or add Keychain item: {service}")
    value = result.stdout.strip()
    if not value:
        raise SendError(f"Empty Keychain item: {service}")
    return value


def api_call(token, method, fields, file=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    if file is None:
        body = urllib.parse.urlencode(fields).encode("utf-8")
        content_type = "application/x-www-form-urlencoded"
    else:
        boundary = uuid.uuid4().hex
        parts = []
        for key, value in fields.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8")
            )
        field_name = {"sendAudio": "audio", "sendVideo": "video", "sendVoice": "voice", "sendPhoto": "photo", "sendAnimation": "animation", "sendDocument": "document"}[method]
        mime_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        safe_name = file.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"; filename=\"{safe_name}\"\r\nContent-Type: {mime_type}\r\n\r\n".encode("utf-8")
        )
        parts.append(file.read_bytes())
        parts.append(f"\r\n--{boundary}--\r\n".encode("ascii"))
        body = b"".join(parts)
        content_type = f"multipart/form-data; boundary={boundary}"
    request = urllib.request.Request(url, data=body, headers={"Content-Type": content_type}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            result = json.load(error)
        except (ValueError, OSError):
            raise SendError(f"Telegram returned HTTP {error.code}") from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise SendError(f"Network error ({type(error).__name__}); delivery status is uncertain") from None
    if not result.get("ok"):
        raise SendError(f"Telegram rejected {method}: {result.get('description', 'unknown error')}")
    return result["result"]


def text_chunks(value):
    while value:
        if len(value) <= MAX_TEXT_CHARS:
            yield value
            break
        cut = value.rfind("\n", 0, MAX_TEXT_CHARS + 1)
        if cut < MAX_TEXT_CHARS // 2:
            cut = MAX_TEXT_CHARS
        yield value[:cut]
        value = value[cut:]


def method_for_file(path):
    extension = path.suffix.lower()
    if extension in {".mp3", ".m4a"}:
        return "sendAudio"
    if extension == ".mp4":
        return "sendVideo"
    if extension in PHOTO_EXTENSIONS and path.stat().st_size <= 10_000_000:
        return "sendPhoto"
    return "sendDocument"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    send = subparsers.add_parser("send", help="Send text or local files to the configured chat")
    source = send.add_mutually_exclusive_group()
    source.add_argument("--text", help="Text to send")
    source.add_argument("--text-file", type=Path, help="Read text from a UTF-8 file")
    source.add_argument("--stdin", action="store_true", help="Read text from standard input")
    send.add_argument("--file", action="append", type=Path, default=[], help="Local file to send; repeatable")
    send.add_argument("--as", dest="as_type", choices=["audio", "video", "voice", "photo", "document", "animation"], help="Telegram presentation for one file")
    send.add_argument("--dry-run", action="store_true", help="Validate content and show planned methods without sending")
    args = parser.parse_args()

    if args.as_type and len(args.file) != 1:
        raise SendError("--as requires exactly one --file")
    if args.text_file:
        message = args.text_file.expanduser().read_text(encoding="utf-8")
    elif args.stdin:
        message = sys.stdin.read()
    else:
        message = args.text or ""
    files = [path.expanduser().resolve() for path in args.file]
    if not message and not files:
        raise SendError("Provide text or at least one file")
    for path in files:
        if not path.is_file():
            raise SendError(f"File does not exist: {path}")
        size = path.stat().st_size
        if size == 0:
            raise SendError(f"File is empty: {path}")
        if size > MAX_UPLOAD_BYTES:
            raise SendError(f"File exceeds Telegram's 50 MB Bot API upload limit: {path}")
    methods = ["send" + args.as_type.capitalize() if args.as_type else method_for_file(path) for path in files]
    if args.dry_run:
        print(json.dumps({"text_parts": sum(1 for _ in text_chunks(message)), "files": [{"name": path.name, "method": method, "bytes": path.stat().st_size} for path, method in zip(files, methods)]}))
        return

    token = secret(TOKEN_SERVICE)
    chat_id = secret(CHAT_SERVICE)
    for index, chunk in enumerate(text_chunks(message), 1):
        result = api_call(token, "sendMessage", {"chat_id": chat_id, "text": chunk})
        print(f"Text part {index} accepted (message {result['message_id']})")
    for path, method in zip(files, methods):
        try:
            result = api_call(token, method, {"chat_id": chat_id}, path)
        except SendError as error:
            if method == "sendDocument" or "Telegram rejected" not in str(error):
                raise
            print(f"{path.name}: {method} rejected; trying as document", file=sys.stderr)
            result = api_call(token, "sendDocument", {"chat_id": chat_id}, path)
            method = "sendDocument"
        print(f"{path.name} accepted as {method} (message {result['message_id']})")


if __name__ == "__main__":
    try:
        main()
    except (SendError, OSError, UnicodeError) as error:
        print(f"telegram-me: {error}", file=sys.stderr)
        sys.exit(1)
