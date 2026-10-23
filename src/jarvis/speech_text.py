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


def speech_chunks(text, max_chars=700):
    """Frases em ordem; frases grandes dividem por palavras, sem perder conteúdo."""
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        yield from textwrap.wrap(sentence, width=max_chars, break_long_words=False,
                                 break_on_hyphens=False)
