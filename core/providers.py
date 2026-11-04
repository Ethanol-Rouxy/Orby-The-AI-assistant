"""Gestion des fournisseurs d'IA avec basculement automatique.

Ce module ne dépend PAS de l'interface : il prévient simplement via un
callback `on_switch(ancien, nouveau, raison)` quand le fournisseur change.
"""
import os
import time

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

import config


class AllProvidersFailed(Exception):
    pass


def _classify(e: Exception):
    """Retourne (raison lisible, durée de pause en secondes)."""
    if isinstance(e, RateLimitError):
        return "quota ou limite atteinte", config.COOLDOWN_SECONDS
    if isinstance(e, (AuthenticationError, PermissionDeniedError)):
        return "clé API refusée", 3600
    if isinstance(e, APIConnectionError):  # inclut les timeouts
        return "connexion impossible", 30
    if isinstance(e, APIStatusError):
        return f"erreur serveur ({e.status_code})", 30
    return f"erreur : {str(e)[:80]}", 30


class Provider:
    def __init__(self, cfg: dict):
        self.name = cfg["name"]
        self.model = cfg["model"]
        self.color = cfg["color"]
        key = os.getenv(cfg["api_key_env"], "").strip()
        self.available = bool(key)
        self.client = (
            OpenAI(api_key=key, base_url=cfg["base_url"], timeout=30, max_retries=0)
            if key
            else None
        )
        self.blocked_until = 0.0
        self.last_reason = ""


class ProviderPool:
    def __init__(self, on_switch=None):
        all_providers = [Provider(c) for c in config.PROVIDERS]
        self.providers = [p for p in all_providers if p.available]
        self.current = None
        self.on_switch = on_switch or (lambda old, new, reason: None)

    @property
    def first_name(self):
        return self.providers[0].name if self.providers else None

    def color_of(self, name: str) -> str:
        for p in self.providers:
            if p.name == name:
                return p.color
        return "#888888"

    def chat(self, messages: list, tools: list | None = None):
        if not self.providers:
            raise AllProvidersFailed(
                "Aucune clé API trouvée. Remplis le fichier .env (voir .env.example)."
            )
        for p in self.providers:
            if p.blocked_until > time.time():
                continue
            try:
                kwargs = {"model": p.model, "messages": messages}
                if tools:
                    kwargs["tools"] = tools
                resp = p.client.chat.completions.create(**kwargs)
            except Exception as e:  # on essaie le fournisseur suivant
                p.last_reason, cooldown = _classify(e)
                p.blocked_until = time.time() + cooldown
                continue
            self._switch_to(p)
            return resp
        raise AllProvidersFailed(self._summary())

    def _switch_to(self, p: Provider):
        if self.current is p:
            return
        now = time.time()
        higher = self.providers[: self.providers.index(p)]
        reason = " ; ".join(
            f"{q.name} : {q.last_reason}" for q in higher if q.blocked_until > now
        )
        old = self.current.name if self.current else None
        self.current = p
        self.on_switch(old, p.name, reason)

    def _summary(self) -> str:
        now = time.time()
        lines = []
        for p in self.providers:
            wait = max(0, int(p.blocked_until - now))
            lines.append(f"- {p.name} : {p.last_reason or 'indisponible'} (retry dans {wait}s)")
        return "Aucune IA disponible pour le moment :\n" + "\n".join(lines)
