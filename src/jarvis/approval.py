"""Política local de aprovações para ferramentas já autorizadas pela JARVIS.

Não altera permissões do SO, portais GNOME, listas de comandos ou raízes
permitidas. Auto significa consentimento antecipado durante esta sessão.
"""
from __future__ import annotations


class ApprovalPolicy:
    def __init__(self, auto=False, manual_callback=None, report=print):
        if not isinstance(auto, bool):
            raise TypeError("auto deve ser booleano")
        self.auto = auto
        self.revoked = False
        self.manual_callback = manual_callback or (lambda _action: False)
        self.report = report
        self.auto_approved = 0

    def __call__(self, action):
        if not isinstance(action, str):
            return False
        if self.mode == "revoked":
            self.report("⛔ SESSÃO REVOGADA: " + action[:240])
            return False
        if self.auto:
            self.auto_approved += 1
            self.report("⚡ AUTOAUTORIZADO (sessão): " + action[:240])
            return True
        return bool(self.manual_callback(action))

    def set_mode(self, name):
        if name not in ("auto", "manual", "revoked"):
            raise ValueError("Modo de aprovação inválido")
        self.revoked = name == "revoked"
        self.auto = name == "auto"

    def revoke(self):
        self.set_mode("revoked")

    def confirm_sensitive(self, action):
        """Ações que podem perder dados sempre pedem confirmação específica."""
        if self.revoked or not isinstance(action, str):
            return False
        return bool(self.manual_callback(action))

    @property
    def mode(self):
        if getattr(self, "revoked", False):
            return "revoked"
        return "auto" if self.auto else "manual"
