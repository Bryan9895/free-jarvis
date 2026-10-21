import tempfile
import json
import unittest
from pathlib import Path
from jarvis.tools import Toolkit
from jarvis.memory import Memory
from jarvis.agent import Agent

class DummyClient:
    def __init__(self): self.calls=[]
    def responses(self, payload):
        self.calls.append(payload)
        if len(self.calls)==1:
            return {"id":"resp_1", "output":[{"type":"function_call", "name":"list_files", "call_id":"call_1", "arguments":json.dumps({"path":"."})}]}
        return {"id":"resp_2", "output":[{"type":"message","content":[{"type":"output_text","text":"Diretório analisado."}]}]}

class JarvisTests(unittest.TestCase):
    def test_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Toolkit(Path(tmp))
            with self.assertRaises(ValueError): t.path("../outside")
            with self.assertRaises(ValueError): t.path("/etc/passwd")

    def test_write_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Toolkit(Path(tmp), lambda _action: False)
            self.assertEqual(t.write_file("a.txt","hello")["status"],"rejected")
            self.assertFalse((Path(tmp)/"a.txt").exists())
            t.approve=lambda _action: True
            t.write_file("a.txt","hello")
            self.assertEqual(t.read_file("a.txt"),"hello")

    def test_command_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Toolkit(Path(tmp))
            self.assertIn("error", t.execute("run_command",{"command":"rm -rf ."}))
            self.assertIn("error", t.execute("run_command",{"command":"git push"}))

    def test_loop_and_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Toolkit(Path(tmp))
            m=Memory(Path(tmp)/"state.sqlite3")
            c=DummyClient()
            a=Agent(c,t,m,"test-model")
            self.assertEqual(a.ask("Liste meus arquivos"),"Diretório analisado.")
            self.assertEqual(c.calls[1]["input"][-1]["type"],"function_call_output")
            self.assertEqual([x["role"] for x in m.recent()], ["user", "assistant"])
            m.close()

if __name__=="__main__": unittest.main()
