"""Opções de voz sintética. IDs adicionais vêm do repositório de referência.

A disponibilidade depende da conta ElevenLabs; um ID conhecido não autoriza
acessar/clonar a voz de outra pessoa. O usuário pode informar sua própria voz.
"""
VOICE_PRESETS = {
    "Adam · voz padrão": "pNInz6obpgDQGcFmaJgB",
    "Adryan · assistente firme (referência)": "xHUwLsLfyqiYOIVTzLRW",
    "Lucas · grave e sereno (referência)": "GIuLCSVfgJaUuh7hYOY8",
    "Cássio · grave e direto (referência)": "TY3h8ANhQUsJaa0Bga5F",
}
VOICE_PRESETS_BY_ID = {identifier: name for name, identifier in VOICE_PRESETS.items()}
