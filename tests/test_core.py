import json
import os
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path
from jarvis.tools import Toolkit
from jarvis.agent import Agent
from jarvis.memory import Memory

class FakeClient:
    def __init__(self, sequence):
        self.sequence = iter(sequence)
        self.requests = []
    def responses(self, payload):
        self.requests.append(payload)
        return next(self.sequence)

class CoreTests(unittest.TestCase):
    def test_desktop_input_is_hidden_by_default(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"JARVIS_ENABLE_DESKTOP_INPUT": ""}):
            client = FakeClient([{"output":[{"type":"message","content":[{"type":"output_text","text":"ok"}]}]}])
            memory = Memory(Path(td)/"m.db")
            Agent(client, Toolkit(Path(td)), memory, "fake").ask("teste")
            self.assertNotIn("desktop_input", [t["name"] for t in client.requests[0]["tools"]])
            memory.close()

    def test_desktop_input_requires_opt_in_and_does_not_run(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"JARVIS_ENABLE_DESKTOP_INPUT":"1"}):
            toolkit=Toolkit(Path(td), approve=lambda _: False)
            with patch.dict(os.environ, {"XDG_SESSION_TYPE":"wayland"}):
                outcome=toolkit.execute("desktop_input", {"action":"click"})
            self.assertEqual(outcome["result"]["status"],"rejected")
            client=FakeClient([{"output":[{"type":"message","content":[{"type":"output_text","text":"ok"}]}]}])
            memory=Memory(Path(td)/"m.db")
            Agent(client, toolkit, memory, "fake").ask("teste")
            self.assertIn("desktop_input", [t["name"] for t in client.requests[0]["tools"]])
            memory.close()

    def test_fast_question_omits_tools_and_reasoning(self):
        with tempfile.TemporaryDirectory() as td:
            client=FakeClient([{"output":[{"type":"message","content":[{"type":"output_text","text":"É uma rede."}]}]}])
            memory=Memory(Path(td)/"m.db")
            agent=Agent(client, Toolkit(Path(td)), memory, "ollama/model")
            self.assertEqual(agent.ask("O que é uma rede neural?"), "É uma rede.")
            self.assertEqual(client.requests[0]["tools"], [])
            self.assertEqual(client.requests[0]["reasoning"], {"effort": "none"})
            self.assertEqual(client.requests[0]["max_output_tokens"], 512)
            self.assertEqual(agent.last_metrics["route"], "fast")
            self.assertEqual(agent.last_metrics["model_rounds"], 1)
            memory.close()

    def test_fast_remote_model_does_not_force_ollama_reasoning(self):
        with tempfile.TemporaryDirectory() as td:
            client=FakeClient([{"output":[{"type":"message","content":[{"type":"output_text","text":"OK"}]}]}])
            memory=Memory(Path(td)/"m.db")
            agent=Agent(client, Toolkit(Path(td)), memory, "gemini/example")
            agent.ask("O que é fotossíntese?")
            self.assertNotIn("reasoning", client.requests[0])
            self.assertEqual(client.requests[0]["tools"], [])
            memory.close()

    def test_desktop_requests_keep_tools(self):
        with tempfile.TemporaryDirectory() as td:
            client=FakeClient([{"output":[{"type":"message","content":[{"type":"output_text","text":"ok"}]}]}])
            memory=Memory(Path(td)/"m.db")
            agent=Agent(client, Toolkit(Path(td)), memory, "fake")
            agent.ask("Explique o erro na minha tela")
            self.assertTrue(client.requests[0]["tools"])
            self.assertEqual(agent.last_metrics["route"], "tools")
            memory.close()

    def test_duplicate_tool_call_executes_once(self):
        with tempfile.TemporaryDirectory() as td:
            def call(cid):
                return {"type":"function_call","name":"list_files","call_id":cid,"arguments":'{"path":"."}'}
            client=FakeClient([
                {"output":[call("c1")]}, {"output":[call("c2")]},
                {"output":[{"type":"message","content":[{"type":"output_text","text":"Concluído"}]}]},
            ])
            memory=Memory(Path(td)/"m.db")
            toolkit=Toolkit(Path(td))
            with patch.object(toolkit,"execute",wraps=toolkit.execute) as execute:
                agent=Agent(client, toolkit, memory, "fake")
                agent.ask("Liste os arquivos na pasta")
                self.assertEqual(execute.call_count,1)
            self.assertEqual(agent.last_metrics["tools_executed"],1)
            second=json.loads(client.requests[2]["input"][-1]["output"])
            self.assertTrue(second["reused_previous_result"])
            memory.close()

    def test_empty_assistant_message_omitted_before_tool_reply(self):
        """NIM não aceita mensagens assistant com content vazio."""
        with tempfile.TemporaryDirectory() as td:
            call = {"type": "function_call", "name": "desktop_windows",
                    "call_id": "call-1", "arguments": "{}"}
            first = {"output": [
                {"type": "message", "role": "assistant", "content": []},
                {"type": "message", "role": "assistant",
                 "content": [{"type": "output_text", "text": "  "}]},
                call]}
            second = {"output": [{"type": "message",
                       "content": [{"type": "output_text", "text": "Encontrei janelas."}]}]}
            client = FakeClient([first, second])
            memory = Memory(Path(td) / "memory.db")
            toolkit = Toolkit(Path(td))
            with patch.object(toolkit, "execute", return_value={
                "result": {"status": "observed", "windows": []}}):
                answer = Agent(client, toolkit, memory, "fake").ask(
                    "Quais janelas estão abertas?", mode="tools")
            self.assertEqual(answer, "Encontrei janelas.")
            following = client.requests[1]["input"]
            self.assertEqual(sum(i.get("type") == "function_call" for i in following), 1)
            self.assertEqual(sum(i.get("type") == "function_call_output" for i in following), 1)
            self.assertFalse(any(i.get("type") == "message" for i in following))
            memory.close()

    def test_nonempty_assistant_message_preserved(self):
        from jarvis.agent import _valid_history_output
        items = [
            {"type": "message", "content": [
                {"type": "output_text", "text": "texto"},
                {"type": "output_text", "text": ""}]},
            {"type": "function_call", "name": "list_files", "call_id": "x",
             "arguments": "{}"}]
        result = _valid_history_output(items)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["content"],
                         [{"type": "output_text", "text": "texto"}])

    def test_desktop_source_and_completeness_appear_in_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            first = {"output": [{"type": "function_call", "name": "desktop_windows",
                                  "call_id": "c1", "arguments": "{}"}]}
            last = {"output": [{"type": "message", "content": [
                {"type": "output_text", "text": "Janelas observadas."}]}]}
            client = FakeClient([first, last])
            mem = Memory(Path(td) / "memory.db")
            kit = Toolkit(Path(td))
            with patch.object(kit, "execute", return_value={"result": {
                "status": "observed", "source": "gnome_shell_extension",
                "complete": False, "windows": []}}):
                agent = Agent(client, kit, mem, "fake")
                agent.ask("Liste as janelas", mode="tools")
            evidence = agent.last_metrics["tool_outcomes"][0]["outcome"]["result"]
            self.assertEqual(evidence["source"], "gnome_shell_extension")
            self.assertIs(evidence["complete"], False)
            self.assertNotIn("windows", evidence)
            mem.close()

    def test_focus_window_returns_immediately_without_second_fcc_round(self):
        with tempfile.TemporaryDirectory() as td:
            call = {"type": "function_call", "name": "focus_window",
                    "call_id": "focus-1", "arguments": '{"app":"firefox"}'}
            client = FakeClient([{"output": [call]}])
            memory = Memory(Path(td)/"db.sqlite3")
            kit = Toolkit(Path(td))
            with patch.object(kit, "execute", return_value={"result": {
                "status": "focused_verified", "title": "Mozilla Firefox",
                "app": "firefox_firefox", "pid": 100}}) as execute:
                agent = Agent(client, kit, memory, "fake")
                answer = agent.ask("Jarvis, coloque o Firefox em primeiro plano")
            self.assertIn("foco confirmado", answer)
            self.assertEqual(len(client.requests), 1)
            execute.assert_called_once()
            self.assertTrue(agent.last_metrics["direct_tool_reply"])
            self.assertEqual(agent.last_metrics["model_rounds"], 1)
            self.assertEqual(len(memory.recent()), 2)
            memory.close()

    def test_focus_denial_reply_is_local_and_never_claims_success(self):
        with tempfile.TemporaryDirectory() as td:
            call = {"type": "function_call", "name": "focus_window",
                    "call_id": "focus-2", "arguments": '{"app":"firefox"}'}
            client = FakeClient([{"output": [call]}])
            memory = Memory(Path(td)/"db.sqlite3")
            kit = Toolkit(Path(td))
            with patch.object(kit, "execute", return_value={"result": {
                "status": "rejected"}}):
                agent = Agent(client, kit, memory, "fake")
                answer = agent.ask("Coloque o Firefox em primeiro plano")
            self.assertIn("cancelada", answer)
            self.assertNotIn("confirmado", answer)
            self.assertEqual(len(client.requests), 1)
            memory.close()

    def test_multi_tool_round_does_not_short_circuit(self):
        with tempfile.TemporaryDirectory() as td:
            focus = {"type": "function_call", "name": "focus_window",
                     "call_id": "f1", "arguments": '{"app":"firefox"}'}
            inventory = {"type": "function_call", "name": "desktop_windows",
                         "call_id": "w1", "arguments": "{}"}
            client = FakeClient([
                {"output": [focus, inventory]},
                {"output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "Concluído."}]}]},
            ])
            memory = Memory(Path(td)/"db.sqlite3")
            kit = Toolkit(Path(td))
            with patch.object(kit, "execute", return_value={"result": {
                "status": "focused_verified", "title": "Mozilla Firefox"}}):
                agent = Agent(client, kit, memory, "fake")
                answer = agent.ask("Coloque o Firefox em primeiro plano e liste as janelas")
            self.assertEqual(answer, "Concluído.")
            self.assertEqual(len(client.requests), 2)
            self.assertFalse(agent.last_metrics["direct_tool_reply"])
            memory.close()

    def test_fast_mode_never_executes_tools(self):
        with tempfile.TemporaryDirectory() as td:
            call={"type":"function_call","name":"write_file","call_id":"c1",
                  "arguments":'{"path":"danger","content":"x"}'}
            client=FakeClient([{"output":[call]}])
            memory=Memory(Path(td)/"m.db")
            agent=Agent(client,Toolkit(Path(td),approve=lambda _:True),memory,"fake")
            answer=agent.ask("escreva",mode="fast")
            self.assertIn("modo rápido",answer)
            self.assertFalse((Path(td)/"danger").exists())
            memory.close()

    def test_call_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            call = {"type":"function_call", "name":"list_files", "call_id":"c1", "arguments":"{}"}
            client = FakeClient([{"output":[call]}, {"output":[{"type":"message", "content":[{"type":"output_text", "text":"ok"}]}]}])
            memory = Memory(Path(td)/"m.db")
            result = Agent(client, Toolkit(Path(td)), memory, "fake").ask("Liste")
            self.assertEqual(result, "ok")
            self.assertEqual(client.requests[1]["input"][-1]["call_id"], "c1")
            self.assertFalse(client.requests[0]["parallel_tool_calls"])
            self.assertEqual(len(memory.recent()), 2)
            memory.close()

    def test_invalid_tool_arguments_are_returned_as_error(self):
        with tempfile.TemporaryDirectory() as td:
            client = FakeClient([{"output":[{"type":"function_call", "name":"list_files", "call_id":"c1", "arguments":"{not json"}]},
                                 {"output":[{"type":"message", "content":[{"type":"output_text", "text":"Falhou."}]}]}])
            memory = Memory(Path(td)/"m.db")
            Agent(client, Toolkit(Path(td)), memory, "fake").ask("Liste")
            outcome = json.loads(client.requests[1]["input"][-1]["output"])
            self.assertIn("error", outcome)
            memory.close()

    def test_no_side_effects_outside_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            t = Toolkit(Path(td)/"project", approve=lambda _: True)
            self.assertIn("error", t.execute("write_file", {"path":"../secret", "content":"no"}))
            self.assertIn("error", t.execute("run_command", {"command":"git -C / status"}))
            self.assertIn("error", t.execute("run_command", {"command":"ls /etc"}))
            self.assertIn("error", t.execute("run_command", {"command":"gh repo delete"}))

    def test_run_allowed_command(self):
        with tempfile.TemporaryDirectory() as td:
            result = Toolkit(Path(td)).execute("run_command", {"command":"pwd"})
            self.assertEqual(result["result"]["exit_code"], 0)

    def test_rejection_after_limit(self):
        with tempfile.TemporaryDirectory() as td:
            call = {"type":"function_call", "name":"list_files", "call_id":"c1", "arguments":"{}"}
            client = FakeClient([{"output":[call]} for _ in range(7)])
            memory = Memory(Path(td)/"m.db")
            answer = Agent(client, Toolkit(Path(td)), memory, "fake").ask("Repita")
            self.assertIn("Limite", answer)
            self.assertEqual(len(memory.recent()), 2)
            self.assertEqual(client.requests[-1]["tools"], [])
            memory.close()

if __name__ == "__main__":
    unittest.main()
