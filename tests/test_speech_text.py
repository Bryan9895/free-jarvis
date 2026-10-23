import unittest
from jarvis.speech_text import ResponseText, speech_chunks


class SpeechTextTests(unittest.TestCase):
    def test_markdown_keeps_meaning_and_math(self):
        response = ResponseText.from_display('# Resultado\n**Dois** vezes 2 * 3 = 6. [Detalhes](https://example.test)')
        self.assertEqual(response.spoken_text, 'Resultado Dois vezes 2 * 3 = 6. Detalhes')
        self.assertTrue(response.display_text.startswith('#'))

    def test_code_table_json_and_paths_are_not_read_literally(self):
        for value in ('```python\nprint(42)\n```', '| A | B |\n|---|---|\n| 1 | 2 |', '{"result": true}', '/home/bryan/projeto/arquivo.txt'):
            with self.subTest(value=value):
                spoken = ResponseText.from_display(value).spoken_text
                self.assertNotIn('print', spoken)
                self.assertNotIn('|', spoken)
                self.assertNotIn('true', spoken)
                self.assertNotIn('/home', spoken)
                self.assertTrue(spoken)

    def test_long_text_is_segmented_without_loss_or_reordering(self):
        text = ' '.join(f'Frase {i} completa.' for i in range(600))
        chunks = list(speech_chunks(text))
        self.assertGreater(len(text), 3000)
        self.assertEqual(' '.join(chunks), text)
        self.assertLessEqual(max(map(len, chunks)), 700)
