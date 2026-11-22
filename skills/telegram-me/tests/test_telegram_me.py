import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "telegram_me.py"
SPEC = importlib.util.spec_from_file_location("telegram_me", SCRIPT)
telegram_me = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(telegram_me)


class TelegramMeTests(unittest.TestCase):
    def test_long_text_is_preserved_and_stays_below_limit(self):
        message = ("hello\n" * 1500) + "end"
        chunks = list(telegram_me.text_chunks(message))
        self.assertEqual("".join(chunks), message)
        self.assertTrue(all(0 < len(chunk) <= 3900 for chunk in chunks))
        self.assertGreater(len(chunks), 1)

    def test_binary_multipart_upload_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bin"
            payload = b"\x00\xff\r\n--not-the-boundary\x00"
            path.write_bytes(payload)
            accepted = io.BytesIO(json.dumps({"ok": True, "result": {"message_id": 7}}).encode())
            with mock.patch.object(telegram_me.urllib.request, "urlopen", return_value=accepted) as send:
                result = telegram_me.api_call("test-token", "sendDocument", {"chat_id": "12345"}, path)
            request = send.call_args.args[0]
            self.assertEqual(result["message_id"], 7)
            self.assertTrue(request.full_url.endswith("/sendDocument"))
            self.assertIn(b'name="chat_id"\r\n\r\n12345', request.data)
            self.assertIn(b'name="document"; filename="sample.bin"', request.data)
            self.assertIn(payload, request.data)

    def test_file_routing_includes_generic_document_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("clip.mp3", "clip.mp4", "report.pdf", "other.bin")]
            for path in paths:
                path.write_bytes(b"data")
            self.assertEqual([telegram_me.method_for_file(path) for path in paths],
                             ["sendAudio", "sendVideo", "sendDocument", "sendDocument"])

    def test_uncertain_network_result_does_not_retry_as_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp3"
            path.write_bytes(b"data")
            with mock.patch.object(sys, "argv", [str(SCRIPT), "send", "--file", str(path)]), \
                 mock.patch.object(telegram_me, "secret", side_effect=["test-token", "12345"]), \
                 mock.patch.object(telegram_me, "api_call", side_effect=telegram_me.SendError("Network error; delivery status is uncertain")) as send, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(telegram_me.SendError):
                    telegram_me.main()
            self.assertEqual(send.call_count, 1)

    def test_rejected_media_is_resent_as_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp3"
            path.write_bytes(b"data")
            with mock.patch.object(sys, "argv", [str(SCRIPT), "send", "--file", str(path)]), \
                 mock.patch.object(telegram_me, "secret", side_effect=["test-token", "12345"]), \
                 mock.patch.object(telegram_me, "api_call", side_effect=[telegram_me.SendError("Telegram rejected sendAudio: unsupported format"), {"message_id": 8}]) as send, \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                telegram_me.main()
            self.assertEqual([call.args[1] for call in send.call_args_list],
                             ["sendAudio", "sendDocument"])

    def test_oversize_file_is_rejected_before_credentials_are_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.bin"
            with path.open("wb") as file:
                file.truncate(50_000_001)
            with mock.patch.object(sys, "argv", [str(SCRIPT), "send", "--file", str(path)]), \
                 mock.patch.object(telegram_me, "secret") as secret:
                with self.assertRaisesRegex(telegram_me.SendError, "50 MB"):
                    telegram_me.main()
            secret.assert_not_called()

    def test_environment_credentials_win_without_keychain(self):
        env = {"TELEGRAM_ME_BOT_TOKEN": "env-token", "TELEGRAM_ME_CHAT_ID": "999"}
        with mock.patch.dict(telegram_me.os.environ, env), \
             mock.patch.object(telegram_me.subprocess, "run") as run:
            self.assertEqual(telegram_me.secret(telegram_me.TOKEN_SERVICE), "env-token")
            self.assertEqual(telegram_me.secret(telegram_me.CHAT_SERVICE), "999")
        run.assert_not_called()

    def test_missing_credentials_name_the_variable_off_macos(self):
        with mock.patch.dict(telegram_me.os.environ, {}, clear=True), \
             mock.patch.object(telegram_me.shutil, "which", return_value=None):
            with self.assertRaisesRegex(telegram_me.SendError, "TELEGRAM_ME_BOT_TOKEN"):
                telegram_me.secret(telegram_me.TOKEN_SERVICE)


if __name__ == "__main__":
    unittest.main()
