"""Validação de localização visual sem GNOME, sem rede e sem ações."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.targeting import parse_target, locate_target, save_preview
from jarvis.wayland import WaylandError

class TargetingTests(unittest.TestCase):
    def test_valid_region(self):
        result=parse_target('{"found":true,"label":"Pesquisar","confidence":0.7,"bbox":[100,200,300,400]}')
        self.assertEqual(result["bbox"], [100,200,300,400])
        self.assertEqual(result["confidence"], 0.7)

    def test_code_fence_is_accepted(self):
        result=parse_target('```json\n{"found":false,"reason":"sem botão"}\n```')
        self.assertFalse(result["found"])

    def test_explanatory_text_and_fenced_json(self):
        payload = '{"found":true,"label":"Arquivos","confidence":0.6,"bbox":[10,20,40,80]}'
        result=parse_target("Resposta do modelo:\\n" + payload + "\\nEssa é a região.")
        self.assertEqual(result["label"], "Arquivos")
        result=parse_target("Segue:\\n```json\\n"+payload+"\\n```")
        self.assertEqual(result["bbox"], [10,20,40,80])

    def test_multiple_objects_and_partial_json_rejected(self):
        good='{"found":false,"reason":"não localizado"}'
        with self.assertRaises(WaylandError):
            parse_target("Primeiro: "+good+" Segundo: "+good)
        with self.assertRaises(WaylandError):
            parse_target('{"found":true,"label":"x","bbox":')

    def test_unstructured_response_does_not_draw_or_act(self):
        answer="O ícone de arquivos parece estar na lateral."
        with patch("jarvis.targeting.analyze_screen",return_value={
            "status":"analyzed","answer":answer,"screenshot":"/mock/screen.png"
        }), patch("jarvis.targeting.save_preview",side_effect=AssertionError("must not draw")):
            result=locate_target(Mock(),"ollama/qwen3.5:2b",".",lambda _:True,"Ícone")
        self.assertEqual(result["status"],"unstructured")
        self.assertFalse(result["action_executed"])
        self.assertIn("ícone", result["model_excerpt"])

    def test_invalid_regions_rejected(self):
        regions = [
            [100, 200, 100, 400],
            [-1, 0, 20, 20],
            [20, 20, 1001, 90],
            [0, 0, 10],
            [0, 0, "10", 20],
            [0, 0, True, 20]
        ]
        for box in regions:
            with self.subTest(box=box):
                item={"found":True, "label":"Alvo","confidence":0.8,"bbox":box}
                with self.assertRaises(WaylandError):
                    parse_target(json.dumps(item))

    def test_invalid_confidence_and_noisy_text(self):
        for value in (-0.1, 1.1, "0.8", True):
            item={"found":True,"label":"Alvo","confidence":value,"bbox":[0,0,10,10]}
            with self.assertRaises(WaylandError):
                parse_target(json.dumps(item))
        # Uma explicação com um único JSON completo é recuperável.
        self.assertFalse(parse_target('Localizei: {"found":false,"reason":"ausente"}')["found"])
        self.assertTrue(parse_target('{"found":true,"label":"x","confidence":0.9,"bbox":[1,2,3,4]} outro texto')["found"])

    def test_remote_model_rejected_before_screenshot(self):
        with patch("jarvis.targeting.analyze_screen",side_effect=AssertionError("should not capture")):
            with self.assertRaises(WaylandError):
                locate_target(Mock(), "gemini/model", ".", lambda _:True, "Abrir")

    def test_rejection_no_file(self):
        with patch("jarvis.targeting.analyze_screen",return_value={"status":"rejected"}),patch("jarvis.targeting.save_preview",side_effect=AssertionError("must not draw")):
            result=locate_target(Mock(),"ollama/qwen3.5:2b",".",lambda _:False,"Alvo")
        self.assertEqual(result["status"],"rejected")

    def test_proposal_only_and_annotated_image(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"screen.png"
            Image.new("RGB",(800,600),"white").save(source)
            answer='{"found":true,"label":"Campo","confidence":0.82,"bbox":[100,200,600,400]}'
            with patch("jarvis.targeting.analyze_screen",return_value={"status":"analyzed","screenshot":str(source),"answer":answer}):
                output=locate_target(Mock(),"ollama/qwen3.5:2b",td,lambda _:True,"Campo")
            self.assertEqual(output["status"],"proposal_only")
            self.assertFalse(output["action_executed"])
            self.assertTrue(Path(output["preview"]).is_file())
            with Image.open(output["preview"]) as image:
                self.assertEqual(image.size,(800,600))
                self.assertNotEqual(image.getpixel((80,120)),(255,255,255))
            with Image.open(source) as image:
                self.assertEqual(image.getpixel((80,120)),(255,255,255))

if __name__=="__main__":
    unittest.main()
