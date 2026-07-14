"""
Configuration centralisée du projet.
Toutes les valeurs sensibles viennent de variables d'environnement (.env),
jamais en dur dans le code.
"""
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optionnel si les variables sont déjà exportées dans l'environnement


@dataclass
class AzureADConfig:
    """
    Ces valeurs sont fournies par l'admin M365/Azure AD de SGCI
    après création de l'App Registration.
    Permissions Graph API nécessaires (application permissions, avec consentement admin) :
      - OnlineMeetingTranscript.Read.All
      - OnlineMeetings.Read.All
      - Calendars.Read (si on veut lister automatiquement les réunions)
    """
    tenant_id: str = os.getenv("AZURE_TENANT_ID", "")
    client_id: str = os.getenv("AZURE_CLIENT_ID", "")
    client_secret: str = os.getenv("AZURE_CLIENT_SECRET", "")
    authority: str = None
    scope: list = None

    def __post_init__(self):
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        # Pour les application permissions (pas de user interactif), on utilise le scope .default
        self.scope = ["https://graph.microsoft.com/.default"]


@dataclass
class LLMConfig:
    """
    Configuration du fournisseur LLM utilisé pour générer la fiche de réunion.
    Groq est utilisé par défaut (cohérent avec le reste du stack SGCI),
    mais le provider est interchangeable (cf. llm_provider.py).
    """
    provider: str = os.getenv("LLM_PROVIDER", "groq")  # "groq" | "ollama" | "azure_openai"
    api_key: str = os.getenv("GROQ_API_KEY", "")
    model: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


AZURE_CONFIG = AzureADConfig()
LLM_CONFIG = LLMConfig()

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
