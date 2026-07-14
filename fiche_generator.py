"""
Génère la fiche de réunion structurée (résumé, décisions, actions) à partir
du transcript par locuteur, via un LLM.
"""
import json
import re
from datetime import datetime

from llm_provider import get_llm_provider

SYSTEM_PROMPT = """Tu es un assistant qui rédige des comptes-rendus de réunion professionnels et détaillés pour une banque (SGCI).
Tu reçois un transcript de réunion Teams avec l'indication du locuteur pour chaque prise de parole.

Règles strictes :
- Tu ne dois JAMAIS inventer d'information qui n'est pas dans le transcript.
- Si une information n'est pas claire ou absente (ex. échéance d'une action), indique "non précisé".
- Réponds UNIQUEMENT en JSON valide, sans texte avant ou après, selon le schéma suivant :

{
  "titre_reunion": "string",
  "date": "string",
  "participants": ["string", ...],
  "resume_general": "string (analyse détaillée et complète, plusieurs paragraphes si nécessaire — ne résume pas à l'excès, développe le contexte, les enjeux discutés et les nuances importantes)",
  "sujets_abordes": [
    {
      "sujet": "string",
      "points_cles": ["string", ...],
      "details": "string (paragraphe développé expliquant ce qui a été dit sur ce sujet précisément, qui a dit quoi, et dans quel contexte — pas juste une liste de mots-clés)"
    }
  ],
  "decisions": ["string", ...],
  "actions": [
    {"action": "string", "responsable": "string", "echeance": "string"}
  ],
  "points_de_vigilance": ["string, ... (désaccords, incertitudes, questions restées sans réponse, points à reprendre plus tard)"]
}

Consignes de profondeur :
- Le résumé général doit être substantiel (plusieurs phrases voire plusieurs paragraphes selon la longueur de la réunion), pas une synthèse minimaliste.
- Pour chaque sujet abordé, le champ "details" doit vraiment expliquer le contenu de l'échange, pas juste lister des mots-clés.
- Attribue les propos aux bons locuteurs quand c'est pertinent (ex. "Participant 2 a soulevé que...").
- Ne comble jamais un manque de contenu réel par du remplissage : si le transcript est court ou pauvre en substance, le compte-rendu doit rester honnête sur ce point plutôt que d'exagérer artificiellement.
"""

USER_PROMPT_TEMPLATE = """Voici le transcript de la réunion (format "Locuteur: texte") :

---
{transcript}
---

Participants détectés : {participants}

Génère la fiche de réunion au format JSON défini dans les instructions système."""


def generate_fiche(plain_transcript: str, participants: list, titre_reunion: str = "Réunion Teams") -> dict:
    provider = get_llm_provider()

    user_prompt = USER_PROMPT_TEMPLATE.format(
        transcript=plain_transcript,
        participants=", ".join(participants),
    )

    raw_response = provider.complete(SYSTEM_PROMPT, user_prompt)

    # Nettoyage défensif : certains modèles ajoutent des fences ```json malgré la consigne
    cleaned = re.sub(r"^```json|```$", "", raw_response.strip(), flags=re.MULTILINE).strip()

    try:
        fiche = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Le LLM n'a pas renvoyé un JSON valide : {e}\n--- Réponse brute ---\n{raw_response}"
        )

    fiche.setdefault("titre_reunion", titre_reunion)
    fiche.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
    return fiche


def fiche_to_markdown(fiche: dict) -> str:
    """Convertit la fiche JSON en Markdown lisible, prêt à envoyer par email/Teams ou à stocker."""
    lines = [
        f"# Compte-rendu — {fiche.get('titre_reunion', 'Réunion')}",
        f"**Date :** {fiche.get('date', 'non précisé')}",
        f"**Participants :** {', '.join(fiche.get('participants', []))}",
        "",
        "## Résumé",
        fiche.get("resume_general", ""),
        "",
        "## Sujets abordés",
    ]
    for sujet in fiche.get("sujets_abordes", []):
        lines.append(f"### {sujet.get('sujet', '')}")
        for point in sujet.get("points_cles", []):
            lines.append(f"- {point}")
        if sujet.get("details"):
            lines.append("")
            lines.append(sujet["details"])
        lines.append("")
    lines.append("## Décisions")
    for d in fiche.get("decisions", []):
        lines.append(f"- {d}")
    lines.append("")
    lines.append("## Actions")
    lines.append("| Action | Responsable | Échéance |")
    lines.append("|---|---|---|")
    for a in fiche.get("actions", []):
        lines.append(f"| {a.get('action', '')} | {a.get('responsable', '')} | {a.get('echeance', '')} |")

    if fiche.get("points_de_vigilance"):
        lines.append("")
        lines.append("## Points de vigilance")
        for p in fiche["points_de_vigilance"]:
            lines.append(f"- {p}")

    return "\n".join(lines)
