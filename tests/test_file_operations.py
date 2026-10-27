"""Operações em arquivos confinadas ao workspace e com aprovação."""
import tempfile
import unittest
import hashlib
from pathlib import Path
from unittest.mock import patch

from jarvis.tools import Toolkit, TOOL_SPECS


class FilesOperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "work"
        self.root.mkdir()
        self.allowed = Toolkit(self.root, approve=lambda _: True)
        self.denied = Toolkit(self.root, approve=lambda _: False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_directory_and_denial(self):
        self.assertEqual(self.denied.execute("make_directory", {"path":"novo"})["result"]["status"],"rejected")
        result=self.allowed.execute("make_directory", {"path":"novo/projeto"})
        self.assertEqual(result["result"]["status"],"created")
        self.assertTrue((self.root/"novo/projeto").is_dir())

    def test_move_directory_and_refuse_overwrite(self):
        (self.root/"origem").mkdir()
        moved=self.allowed.execute("move_path", {"source":"origem","destination":"destino"})
        self.assertEqual(moved["result"]["status"],"moved")
        self.assertTrue((self.root/"destino").is_dir())
        (self.root/"outro").mkdir()
        self.assertIn("error",self.allowed.execute("move_path", {"source":"outro","destination":"destino"}))

    def test_recoverable_delete_only_moves(self):
        folder=self.root/"temporario"
        folder.mkdir()
        (folder/"nota.txt").write_text("salvo",encoding="utf8")
        denial=self.denied.execute("delete_path", {"path":"temporario"})
        self.assertEqual(denial["result"]["status"],"rejected")
        result=self.allowed.execute("delete_path", {"path":"temporario"})
        self.assertEqual(result["result"]["status"],"trashed")
        self.assertFalse(folder.exists())
        stored=Path(result["result"]["trash_path"])
        self.assertEqual((stored/"nota.txt").read_text(encoding="utf8"),"salvo")

    def test_cannot_escape_or_delete_workspace(self):
        (self.root/"safe").mkdir()
        for name, args in [
            ("make_directory",{"path":"../other"}),
            ("move_path",{"source":"safe","destination":"../bad"}),
            ("delete_path",{"path":"."}),
            ("delete_path",{"path":"../outside"}),
        ]:
            with self.subTest(name=name):
                self.assertIn("error",self.allowed.execute(name,args))
        self.assertTrue((self.root/"safe").is_dir())

    def test_reject_move_into_own_child(self):
        (self.root/"dir").mkdir()
        self.assertIn("error", self.allowed.execute("move_path",{"source":"dir","destination":"dir/nested"}))

    def test_specs_registered(self):
        names={item["name"] for item in TOOL_SPECS}
        self.assertTrue({"make_directory","move_path","delete_path"} <= names)

    def test_write_shows_diff_and_rejects_stale_content(self):
        target = self.root / "note.txt"
        target.write_text("original\n", encoding="utf-8")
        prompts = []
        kit = Toolkit(self.root, approve=lambda message: prompts.append(message) or True)
        stale = kit.execute("write_file", {"path": "note.txt", "content": "novo\n",
                                           "expected_sha256": "0" * 64})
        self.assertIn("error", stale)
        self.assertFalse(prompts)
        digest = hashlib.sha256(b"original\n").hexdigest()
        written = kit.execute("write_file", {"path": "note.txt", "content": "novo\n",
                                             "expected_sha256": digest})
        self.assertEqual(written["result"]["status"], "written")
        self.assertIn("-original", prompts[0])
        self.assertIn("+novo", prompts[0])
        self.assertEqual(target.read_text(encoding="utf-8"), "novo\n")
        self.assertEqual(written["result"]["sha256"], hashlib.sha256(b"novo\n").hexdigest())

    def test_write_aborts_when_file_changes_during_approval(self):
        target = self.root / "note.txt"
        target.write_text("before", encoding="utf-8")
        def concurrent_edit(_message):
            target.write_text("someone else", encoding="utf-8")
            return True
        kit = Toolkit(self.root, approve=concurrent_edit)
        result = kit.execute("write_file", {"path": "note.txt", "content": "jarvis"})
        self.assertIn("error", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "someone else")

    def test_write_replace_failure_preserves_existing_file_and_cleans_temp(self):
        target = self.root / "note.txt"
        target.write_text("before", encoding="utf-8")
        with patch("jarvis.tools.os.replace", side_effect=OSError("disk error")):
            result = self.allowed.execute("write_file", {"path": "note.txt", "content": "after"})
        self.assertIn("error", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "before")
        self.assertEqual(list(self.root.glob(".jarvis-write-*")), [])

    def test_write_rejects_symlink_destination(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        (self.root / "link.txt").symlink_to(outside)
        result = self.allowed.execute("write_file", {"path": "link.txt", "content": "wrong"})
        self.assertIn("error", result)
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside")

    def test_empty_hash_creates_only_when_target_is_absent(self):
        outcome = self.allowed.execute('write_file', {'path': 'new.txt', 'content': 'teste', 'expected_sha256': ''})
        self.assertEqual(outcome['result']['status'], 'written')
        self.assertEqual((self.root / 'new.txt').read_text(), 'teste')
        empty = self.root / 'empty.txt'
        empty.write_text('')
        denied = self.allowed.execute('write_file', {'path': 'empty.txt', 'content': 'replace', 'expected_sha256': ''})
        self.assertIn('error', denied)
        self.assertEqual(empty.read_text(), '')

    def test_home_shorthand_resolves_before_root_authorization(self):
        self.allowed.allowed_roots = [Path.home()]
        self.assertEqual(self.allowed.path('~/Documents'), Path.home() / 'Documents')

    def test_creation_sentinel_still_rejects_concurrent_file_creation(self):
        target = self.root / 'concurrent.txt'
        def race(_):
            target.write_text('someone else')
            return True
        kit = Toolkit(self.root, approve=race)
        result = kit.execute('write_file', {'path': target.name, 'content': 'jarvis', 'expected_sha256': ''})
        self.assertIn('error', result)
        self.assertEqual(target.read_text(), 'someone else')


if __name__ == "__main__":
    unittest.main()
