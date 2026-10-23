"""Registro central, concessões de capacidade e extensões explícitas."""
import tempfile
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.agent import Agent
from jarvis.approval import ApprovalPolicy
from jarvis.memory import Memory
from jarvis.registry import ToolRegistry
from jarvis.plugins import load_plugins
from jarvis.tools import DEFAULT_REGISTRY, TOOL_SPECS, Toolkit


class FakeClient:
    def __init__(self):
        self.tools = None

    def responses(self, payload):
        self.tools = payload["tools"]
        return {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "ok"}]}]}


class RegistryTests(unittest.TestCase):
    def test_builtin_catalog_has_one_executor_and_capability_per_spec(self):
        self.assertEqual(len(DEFAULT_REGISTRY.capabilities), 9)
        self.assertEqual({spec["name"] for spec in TOOL_SPECS},
                         {spec["name"] for spec in DEFAULT_REGISTRY.available_specs(
                             DEFAULT_REGISTRY.capabilities, desktop_input=True)})

    def test_capability_restricts_advertising_and_direct_execution_even_in_auto_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            policy = ApprovalPolicy(auto=True, report=lambda _: None)
            kit = Toolkit(Path(temp), approve=policy,
                          enabled_capabilities={"filesystem.read"})
            client = FakeClient()
            memory = Memory(Path(temp) / "memory.db")
            Agent(client, kit, memory, "fake").ask("Liste os arquivos")
            self.assertEqual({item["name"] for item in client.tools},
                             {"list_files"})
            denied = kit.execute("write_file", {"path": "blocked.txt", "content": "x"})
            self.assertIn("Capacidade não autorizada", denied["error"])
            self.assertEqual(policy.auto_approved, 0)
            self.assertFalse((Path(temp) / "blocked.txt").exists())
            memory.close()
            kit.close()

    def test_unknown_capability_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "desconhecidas"):
                Toolkit(Path(temp), enabled_capabilities={"root"})

    def test_environment_can_disable_all_capabilities(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
                "os.environ", {"JARVIS_ENABLED_CAPABILITIES": ""}):
            kit = Toolkit(Path(temp))
            self.assertEqual(kit.registry.available_specs(kit.capabilities.enabled), [])
            self.assertIn("Capacidade não autorizada", kit.execute("list_files", {})["error"])
            kit.close()

    def test_desktop_input_requires_opt_in_at_execution_boundary(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
                "os.environ", {"JARVIS_ENABLE_DESKTOP_INPUT": "0"}):
            kit = Toolkit(Path(temp), approve=lambda _: True)
            self.assertEqual(kit.execute("desktop_input", {"action": "click"}),
                             {"error": "Entrada gráfica desativada"})
            kit.close()

    def test_explicit_plugin_registration_needs_no_toolkit_method(self):
        registry = ToolRegistry()
        spec = {"type": "function", "name": "hello", "parameters": {"type": "object"}}
        registry.register(spec, "plugin.hello", lambda kit, name: kit.workspace.name + name)
        with self.assertRaisesRegex(ValueError, "duplicada"):
            registry.register(spec, "plugin.hello", lambda kit: None)
        with tempfile.TemporaryDirectory() as temp:
            kit = Toolkit(Path(temp), registry=registry)
            self.assertEqual(kit.execute("hello", {"name": "!"})["result"],
                             Path(temp).name + "!")
            kit.close()

    def test_operation_log_is_bounded_and_contains_no_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            kit = Toolkit(Path(temp), enabled_capabilities={"filesystem.read"})
            for _ in range(105):
                kit.execute("read_file", {"path": "private-secret.txt"})
            self.assertEqual(len(kit.operation_log), 100)
            entry = kit.operation_log[-1]
            self.assertEqual(entry["tool"], "read_file")
            self.assertEqual(entry["status"], "error")
            self.assertGreaterEqual(entry["duration_ms"], 0)
            self.assertNotIn("private-secret", str(entry))
            kit.close()

    def test_explicit_plugin_loader_is_isolated_from_default_registry(self):
        module = types.ModuleType("jarvis_test_plugin")
        module.register_tools = lambda registry: registry.register(
            {"type": "function", "name": "plugin_hello",
             "parameters": {"type": "object", "properties": {}}},
            "plugin.hello", lambda kit: "ok")
        with patch.dict(sys.modules, {"jarvis_test_plugin": module}):
            loaded = load_plugins(DEFAULT_REGISTRY, "jarvis_test_plugin")
        self.assertIsNone(DEFAULT_REGISTRY.get("plugin_hello"))
        self.assertEqual(loaded.get("plugin_hello").capability, "plugin.hello")
        with tempfile.TemporaryDirectory() as temp:
            kit = Toolkit(Path(temp), registry=loaded)
            self.assertEqual(kit.execute("plugin_hello", {})["result"], "ok")
            kit.close()

    def test_plugin_loader_rejects_duplicates_and_invalid_modules(self):
        with self.assertRaisesRegex(ValueError, "repetido"):
            load_plugins(DEFAULT_REGISTRY, "a,a")
        with self.assertRaisesRegex(ValueError, "inválido"):
            load_plugins(DEFAULT_REGISTRY, "../evil")


if __name__ == "__main__":
    unittest.main()
