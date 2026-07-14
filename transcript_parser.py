"""
Parseur de transcript WebVTT (format renvoyé par Microsoft Graph pour les réunions Teams).

Format d'entrée typique (WebVTT avec voice tags) :

    WEBVTT

    00:00:01.000 --> 00:00:04.500
    <v Christ-Emmanuel Mouhi>Bonjour à tous, on démarre la réunion.</v>

    00:00:05.000 --> 00:00:09.200
    <v Fatou Diabaté>Oui bonjour, j'ai le point budget à présenter.</v>

Ce module transforme ça en une liste structurée exploitable par le générateur de fiche.
"""
import re
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class TranscriptSegment:
    speaker: str
    text: str
    start: str
    end: str

    def to_dict(self):
        return asdict(self)


VTT_CUE_TIME_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
)
VOICE_TAG_RE = re.compile(r"<v\s+([^>]+)>(.*?)(</v>)?$", re.DOTALL)


def parse_vtt(vtt_content: str) -> List[TranscriptSegment]:
    """
    Parse un contenu WebVTT complet et retourne la liste des segments par locuteur,
    dans l'ordre chronologique.
    """
    segments = []
    blocks = re.split(r"\n\s*\n", vtt_content.strip())

    current_time = None
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines or lines[0].upper().startswith("WEBVTT"):
            continue

        # certains blocs commencent par un numéro de cue optionnel, on l'ignore
        text_lines = []
        for line in lines:
            time_match = VTT_CUE_TIME_RE.search(line)
            if time_match:
                current_time = (time_match.group(1), time_match.group(2))
            else:
                text_lines.append(line)

        if not current_time or not text_lines:
            continue

        full_text = " ".join(text_lines)
        voice_match = VOICE_TAG_RE.search(full_text)
        if voice_match:
            speaker = voice_match.group(1).strip()
            text = voice_match.group(2).strip()
        else:
            # pas de tag <v> (attribution du locuteur désactivée côté tenant)
            speaker = "Inconnu"
            text = full_text

        segments.append(
            TranscriptSegment(speaker=speaker, text=text, start=current_time[0], end=current_time[1])
        )
        current_time = None

    return segments


def merge_consecutive_same_speaker(segments: List[TranscriptSegment]) -> List[TranscriptSegment]:
    """
    Fusionne les segments consécutifs d'un même locuteur pour produire
    des tours de parole plus lisibles (moins de fragmentation), utile avant
    d'envoyer le transcript au LLM (réduit le nombre de tokens et le bruit).
    """
    if not segments:
        return []

    merged = [segments[0]]
    for seg in segments[1:]:
        last = merged[-1]
        if seg.speaker == last.speaker:
            last.text = f"{last.text} {seg.text}"
            last.end = seg.end
        else:
            merged.append(seg)
    return merged


def segments_to_plain_transcript(segments: List[TranscriptSegment]) -> str:
    """Transforme la liste de segments en texte simple 'Locuteur: texte', prêt pour le prompt LLM."""
    return "\n".join(f"{seg.speaker}: {seg.text}" for seg in segments)


def get_participants(segments: List[TranscriptSegment]) -> List[str]:
    """Liste unique des participants ayant pris la parole, dans l'ordre d'apparition."""
    seen = []
    for seg in segments:
        if seg.speaker not in seen:
            seen.append(seg.speaker)
    return seen


if __name__ == "__main__":
    with open("sample_data/sample_transcript.vtt", encoding="utf-8") as f:
        raw = f.read()

    segs = parse_vtt(raw)
    segs = merge_consecutive_same_speaker(segs)

    print(f"{len(segs)} tours de parole détectés.")
    print(f"Participants : {get_participants(segs)}\n")
    print(segments_to_plain_transcript(segs))
