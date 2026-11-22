"""Offline checks for the files in the frozen public review snapshot."""

import hashlib
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "xuchuan_desktop.pyw"
loader = importlib.machinery.SourceFileLoader("xuchuan_frozen", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
application = importlib.util.module_from_spec(spec)
loader.exec_module(application)


class PublicSnapshotTests(unittest.TestCase):
    def test_checksums_and_candidate_metadata(self):
        for line in (ROOT / "RELEASE_FILES.sha256").read_text(encoding="utf-8").splitlines():
            expected, filename = line.split("  ", 1)
            with self.subTest(file=filename):
                self.assertEqual(hashlib.sha256((ROOT / filename).read_bytes()).hexdigest(), expected)
        valid, status = application.release_integrity()
        self.assertTrue(valid, status)
        self.assertIn("候选包", status)

    def test_shipped_examples_match_format_card(self):
        self.assertEqual(application.format_folder_conflicts(ROOT), {})

    def test_complete_single_note(self):
        body, accepted, failures = application.parse_reply_outputs(
            "<续川笔记>一条合成测试笔记</续川笔记>", "stop"
        )
        self.assertEqual(body, "")
        self.assertEqual(failures, [])
        self.assertEqual([(kind, content) for kind, content, _ in accepted],
                         [("笔记", "一条合成测试笔记")])
