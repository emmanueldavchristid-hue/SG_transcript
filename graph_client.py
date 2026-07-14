"""
Client Microsoft Graph API.

Responsabilités :
  1. S'authentifier en tant qu'application (client credentials flow, via MSAL)
  2. Lister les réunions en ligne d'un organisateur (optionnel, pour automatiser)
  3. Récupérer le transcript brut (WebVTT) d'une réunion donnée via callTranscript

Pré-requis côté Azure AD (à demander à l'admin M365 de SGCI) :
  - App Registration avec les "Application permissions" suivantes, consenties par un admin :
        OnlineMeetingTranscript.Read.All
        OnlineMeetings.Read.All
  - Un client secret (ou certificat) généré pour cette App Registration
  - La transcription native Teams doit être activée dans les politiques de réunion du tenant

Tant que le consentement admin n'est pas accordé, get_transcript() renverra une erreur
403/401 explicite — c'est attendu, ce n'est pas un bug du code.
"""
import logging
import requests
import msal

from config import AZURE_CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("graph_client")

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_BETA_URL = "https://graph.microsoft.com/beta"  # certains endpoints transcript sont encore en beta


class GraphAuthError(Exception):
    pass


class GraphClient:
    def __init__(self, config=AZURE_CONFIG):
        self.config = config
        self._app = msal.ConfidentialClientApplication(
            client_id=self.config.client_id,
            client_credential=self.config.client_secret,
            authority=self.config.authority,
        )
        self._token = None

    def _get_token(self) -> str:
        """Récupère (ou renouvelle) un token d'accès application."""
        result = self._app.acquire_token_silent(self.config.scope, account=None)
        if not result:
            logger.info("Aucun token en cache, demande d'un nouveau token...")
            result = self._app.acquire_token_for_client(scopes=self.config.scope)

        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "erreur inconnue"))
            raise GraphAuthError(
                f"Échec d'authentification Graph API : {error}\n"
                "→ Vérifier que le consentement admin a bien été accordé pour les permissions "
                "OnlineMeetingTranscript.Read.All et OnlineMeetings.Read.All."
            )
        self._token = result["access_token"]
        return self._token

    def _headers(self) -> dict:
        token = self._token or self._get_token()
        return {"Authorization": f"Bearer {token}"}

    def list_online_meetings(self, organizer_user_id: str, limit: int = 10) -> list:
        """
        Liste les réunions en ligne récentes d'un organisateur donné.
        organizer_user_id : l'objectId (GUID) ou l'UPN (email) de l'utilisateur Teams organisateur.
        """
        url = f"{GRAPH_BASE_URL}/users/{organizer_user_id}/onlineMeetings"
        resp = requests.get(url, headers=self._headers(), params={"$top": limit})
        resp.raise_for_status()
        return resp.json().get("value", [])

    def list_transcripts(self, organizer_user_id: str, meeting_id: str) -> list:
        """Liste les transcripts disponibles pour une réunion (une réunion peut en avoir plusieurs si redémarrée)."""
        url = f"{GRAPH_BASE_URL}/users/{organizer_user_id}/onlineMeetings/{meeting_id}/transcripts"
        resp = requests.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json().get("value", [])

    def get_transcript_content(self, organizer_user_id: str, meeting_id: str, transcript_id: str) -> str:
        """
        Récupère le contenu brut du transcript au format WebVTT
        (avec attribution du locuteur si activée dans les politiques du tenant).
        """
        url = (
            f"{GRAPH_BASE_URL}/users/{organizer_user_id}/onlineMeetings/"
            f"{meeting_id}/transcripts/{transcript_id}/content"
        )
        headers = self._headers()
        headers["Accept"] = "text/vtt"
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text

    def get_latest_transcript_for_meeting(self, organizer_user_id: str, meeting_id: str) -> str:
        """Raccourci : récupère directement le contenu du transcript le plus récent d'une réunion."""
        transcripts = self.list_transcripts(organizer_user_id, meeting_id)
        if not transcripts:
            raise ValueError("Aucun transcript disponible pour cette réunion (transcription non activée ou pas encore générée).")
        latest = sorted(transcripts, key=lambda t: t.get("createdDateTime", ""))[-1]
        return self.get_transcript_content(organizer_user_id, meeting_id, latest["id"])


if __name__ == "__main__":
    # Test manuel rapide (nécessite les variables d'environnement configurées)
    client = GraphClient()
    try:
        token = client._get_token()
        print("Authentification réussie, token obtenu.")
    except GraphAuthError as e:
        print(f"Échec attendu tant que le consentement admin n'est pas accordé :\n{e}")
