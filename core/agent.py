"""Le cerveau : boucle question -> (outils) -> réponse.

Aucune dépendance à l'interface : l'UI s'abonne via deux callbacks.
  on_state(state)               state = idle | thinking | working | error
  on_switch(ancien, nouveau, raison)  quand l'IA utilisée change
"""
import json
from datetime import datetime

import config
from core import tools
from core.providers import AllProvidersFailed, ProviderPool


class Agent:
    def __init__(self, on_state=None, on_switch=None):
        self.on_state = on_state or (lambda s: None)
        self.pool = ProviderPool(on_switch=on_switch)
        self._extra = ""
        self.history = [{"role": "system", "content": self._system()}]

    def _system(self) -> str:
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        extra = f"\n\n{self._extra}" if self._extra else ""
        return f"{config.SYSTEM_PROMPT}\n\nDate et heure actuelles : {now}.{extra}"

    def set_mode(self, extra: str = ""):
        """Ajoute la consigne du mode choisi au prompt système."""
        self._extra = extra
        self.history[0] = {"role": "system", "content": self._system()}

    def ask(self, text: str) -> str:
        mark = len(self.history)
        self.history[0] = {"role": "system", "content": self._system()}   # heure à jour
        self.history.append({"role": "user", "content": text})
        self._trim()
        self.on_state("thinking")
        try:
            answer = self._loop()
            self.on_state("idle")
            return answer
        except AllProvidersFailed as e:
            del self.history[mark:]
            self.on_state("error")
            return f"⚠ {e}"
        except Exception as e:
            del self.history[mark:]
            self.on_state("error")
            return f"⚠ Erreur inattendue : {e}"

    def _loop(self) -> str:
        for _ in range(config.MAX_TOOL_STEPS):
            msg = self.pool.chat(self.history, tools.SCHEMAS).choices[0].message
            if not msg.tool_calls:
                answer = msg.content or "(réponse vide)"
                self.history.append({"role": "assistant", "content": answer})
                return answer

            calls = [
                {"id": tc.id or f"call_{i}", "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments or "{}"}}
                for i, tc in enumerate(msg.tool_calls)
            ]
            self.history.append(
                {"role": "assistant", "content": msg.content or "", "tool_calls": calls})
            self.on_state("working")
            for call in calls:
                try:
                    args = json.loads(call["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}
                result = tools.run_tool(call["function"]["name"], args)
                self.history.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": result})
        return "J'ai enchaîné trop d'actions sans conclure, reformule ta demande."

    def _trim(self):
        if len(self.history) <= config.MAX_HISTORY + 1:
            return
        cut = len(self.history) - config.MAX_HISTORY
        while cut < len(self.history) and self.history[cut]["role"] != "user":
            cut += 1
        if cut < len(self.history):
            self.history = self.history[:1] + self.history[cut:]
