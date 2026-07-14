"""
Couche d'abstraction du fournisseur LLM.

Reprend le même principe que ton architecture de la plateforme de formation :
un provider interchangeable, pour ne pas dépendre d'un seul fournisseur
(ex. bascule OpenAI -> Groq que tu avais déjà faite sur l'autre projet).
"""
from abc import ABC, abstractmethod
from config import LLM_CONFIG


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        ...


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        from groq import Groq  # pip install groq
        self.client = Groq(api_key=api_key)
        self.model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=4096,  # fiche détaillée = besoin de plus de place que le défaut
        )
        return response.choices[0].message.content


class OllamaProvider(LLMProvider):
    """Alternative 100% locale/on-premise, pour ne rien envoyer à l'extérieur du réseau SGCI."""
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        import requests
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.2},
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def get_llm_provider() -> LLMProvider:
    if LLM_CONFIG.provider == "groq":
        return GroqProvider(api_key=LLM_CONFIG.api_key, model=LLM_CONFIG.model)
    elif LLM_CONFIG.provider == "ollama":
        return OllamaProvider(base_url=LLM_CONFIG.ollama_base_url, model=LLM_CONFIG.model)
    else:
        raise ValueError(f"Provider LLM non supporté : {LLM_CONFIG.provider}")
