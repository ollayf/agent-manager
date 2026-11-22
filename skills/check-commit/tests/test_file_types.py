"""Census the whole format catalog plus adversarial classification cases."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import file_types as types


def inspect(path, head, size=None, mode="100644"):
    return types.classify(path, "index", head, len(head) if size is None and head is not None else size,
                          mode, True, "full-file-read")


class TypeTests(unittest.TestCase):
    def test_catalog_is_nonempty_and_signature_names_are_unique(self):
        self.assertGreater(len(types.SIGNATURES), 50)
        self.assertEqual(len(types.SIGNATURES), len({rule[0] for rule in types.SIGNATURES}))
        self.assertGreater(len(types.SUFFIX_CATEGORY), 200)

    def test_every_signature_is_detected_even_with_a_text_extension(self):
        for name, category, prefix, offset, compatible in types.SIGNATURES:
            with self.subTest(format=name):
                header = b"\x00" * offset + prefix + b"\x00" * 16
                record = inspect("disguised.txt", header)
                self.assertEqual(record["detected_format"], name)
                self.assertEqual(record["category"], category)
                self.assertIn("file-extension-mismatch", {w["code"] for w in record["warnings"]})

    def test_every_extension_is_classified_and_assets_always_warn(self):
        for suffix, category in types.SUFFIX_CATEGORY.items():
            with self.subTest(suffix=suffix):
                record = inspect("asset" + suffix, b"ordinary content\n")
                self.assertEqual(record["declared_category"], category)
                self.assertEqual(record["category"], category)
                codes = {w["code"] for w in record["warnings"]}
                self.assertEqual("file-type-review" in codes, category in types.ASSET_CATEGORIES)

    def test_compound_extensions_and_uppercase_are_classified(self):
        for path, category in [("CLIP.MP4", "video"), ("recording.WAV", "audio"),
                               ("assets.tar.gz", "archive"), ("config.yaml.example", "source"),
                               (".env.example", "source"), (".gitignore", "text")]:
            with self.subTest(path=path):
                self.assertEqual(inspect(path, b"content\n")["category"], category)

    def test_riff_forms_are_distinguished(self):
        for tag, category in [(b"WAVE", "audio"), (b"AVI ", "video"), (b"WEBP", "image")]:
            with self.subTest(tag=tag):
                self.assertEqual(inspect("hidden.txt", b"RIFF\x00\x00\x00\x00" + tag)["category"], category)

    def test_iso_media_brands_distinguish_images_audio_and_containers(self):
        for brand, category in [(b"avif", "image"), (b"heic", "image"),
                                (b"M4A ", "audio"), (b"isom", "media_container")]:
            with self.subTest(brand=brand):
                self.assertEqual(inspect("hidden.txt", b"\x00\x00\x00\x18ftyp" + brand)["category"], category)
        self.assertEqual(inspect("clip.mp4", b"\x00\x00\x00\x18ftypisom")["category"], "video")

    def test_shared_containers_keep_compatible_declared_category(self):
        for path, header, category in [("sound.ogg", b"OggS", "audio"),
                                       ("clip.ogv", b"OggS", "video"),
                                       ("talk.webm", b"\x1a\x45\xdf\xa3", "video"),
                                       ("report.docx", b"PK\x03\x04", "document"),
                                       ("data.npz", b"PK\x03\x04", "dataset")]:
            with self.subTest(path=path):
                record = inspect(path, header)
                self.assertEqual(record["category"], category)
                self.assertNotIn("file-extension-mismatch", {w["code"] for w in record["warnings"]})
                self.assertFalse(record["inspection"]["embedded_contents_scanned"])

    def test_within_category_extension_mismatches_are_not_hidden(self):
        for path, header in [("picture.jpg", b"\x89PNG\r\n\x1a\n"),
                             ("song.wav", b"fLaC"), ("typeface.woff", b"wOF2")]:
            with self.subTest(path=path):
                self.assertIn("file-extension-mismatch", {w["code"] for w in inspect(path, header)["warnings"]})

    def test_nonportable_names_are_flagged(self):
        for path in ["NUL.txt", "assets/COM1.mp4", "clip:video.mp4"]:
            with self.subTest(path=path):
                self.assertIn("nonportable-filename-review", {w["code"] for w in inspect(path, b"text")["warnings"]})

    def test_svg_and_rtf_are_recognized_in_text_content(self):
        for header, category in [(b'<svg xmlns="example"></svg>', "image"),
                                 (b'<?xml version="1.0"?><!-- comment --><svg />', "image"),
                                 (b'{\\rtf1 hello}', "document")]:
            with self.subTest(category=category):
                self.assertEqual(inspect("hidden.txt", header)["category"], category)

    def test_scripts_hidden_as_text_warn_without_executing(self):
        head = b"#!/bin/sh\nexit 0\n"
        self.assertEqual(inspect("script.txt", head)["category"], "executable")
        self.assertEqual(inspect("script.sh", head)["category"], "source")

    def test_additional_audio_and_video_headers_are_recognized(self):
        transport = b"G" + b"\0" * 187 + b"G" + b"\0" * 187 + b"G"
        for head, category in [(b"FORM\0\0\0\0AIFF", "audio"), (b"\xff\xfb123", "audio"),
                               (b"\xff\xf1123", "audio"), (b"\x80\x05abc", "serialized"),
                               (transport, "video")]:
            with self.subTest(header=head[:4]):
                self.assertEqual(inspect("hidden.txt", head)["category"], category)

    def test_unknown_formats_are_visible_and_require_review(self):
        for path, head, category in [("asset.mystery", b"plain text", "unknown_text"),
                                     ("asset.mystery", b"\x00\x88\x99", "unknown_binary"),
                                     ("README", b"read me\n", "text"),
                                     ("Dockerfile", b"FROM scratch\n", "source"),
                                     ("extensionless", b"text", "unknown_text")]:
            with self.subTest(path=path):
                record = inspect(path, head)
                self.assertEqual(record["category"], category)
                self.assertEqual(bool(record["warnings"]), category.startswith("unknown"))

    def test_binary_disguised_as_source_warns(self):
        record = inspect("hello.py", b"\x00\x88\x99")
        self.assertEqual(record["category"], "unknown_binary")
        self.assertIn("binary-disguised-as-text", {w["code"] for w in record["warnings"]})

    def test_multibyte_text_prefix_and_unicode_boms_are_handled(self):
        for head in [b"plain\xe2\x82", "hello\n".encode("utf-16"), "hello\n".encode("utf-32")]:
            with self.subTest(header=head):
                self.assertEqual(inspect("hello.txt", head)["category"], "text")

    def test_size_threshold_boundaries_and_empty_files(self):
        self.assertEqual(inspect("empty.py", b"")["warnings"], [])
        for size, warned in [(types.LARGE_FILE_BYTES, False), (types.LARGE_FILE_BYTES + 1, True)]:
            with self.subTest(size=size):
                codes = {w["code"] for w in inspect("data.txt", b"a" * types.HEADER_BYTES, size)["warnings"]}
                self.assertEqual("large-file-review" in codes, warned)

    def test_permission_and_generated_path_warnings_are_independent(self):
        record = inspect("dist/script.py", b"pass\n", mode="100755")
        self.assertEqual({w["code"] for w in record["warnings"]},
                         {"executable-mode-review", "generated-file-review"})

    def test_control_bidi_and_shell_sensitive_paths_warn(self):
        for path in ["-asset.py", "line\nbreak.py", "src/\u202eexe.py", "file .py/odd."]:
            with self.subTest(path=path):
                self.assertIn("unusual-filename-review", {w["code"] for w in inspect(path, b"text")["warnings"]})

    def test_skipped_object_types_have_explicit_categories_and_warnings(self):
        for mode, category in [("120000", "symlink"), ("160000", "submodule"),
                               ("special", "special"), ("unknown", "unreadable")]:
            with self.subTest(mode=mode):
                record = inspect("asset", None, mode=mode)
                self.assertEqual(record["category"], category)
                self.assertTrue(record["warnings"])

    def test_headers_and_secrets_never_appear_in_structured_output(self):
        import json
        secret = b"a-confidential-payload-that-must-not-be-reported"
        record = inspect("video.mp4", b"\0\0\0\x18ftypisom" + secret)
        self.assertNotIn(secret.decode(), json.dumps(record))
        self.assertTrue(all({"severity", "code", "reason", "action"} <= set(w) for w in record["warnings"]))

    def test_every_signature_and_asset_category_has_a_review_reason(self):
        self.assertTrue(types.REASONS)
        self.assertTrue({rule[1] for rule in types.SIGNATURES} <= set(types.REASONS))
        self.assertTrue(set(types.EXTENSIONS) - {"source", "text"} <= set(types.REASONS))


if __name__ == "__main__":
    unittest.main()
