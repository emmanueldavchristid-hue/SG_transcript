"""
Pipeline 100% local : capture audio -> transcription + diarisation -> fiche de réunion.
Aucun accès Graph API / admin Azure AD requis.

Usage typique :

  # 1. Pendant la réunion, dans un terminal :
  python local_capture.py --duration 1800

  # 2. Après la réunion :
  python main_local.py --mic sample_data/mic.wav --system sample_data/system.wav --titre "Point hebdo"
"""
import argparse
import os
from datetime import datetime

from transcribe_diarize import transcribe_single_speaker, transcribe_and_diarize, merge_by_time
from transcript_parser import segments_to_plain_transcript, get_participants
from fiche_generator import generate_fiche, fiche_to_markdown
from config import OUTPUT_DIR


def main():
    parser = argparse.ArgumentParser(description="Pipeline local : audio réunion -> fiche")
    parser.add_argument("--mic", type=str, required=True, help="Chemin du fichier audio micro (ta voix)")
    parser.add_argument("--system", type=str, required=True, help="Chemin du fichier audio système (les autres)")
    parser.add_argument("--titre", type=str, default="Réunion", help="Titre de la réunion pour la fiche")
    parser.add_argument("--mon-nom", type=str, default="Moi", help="Comment t'étiqueter dans la fiche")
    parser.add_argument("--hf-token", type=str, default=os.getenv("HF_TOKEN", ""), help="Token HuggingFace pour pyannote (diarisation)")
    parser.add_argument("--num-speakers", type=int, default=None, help="Nombre exact de participants distants connu à l'avance (améliore la précision)")
    parser.add_argument("--min-speakers", type=int, default=None, help="Nombre minimum de participants distants (si le nombre exact est inconnu)")
    parser.add_argument("--max-speakers", type=int, default=None, help="Nombre maximum de participants distants (si le nombre exact est inconnu)")
    args = parser.parse_args()

    print("=== Transcription de ta piste micro ===")
    mic_segments = transcribe_single_speaker(args.mic, speaker_label=args.mon_nom)
    print(f"{len(mic_segments)} segments transcrits.\n")

    print("=== Transcription + diarisation de la piste système (les autres participants) ===")
    if not args.hf_token:
        print(
            "⚠️  Pas de token HuggingFace fourni (--hf-token ou variable HF_TOKEN) : "
            "la diarisation ne peut pas distinguer les voix. Transcription en un seul bloc "
            "étiqueté 'Autres participants'.\n"
        )
        system_segments = transcribe_single_speaker(args.system, speaker_label="Autres participants")
    else:
        system_segments = transcribe_and_diarize(
            args.system,
            hf_token=args.hf_token,
            num_speakers=args.num_speakers,
            min_speakers=args.min_speakers,
            max_speakers=args.max_speakers,
        )
    print(f"{len(system_segments)} segments transcrits.\n")

    # Fusion chronologique des deux pistes
    all_segments = merge_by_time(mic_segments, system_segments)
    participants = get_participants(all_segments)
    plain_transcript = segments_to_plain_transcript(all_segments)

    print("--- Transcript fusionné ---")
    print(plain_transcript)
    print()

    print("=== Génération de la fiche de réunion (LLM) ===\n")
    fiche = generate_fiche(plain_transcript, participants, titre_reunion=args.titre)
    markdown = fiche_to_markdown(fiche)
    print(markdown)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(OUTPUT_DIR, f"fiche_locale_{timestamp}.md")

    full_output = (
        f"{markdown}\n\n"
        f"---\n\n"
        f"## 🗣️ Transcript brut (qui a dit quoi)\n\n"
        f"```\n{plain_transcript}\n```\n"
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_output)
    print(f"\n✅ Fiche sauvegardée : {out_path}")


if __name__ == "__main__":
    main()
