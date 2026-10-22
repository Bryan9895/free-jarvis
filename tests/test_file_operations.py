"""Operações em arquivos confinadas ao workspace e com aprovação."""
import tempfile
import unittest
from pathlib import Path

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

if __name__ == "__main__":
    unittest.main()
