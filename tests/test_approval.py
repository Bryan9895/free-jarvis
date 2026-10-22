"""Regressões do modo de autoaprovação por sessão."""
import tempfile
import unittest
from pathlib import Path

from jarvis.approval import ApprovalPolicy
from jarvis.tools import Toolkit


class ApprovalModeTests(unittest.TestCase):
    def test_default_is_manual_and_does_not_approve_without_callback(self):
        policy = ApprovalPolicy(report=lambda _: None)
        self.assertEqual(policy.mode, "manual")
        self.assertFalse(policy("CRIAR ARQUIVO"))
        self.assertEqual(policy.auto_approved, 0)

    def test_auto_approves_without_reasking_then_can_disable(self):
        logs = []
        prompts = []
        policy = ApprovalPolicy(
            auto=True,
            manual_callback=lambda msg: prompts.append(msg) or False,
            report=logs.append,
        )
        self.assertTrue(policy("FOCAR FIREFOX"))
        self.assertEqual(policy.auto_approved, 1)
        self.assertFalse(prompts)
        self.assertIn("AUTOAUTORIZADO", logs[0])
        policy.set_mode("manual")
        self.assertFalse(policy("CRIAR ARQUIVO"))
        self.assertEqual(len(prompts), 1)
        policy.set_mode("auto")
        self.assertTrue(policy("ABRIR PROJETO"))
        self.assertEqual(policy.auto_approved, 2)

    def test_auto_does_not_bypass_workspace_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            policy = ApprovalPolicy(auto=True, report=lambda _: None)
            workspace = Path(temp) / "workspace"
            kit = Toolkit(workspace, approve=policy)
            blocked = kit.execute("write_file", {
                "path": "../fora.txt", "content": "não permitido"})
            self.assertIn("error", blocked)
            self.assertFalse((Path(temp) / "fora.txt").exists())
            self.assertEqual(policy.auto_approved, 0)
            allowed = kit.execute("write_file", {
                "path": "permitido.txt", "content": "ok"})
            self.assertEqual(allowed["result"]["status"], "written")
            self.assertEqual((workspace / "permitido.txt").read_text(), "ok")
            self.assertEqual(policy.auto_approved, 1)
            self.assertIn("error", kit.execute("run_command", {
                "command": "sudo rm -rf /"}))
            kit.close()

    def test_unknown_mode_and_action_rejected(self):
        policy = ApprovalPolicy(auto=True, report=lambda _: None)
        with self.assertRaises(ValueError):
            policy.set_mode("root")
        self.assertFalse(policy(None))

    def test_revocation_blocks_actions_until_explicitly_reenabled(self):
        with tempfile.TemporaryDirectory() as temp:
            policy = ApprovalPolicy(auto=True, report=lambda _: None)
            kit = Toolkit(Path(temp), approve=policy)
            policy.revoke()
            self.assertEqual(policy.mode, "revoked")
            denied = kit.execute("write_file", {"path": "blocked.txt", "content": "no"})
            self.assertEqual(denied["result"]["status"], "rejected")
            self.assertEqual(kit.execute("list_files", {"path": "."})["result"]["status"],
                             "rejected")
            self.assertFalse((Path(temp) / "blocked.txt").exists())
            self.assertEqual(policy.auto_approved, 0)
            policy.set_mode("auto")
            allowed = kit.execute("write_file", {"path": "allowed.txt", "content": "yes"})
            self.assertEqual(allowed["result"]["status"], "written")
            kit.close()


if __name__ == "__main__":
    unittest.main()
