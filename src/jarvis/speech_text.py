"""Representação falada determinística, sem segunda inferência nem truncamento."""
from dataclasses import dataclass
import json
import re
import textwrap


@dataclass(frozen=True)
class ResponseText:
    display_text: str
    spoken_text: str

    @classmethod
    def from_display(cls, text):
        return cls(text, spoken_text(text))


def spoken_text(text):
    stripped = text.strip()
    try:
        value = json.loads(stripped)
    except (ValueError, TypeError):
        value = None
    if isinstance(value, (dict, list)):
        return "O resultado estruturado está na conversa."
    text = re.sub(r"```[^\n]*\n.*?(?:```|\Z)", " Há um bloco de código na conversa. ", text, flags=re.S)
    text = re.sub(r"!?\[([^\]]+)\]\([^\s)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "endereço disponível na conversa", text)
    text = re.sub(r"(?<!\w)/(?:[^\s/]+/)+[^\s,;]*", "caminho disponível na conversa", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m[1] or m[2], text)
    text = re.sub(r"(?<!\w)\*(\S(?:[^*\n]*?\S)?)\*(?!\w)",
                  lambda match: match[0] if re.fullmatch(r'[\d\s.,+\-/=]+', match[1]) else match[1], text)
    lines, in_table = [], False
    for line in text.splitlines():
        if line.strip().startswith('|') and line.count('|') >= 2:
            if not in_table:
                lines.append('Há uma tabela com os detalhes na conversa.')
            in_table = True
            continue
        in_table = False
        line = re.sub(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)", "", line)
        lines.append(line)
    return re.sub(r"\s+", " ", ' '.join(lines)).strip()


_ABBREVIATIONS = frozenset(('sr.', 'sra.', 'dr.', 'dra.', 'prof.', 'profa.', 'etc.', 'ex.', 'av.', 'art.'))


def _boundaries(text):
    if text.lstrip().startswith(('{', '[', '|')):
        return
    for match in re.finditer(r'[.!?](?:["”\')\]]*)\s+', text):
        end = match.end()
        prefix = text[:match.start() + 1]
        word = prefix.rsplit(None, 1)[-1].casefold()
        if word in _ABBREVIATIONS or re.fullmatch(r'[A-ZÀ-Ú]\.', word.upper()):
            continue
        # Não dividir links, código ou marcação ainda incompleta.
        if prefix.count('```') % 2 or prefix.count('`') % 2 or prefix.count('[') != prefix.count(']'):
            continue
        yield end


class SentenceBuffer:
    def __init__(self):
        self.pending = ''

    def feed(self, text):
        self.pending += text
        chunks = []
        for end in list(_boundaries(self.pending)):
            chunks.append(end)
        if not chunks:
            return []
        parts, start = [], 0
        for end in chunks:
            parts.append(self.pending[start:end].strip())
            start = end
        self.pending = self.pending[start:]
        return [part for part in parts if part]

    def finish(self):
        tail, self.pending = self.pending.strip(), ''
        return [tail] if tail else []


def speech_chunks(text, max_chars=240):
    """Frases em ordem; frases grandes dividem por palavras, sem perder conteúdo."""
    buffer = SentenceBuffer()
    for sentence in buffer.feed(text) + buffer.finish():
        yield from textwrap.wrap(sentence, width=max_chars, break_long_words=False,
                                 break_on_hyphens=False)
