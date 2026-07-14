"""
Pipeline complet : transcript Teams -> fiche de réunion.

Deux modes d'exécution :

  1) Mode DEMO (par défaut, fonctionne ce soir sans accès Graph API) :
        python main.py --demo

  2) Mode RÉEL (une fois le consentement admin Azure AD obtenu) :
        python main.py --organizer-id <objectId ou UPN> --meeting-id <id de la réunion>
"""
import argparse
import os
from datetime import datetime

from transcript_parser import parse_vtt, merge_consecutive_same_speaker, segments_to_plain_transcript, get_participants
from fiche_generator import generate_fiche, fiche_to_markdown
from config import OUTPUT_DIR


def run_demo():
    print("=== Mode DEMO : utilisation du transcript d'exemple ===\n")
    with open("sample_data/sample_transcript.vtt", encoding="utf-8") as f:
        vtt_content = f.read()
    return vtt_content


def run_real(organizer_id: str, meeting_id: str):
    print(f"=== Mode RÉEL : récupération du transcript via Graph API ===")
    print(f"Organisateur : {organizer_id} | Réunion : {meeting_id}\n")
    from graph_client import GraphClient, GraphAuthError

    client = GraphClient()
    try:
        vtt_content = client.get_latest_transcript_for_meeting(organizer_id, meeting_id)
    except GraphAuthError as e:
        print(f"\n❌ Échec d'authentification :\n{e}")
        raise SystemExit(1)
    return vtt_content


def main():
    parser = argparse.ArgumentParser(description="Pipeline transcript Teams -> fiche de réunion")
    parser.add_argument("--demo", action="store_true", help="Utiliser le transcript d'exemple (aucun accès Graph requis)")
    parser.add_argument("--organizer-id", type=str, help="objectId ou UPN de l'organisateur de la réunion")
    parser.add_argument("--meeting-id", type=str, help="ID de la réunion Teams")
    parser.add_argument("--titre", type=str, default="Réunion SGCI", help="Titre de la réunion pour la fiche")
    args = parser.parse_args()

    if args.demo or not (args.organizer_id and args.meeting_id):
        vtt_content = run_demo()
    else:
        vtt_content = run_real(args.organizer_id, args.meeting_id)

    # 1. Parsing du transcript brut
    segments = parse_vtt(vtt_content)
    segments = merge_consecutive_same_speaker(segments)
    participants = get_participants(segments)
    plain_transcript = segments_to_plain_transcript(segments)

    print(f"{len(segments)} tours de parole détectés.")
    print(f"Participants : {participants}\n")
    print("--- Transcript structuré ---")
    print(plain_transcript)
    print()

    # 2. Génération de la fiche via LLM
    print("=== Génération de la fiche de réunion (LLM) ===\n")
    fiche = generate_fiche(plain_transcript, participants, titre_reunion=args.titre)
    markdown = fiche_to_markdown(fiche)

    print(markdown)

    # 3. Sauvegarde
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(OUTPUT_DIR, f"fiche_reunion_{timestamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"\n✅ Fiche sauvegardée : {out_path}")


if __name__ == "__main__":
    main()
