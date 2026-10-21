"""Visão: proteção de privacidade, tamanho e formato Responses sem desktop real."""
import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.vision import analyze_screen, prepare_image, MAX_IMAGE_BYTES
from jarvis.fcc import FCCError
from jarvis.wayland import WaylandError


class VisionTests(unittest.TestCase):
    def test_requires_explicit_question_and_model(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(WaylandError):
                analyze_screen(Mock(), "ollama/vision", td, lambda _: True, "")
            with self.assertRaises(WaylandError):
                analyze_screen(Mock(), "", td, lambda _: True, "What is on screen?")

    def test_blocks_remote_model_by_default_before_capture(self):
        with patch.dict(os.environ, {"JARVIS_ALLOW_REMOTE_VISION": ""}):
            with patch("jarvis.vision.screenshot", side_effect=AssertionError("must not capture")):
                with self.assertRaises(WaylandError):
                    analyze_screen(Mock(), "provider/vision", ".", lambda _: True, "Descrição")

    def test_rejection_of_capture_prevents_upload(self):
        client = Mock()
        with patch("jarvis.vision.screenshot", return_value={"status":"rejected"}):
            self.assertEqual(analyze_screen(client, "ollama/vision", ".", lambda _: True, "Descreva")["status"], "rejected")
        client.responses.assert_not_called()

    def test_rejection_of_upload_prevents_request(self):
        client = Mock()
        with patch("jarvis.vision.screenshot", return_value={"status":"saved", "path":"/mock/image.png"}), patch("jarvis.vision.prepare_image", return_value="data:image/jpeg;base64,AA=="):
            self.assertEqual(analyze_screen(client, "ollama/vision", ".", lambda _: False, "Descreva")["stage"], "send_image")
        client.responses.assert_not_called()

    def test_sent_payload_has_one_image_and_no_tools(self):
        client = Mock()
        client.responses.return_value = {"output":[{"type":"message","content":[{"type":"output_text","text":"Uma janela aberta."}]}]}
        with patch("jarvis.vision.screenshot", return_value={"status":"saved", "path":"/mock/image.png"}), patch("jarvis.vision.prepare_image", return_value="data:image/jpeg;base64,AA=="):
            result = analyze_screen(client, "ollama/vision", ".", lambda _: True, "Explique a tela")
        self.assertEqual(result["status"], "analyzed")
        payload=client.responses.call_args.args[0]
        self.assertEqual(payload["model"], "ollama/vision")
        self.assertEqual(payload["tools"], [])
        self.assertEqual(payload["input"][0]["content"][1]["type"], "input_image")
        self.assertEqual(payload["input"][0]["content"][0]["text"], "Explique a tela")
        self.assertEqual(result["answer"], "Uma janela aberta.")

    def test_remote_requires_explicit_opt_in(self):
        client = Mock()
        client.responses.return_value={"output_text":"ok"}
        with patch.dict(os.environ, {"JARVIS_ALLOW_REMOTE_VISION":"1"}), patch("jarvis.vision.screenshot", return_value={"status":"saved","path":"/mock/image.png"}), patch("jarvis.vision.prepare_image", return_value="data:image/jpeg;base64,AA=="):
            result=analyze_screen(client, "provider/vision", ".", lambda _: True, "Descreva")
        self.assertEqual(result["uploaded_to"], "PROVEDOR REMOTO")

    def test_targeting_incomplete_is_retried_once_without_new_permissions(self):
        client = Mock()
        client.responses.side_effect = [
            FCCError("FCC retornou response.incomplete (motivo: max_output_tokens)"),
            {"output_text": '{"found":false,"reason":"Não visível"}'},
        ]
        approvals=[]
        def approve(action):
            approvals.append(action)
            return True
        with patch("jarvis.vision.screenshot", return_value={"status":"saved","path":"/fake/screenshot.png"}) as capture, patch("jarvis.vision.prepare_image", return_value="data:image/jpeg;base64,AA==") as prepare:
            result = analyze_screen(client,"ollama/qwen3.5:2b",".",approve,
                "Localize um botão", max_output_tokens=2048,
                reasoning_effort="none", retry_incomplete=True)
        self.assertEqual(result["status"],"analyzed")
        self.assertEqual(client.responses.call_count,2)
        self.assertEqual(client.responses.call_args_list[0].args[0]["max_output_tokens"],2048)
        self.assertEqual(client.responses.call_args_list[1].args[0]["max_output_tokens"],4096)
        self.assertEqual(client.responses.call_args_list[0].args[0]["reasoning"],{"effort":"none"})
        # O mock de screenshot ignora a autorização da captura; só o envio real chama approve.
        self.assertEqual(len(approvals),1)
        capture.assert_called_once()
        prepare.assert_called_once()

    def test_retry_is_bounded_even_if_model_stays_incomplete(self):
        client=Mock()
        client.responses.side_effect=FCCError("FCC retornou response.incomplete (motivo: max_output_tokens)")
        with patch("jarvis.vision.screenshot",return_value={"status":"saved","path":"/fake/screenshot.png"}),patch("jarvis.vision.prepare_image",return_value="data:image/jpeg;base64,AA=="):
            with self.assertRaises(FCCError):
                analyze_screen(client,"ollama/qwen3.5:2b",".",lambda _:True,
                    "Localize",max_output_tokens=2048,reasoning_effort="none",retry_incomplete=True)
        self.assertEqual(client.responses.call_count,2)

    def test_no_retry_for_other_provider_failures(self):
        client=Mock()
        client.responses.side_effect=FCCError("HTTP 400: invalid request",400)
        with patch("jarvis.vision.screenshot",return_value={"status":"saved","path":"/fake/screenshot.png"}),patch("jarvis.vision.prepare_image",return_value="data:image/jpeg;base64,AA=="):
            with self.assertRaises(FCCError):
                analyze_screen(client,"ollama/qwen3.5:2b",".",lambda _:True,
                    "Localize",max_output_tokens=2048,retry_incomplete=True)
        client.responses.assert_called_once()

    def test_actual_image_is_compressed_without_network(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            original=Path(td)/"source.png"
            Image.new("RGB", (2000, 1000), (200, 180, 100)).save(original)
            output=prepare_image(original)
            self.assertTrue(output.startswith("data:image/jpeg;base64,"))
            encoded=base64.b64decode(output.split(",",1)[1])
            self.assertLessEqual(len(encoded), MAX_IMAGE_BYTES)
            from io import BytesIO
            with Image.open(BytesIO(encoded)) as image:
                self.assertLessEqual(image.width,1280)
                self.assertLessEqual(image.height,900)

if __name__ == "__main__":
    unittest.main()
