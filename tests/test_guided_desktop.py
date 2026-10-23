"""Simulações de clique guiado: não envolvem permissão GNOME real."""
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from jarvis.guided_desktop import guided_click, _compare
from jarvis.wayland import WaylandError


def reject_async(coro):
    coro.close()
    raise AssertionError("unexpected async operation")


def return_async(value):
    def run(coro):
        coro.close()
        return value
    return run


class GuidedClickTests(unittest.TestCase):
    def setUp(self):
        self.session=patch.dict(os.environ, {"XDG_SESSION_TYPE":"wayland"})
        self.session.start()

    def tearDown(self):
        self.session.stop()

    def _observation(self):
        return {"status":"analyzed", "answer":"Parece haver botão no canto direito.",
                "screenshot":"/fake/before.png"}

    def test_requires_ollama_and_valid_goal_before_capture(self):
        with patch("jarvis.guided_desktop.analyze_screen", side_effect=AssertionError("must not capture")):
            with self.assertRaises(WaylandError):
                guided_click(Mock(), "gemini/vision", ".", lambda _:True, "abrir")
            with self.assertRaises(WaylandError):
                guided_click(Mock(), "ollama/qwen3.5:2b", ".", lambda _:True, "")

    def test_observation_rejection_does_not_click(self):
        with patch("jarvis.guided_desktop.analyze_screen",return_value={"status":"rejected"}), patch("jarvis.guided_desktop.asyncio.run",side_effect=reject_async):
            result=guided_click(Mock(),"ollama/qwen3.5:2b",".",lambda _:True,"alvo")
        self.assertEqual(result["status"],"rejected")

    def test_position_cancel_prevents_click(self):
        with patch("jarvis.guided_desktop.analyze_screen",return_value=self._observation()), patch("jarvis.guided_desktop.prepare_image",return_value="data:image/jpeg;base64,AA=="),patch("jarvis.guided_desktop.asyncio.run",side_effect=reject_async):
            result=guided_click(Mock(),"ollama/qwen3.5:2b",".",lambda _:True,"alvo",prompt_user=lambda _: "",output=lambda _:None)
        self.assertEqual(result["stage"],"cursor_position")

    def test_click_rejection_prevents_portal_start(self):
        with patch("jarvis.guided_desktop.analyze_screen",return_value=self._observation()), patch("jarvis.guided_desktop.prepare_image",return_value="data:image/jpeg;base64,AA=="),patch("jarvis.guided_desktop.asyncio.run",side_effect=reject_async):
            result=guided_click(Mock(),"ollama/qwen3.5:2b",".",lambda _:False,"alvo",prompt_user=lambda _:"CLICAR",output=lambda _:None)
        self.assertEqual(result["stage"],"click")

    def test_no_verification_does_not_recapture(self):
        approvals=iter([True, False])
        with patch("jarvis.guided_desktop.analyze_screen",return_value=self._observation()), patch("jarvis.guided_desktop.prepare_image",return_value="data:image/jpeg;base64,AA=="), patch("jarvis.guided_desktop.asyncio.run",side_effect=return_async({"status":"sent_unverified"})), patch("jarvis.guided_desktop.screenshot",side_effect=AssertionError("must not capture")):
            result=guided_click(Mock(),"ollama/qwen3.5:2b",".",lambda _:next(approvals),"alvo",prompt_user=lambda _:"clicar",output=lambda _:None)
        self.assertEqual(result["verification"],"not_requested")

    def test_full_workflow_uses_no_tools_and_two_images(self):
        client=Mock()
        client.responses.return_value={"output_text":"Não confirmado."}
        approvals=iter([True, True, True, True])
        with patch("jarvis.guided_desktop.analyze_screen",return_value=self._observation()), patch("jarvis.guided_desktop.prepare_image",side_effect=["data:image/jpeg;base64,AQ==","data:image/jpeg;base64,Ag=="]), patch("jarvis.guided_desktop.asyncio.run",side_effect=return_async({})),patch("jarvis.guided_desktop.screenshot",return_value={"status":"saved","path":"/fake/after.png"}):
            result=guided_click(client,"ollama/qwen3.5:2b",".",lambda _:next(approvals),"abrir configuracoes",prompt_user=lambda _:"clicar",output=lambda _:None)
        self.assertEqual(result["status"],"sent_unverified")
        self.assertEqual(result["assessment"],"Não confirmado.")
        payload=client.responses.call_args.args[0]
        self.assertEqual(payload["tools"],[])
        self.assertEqual(payload["model"],"ollama/qwen3.5:2b")
        images=[item for item in payload["input"][0]["content"] if item["type"]=="input_image"]
        self.assertEqual(len(images),2)
        self.assertNotEqual(images[0]["image_url"], images[1]["image_url"])

if __name__ == "__main__":
    unittest.main()
