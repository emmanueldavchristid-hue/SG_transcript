"""
Transcription + diarisation des pistes audio capturées.

- Piste "moi.wav" (micro) : un seul locuteur connu -> transcription directe, étiquetée "Moi".
- Piste "system.wav" (sortie audio = les autres participants, mixés) : plusieurs locuteurs
  potentiels -> diarisation (pyannote.audio) pour distinguer "Speaker 1", "Speaker 2", etc.,
  puis transcription (faster-whisper) segment par segment.

Prérequis pyannote : un token HuggingFace (gratuit) et l'acceptation des conditions d'usage
du modèle "pyannote/speaker-diarization-3.1" sur huggingface.co avant la première utilisation.
"""
import os
from typing import List

import torch
import soundfile as sf
from faster_whisper import WhisperModel
from transcript_parser import TranscriptSegment

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "large-v3")  # meilleure précision Whisper disponible
WHISPER_LANGUAGE = "fr"

_whisper_model = None


def _get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        # compute_type="int8" = beaucoup plus rapide sur CPU, léger compromis sur la précision
        _whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="auto", compute_type="int8")
    return _whisper_model


def _seconds_to_vtt_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


_HALLUCINATION_PATTERNS = [
    "sous-titrage société radio-canada",
    "sous-titrage st",
    "sous-titres réalisés",
    "sous-titrage fr",
    "amara.org",
    "merci d'avoir regardé",
    "merci d'avoir regardé cette vidéo",
    "abonnez-vous",
    "à bientôt pour une nouvelle vidéo",
]


def _is_hallucination(text: str) -> bool:
    """Détecte les phrases-types que Whisper hallucine classiquement sur du silence/bruit de fond."""
    normalized = text.strip().lower()
    return any(pattern in normalized for pattern in _HALLUCINATION_PATTERNS)


def transcribe_single_speaker(audio_path: str, speaker_label: str) -> List[TranscriptSegment]:
    """Transcrit une piste audio mono-locuteur (ex. le micro) et étiquette tous les segments avec speaker_label."""
    model = _get_whisper_model()
    segments, _ = model.transcribe(
        audio_path,
        language=WHISPER_LANGUAGE,
        vad_filter=True,
        condition_on_previous_text=False,  # réduit le risque de boucle/hallucination sur silence
    )

    result = []
    for seg in segments:
        text = seg.text.strip()
        if not text or _is_hallucination(text):
            continue
        result.append(
            TranscriptSegment(
                speaker=speaker_label,
                text=text,
                start=_seconds_to_vtt_timestamp(seg.start),
                end=_seconds_to_vtt_timestamp(seg.end),
            )
        )
    return result


def _load_waveform_for_pyannote(audio_path: str) -> dict:
    """
    Charge l'audio via soundfile (pas de dépendance à FFmpeg/torchcodec) et le convertit
    au format attendu par pyannote : {'waveform': (channel, time) torch.Tensor, 'sample_rate': int}.
    Contourne le bug d'installation torchcodec fréquent sous Windows.
    """
    data, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
    waveform = torch.from_numpy(data.T)  # soundfile renvoie (time, channel) -> pyannote veut (channel, time)
    return {"waveform": waveform, "sample_rate": sample_rate}


def transcribe_and_diarize(
    audio_path: str,
    hf_token: str,
    speaker_prefix: str = "Participant",
    num_speakers: int = None,
    min_speakers: int = None,
    max_speakers: int = None,
) -> List[TranscriptSegment]:
    """
    Transcrit une piste audio multi-locuteurs (ex. la sortie système) en distinguant
    les différentes voix via diarisation (pyannote), puis transcrit chaque segment (faster-whisper).

    Les locuteurs sont étiquetés de façon générique ("Participant 1", "Participant 2"...)
    car la diarisation ne connaît pas les noms — seulement "voix différente".

    Si le nombre de participants réels est connu à l'avance (ex. 5 personnes en réunion),
    le renseigner via num_speakers améliore significativement la précision — sans cette info,
    l'algorithme doit deviner combien de locuteurs distincts sont présents, ce qui est une
    source d'erreur fréquente (fusion de deux voix proches, ou au contraire scission d'une
    même voix en deux locuteurs différents).
    """
    from pyannote.audio import Pipeline

    diarization_pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", token=hf_token
    )

    diarize_kwargs = {}
    if num_speakers is not None:
        diarize_kwargs["num_speakers"] = num_speakers
    else:
        if min_speakers is not None:
            diarize_kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            diarize_kwargs["max_speakers"] = max_speakers

    diarization = diarization_pipeline(_load_waveform_for_pyannote(audio_path), **diarize_kwargs)

    # Mapping des labels pyannote (SPEAKER_00, SPEAKER_01...) vers des noms lisibles
    speaker_map = {}

    def readable_label(raw_label: str) -> str:
        if raw_label not in speaker_map:
            speaker_map[raw_label] = f"{speaker_prefix} {len(speaker_map) + 1}"
        return speaker_map[raw_label]

    model = _get_whisper_model()
    result = []

    # pyannote.audio 4.x renvoie un objet DiarizeOutput (.speaker_diarization, paires (turn, speaker)).
    # Les versions 3.x renvoient un objet Annotation classique (.itertracks(yield_label=True), triplets).
    # On gère les deux pour rester robuste aux mises à jour de la librairie.
    if hasattr(diarization, "speaker_diarization"):
        turns_iterable = diarization.speaker_diarization
    else:
        turns_iterable = ((turn, raw_speaker) for turn, _, raw_speaker in diarization.itertracks(yield_label=True))

    for turn, raw_speaker in turns_iterable:
        # On transcrit chaque tour de parole détecté par la diarisation séparément,
        # en restreignant Whisper à cette fenêtre temporelle précise.
        segments, _ = model.transcribe(
            audio_path,
            language=WHISPER_LANGUAGE,
            vad_filter=True,
            clip_timestamps=[turn.start, turn.end],
            condition_on_previous_text=False,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        if not text or _is_hallucination(text):
            continue
        result.append(
            TranscriptSegment(
                speaker=readable_label(raw_speaker),
                text=text,
                start=_seconds_to_vtt_timestamp(turn.start),
                end=_seconds_to_vtt_timestamp(turn.end),
            )
        )
    return result


def merge_by_time(*segment_lists: List[TranscriptSegment]) -> List[TranscriptSegment]:
    """Fusionne plusieurs listes de segments (ex. piste micro + piste système) en une seule chronologie."""
    all_segments = [seg for lst in segment_lists for seg in lst]
    return sorted(all_segments, key=lambda s: s.start)
