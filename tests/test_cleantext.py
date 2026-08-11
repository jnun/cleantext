#!/usr/bin/env python3
"""Unit tests for cleantext watermark stripping."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cleantext as ct  # noqa: E402


class ScanTests(unittest.TestCase):
    def test_clean_text_is_clean(self):
        report = ct.scan_text("Hello world.\nPlain ASCII only.\n")
        self.assertTrue(report.is_clean())
        self.assertEqual(report.risk_score, 0)

    def test_detects_zero_width(self):
        dirty = "Hello\u200bWorld"
        report = ct.scan_text(dirty)
        self.assertFalse(report.is_clean())
        kinds = {f.kind for f in report.findings}
        self.assertIn("invisible/zero-width", kinds)

    def test_detects_homoglyphs(self):
        # Cyrillic а and о
        dirty = "p\u0430yrol\u043ead"
        report = ct.scan_text(dirty)
        kinds = {f.kind for f in report.findings}
        self.assertIn("homoglyphs", kinds)

    def test_detects_space_variants(self):
        dirty = "a\u2004b\u3000c"
        report = ct.scan_text(dirty)
        kinds = {f.kind for f in report.findings}
        self.assertIn("alternate spaces", kinds)


class CleanTests(unittest.TestCase):
    def test_strips_zero_width_payload(self):
        base = "The quick brown fox jumps over the lazy dog."
        dirty = ct.inject_zero_width_payload(base)
        self.assertNotEqual(dirty, base)
        cleaned, stats = ct.clean_text(dirty)
        self.assertEqual(cleaned.strip(), base)
        self.assertGreater(stats.removed_invisible, 0)
        self.assertTrue(ct.scan_text(cleaned).is_clean())

    def test_normalizes_homoglyphs(self):
        dirty = ct.inject_homoglyphs("Pack my box with five dozen liquor jugs.")
        cleaned, stats = ct.clean_text(dirty)
        self.assertGreater(stats.normalized_homoglyphs, 0)
        self.assertNotIn("\u0430", cleaned)
        self.assertNotIn("\u043e", cleaned)
        self.assertIn("box", cleaned)
        self.assertTrue(ct.scan_text(cleaned).is_clean())

    def test_normalizes_space_variants(self):
        dirty = ct.inject_space_variants("one two three four five six")
        self.assertIn("\u2004", dirty)
        cleaned, stats = ct.clean_text(dirty)
        self.assertGreater(stats.normalized_spaces, 0)
        self.assertNotIn("\u2004", cleaned)
        self.assertEqual(cleaned, "one two three four five six")

    def test_strips_trailing_snow(self):
        dirty = ct.inject_trailing_snow("hello world\n")
        self.assertTrue(dirty.rstrip("\n").endswith((" ", "\t")))
        cleaned, stats = ct.clean_text(dirty)
        self.assertGreater(stats.stripped_trailing_ws, 0)
        self.assertEqual(cleaned, "hello world\n")

    def test_variation_selectors_and_tags(self):
        dirty = "text\ufe0e\U000e0061more"
        cleaned, stats = ct.clean_text(dirty)
        self.assertGreater(stats.removed_vs, 0)
        self.assertGreater(stats.removed_tags, 0)
        self.assertEqual(cleaned, "textmore")

    def test_special_apostrophes(self):
        # Claude Code-style marker apostrophes
        dirty = "Today\u2019s date\u02bc and\u02b9 mark"
        cleaned, _ = ct.clean_text(dirty)
        self.assertEqual(cleaned, "Today's date' and' mark")

    def test_preserves_meaningful_newlines_and_tabs(self):
        text = "col1\tcol2\nline2\n"
        cleaned, _ = ct.clean_text(text)
        self.assertEqual(cleaned, text)

    def test_combined_attack(self):
        base = (
            "The quick brown fox jumps over the lazy dog.\n"
            "Pack my box with five dozen liquor jugs.\n"
        )
        dirty = ct.inject_trailing_snow(
            ct.inject_space_variants(
                ct.inject_homoglyphs(ct.inject_zero_width_payload(base))
            )
        )
        before = ct.scan_text(dirty)
        self.assertGreater(before.risk_score, 0)
        cleaned, _ = ct.clean_text(dirty)
        after = ct.scan_text(cleaned)
        self.assertTrue(after.is_clean(), msg=ct.format_report(after))
        self.assertIn("quick brown fox", cleaned.lower())
        self.assertIn("liquor jugs", cleaned.lower())

    def test_no_homoglyphs_flag(self):
        dirty = "caf\u0430"  # Cyrillic a
        cleaned, stats = ct.clean_text(dirty, normalize_homoglyphs=False)
        self.assertEqual(stats.normalized_homoglyphs, 0)
        self.assertIn("\u0430", cleaned)

    def test_bidi_override_removed(self):
        # RLO can reverse display order — classic attack vector
        dirty = "safe\u202ewarning"
        cleaned, stats = ct.clean_text(dirty)
        self.assertGreater(stats.removed_invisible, 0)
        self.assertEqual(cleaned, "safewarning")


class CLITests(unittest.TestCase):
    def test_self_test_exit_zero(self):
        code = ct.main(["--self-test"])
        self.assertEqual(code, 0)

    def test_scan_exit_codes(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            clean_path = Path(td) / "clean.txt"
            dirty_path = Path(td) / "dirty.txt"
            clean_path.write_text("hello\n", encoding="utf-8")
            dirty_path.write_text("hel\u200blo\n", encoding="utf-8")
            self.assertEqual(ct.main([str(clean_path), "--scan"]), 0)
            self.assertEqual(ct.main([str(dirty_path), "--scan"]), 1)

    def test_in_place_clean(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "f.txt"
            # ZWSP between a|b is removed (not replaced); three-per-em becomes space
            path.write_text("a\u200bb\u2004c\n", encoding="utf-8")
            self.assertEqual(ct.main([str(path), "--in-place"]), 0)
            self.assertEqual(path.read_text(encoding="utf-8"), "ab c\n")


if __name__ == "__main__":
    unittest.main()
