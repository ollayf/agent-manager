---
name: telegram-me
description: Send information to the user's own Telegram chat through the configured bot. Use when the user asks to Telegram, message, or send them text, audio, video, PDFs, or other files through Telegram.
---

# Telegram me

Send content only when the user requests delivery to their Telegram chat. Use the bundled script; its destination is fixed to the user's private chat. Credentials come from `TELEGRAM_ME_BOT_TOKEN` / `TELEGRAM_ME_CHAT_ID` in the environment, or else macOS Keychain (`telegram-me-bot-token` / `telegram-me-chat-id`, account `telegram-me`). Never paste the bot token or chat ID into a command, skill file, message, log, or repository.

```bash
python3 <this skill's directory>/scripts/telegram_me.py send --text 'Your message'
python3 <this skill's directory>/scripts/telegram_me.py send --text-file /path/to/message.txt
python3 <this skill's directory>/scripts/telegram_me.py send --file /path/to/report.pdf
python3 <this skill's directory>/scripts/telegram_me.py send --text 'Here are the files' --file /path/to/audio.mp3 --file /path/to/video.mp4 --file /path/to/data.bin
```

The script accepts repeated `--file` arguments, `--stdin` for piped text, and `--dry-run` to inspect what it would send. It sends long text in chunks. MP3/M4A and MP4 are sent as playable media, common images as photos, and every other file type as a document. Use `--as audio|video|voice|photo|document|animation` with a single file when the user wants a specific Telegram presentation; a failed specialized send falls back to a document. Telegram's hosted Bot API currently limits new file uploads to 50 MB; report that limit if a file exceeds it. Do not silently omit content or retry an uncertain send, which could duplicate it.

When a task creates a file for delivery, finish and verify that file before sending it. Report which items were accepted by Telegram and any failures. Do not include the credential values in the report.
