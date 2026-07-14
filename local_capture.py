"""
Capture audio locale en parallèle :
  - le micro (ta voix)
  - la sortie audio système / "loopback" (ce que tu entends = les autres participants,
    mixés ensemble par Teams)

Fonctionne sans logiciel tiers (pas de câble audio virtuel nécessaire) grâce à la
librairie `soundcard`, qui expose la capture loopback nativement sur Windows/macOS/Linux.

Usage :
    python local_capture.py --duration 1800     # enregistre 30 min
    python local_capture.py                      # enregistre jusqu'à Ctrl+C
"""
import argparse
import threading
import time
import numpy as np
import soundcard as sc
import soundfile as sf

SAMPLE_RATE = 16000  # 16kHz suffit largement pour la voix, et c'est ce qu'attend Whisper
CHANNELS = 1


def _record_to_file(recorder, filepath: str, stop_event: threading.Event, chunk_seconds: float = 0.5):
    """Enregistre en continu depuis un `recorder` soundcard jusqu'à ce que stop_event soit levé."""
    frames = []
    chunk_size = int(SAMPLE_RATE * chunk_seconds)
    with recorder.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as rec:
        while not stop_event.is_set():
            data = rec.record(numframes=chunk_size)
            frames.append(data)
    if frames:
        audio = np.concatenate(frames, axis=0)
        sf.write(filepath, audio, SAMPLE_RATE)
        print(f"✅ Enregistrement sauvegardé : {filepath} ({len(audio) / SAMPLE_RATE:.1f}s)")
    else:
        print(f"⚠️ Aucune donnée capturée pour {filepath}")


def record_meeting(mic_out: str = "mic.wav", system_out: str = "system.wav", duration: float = None):
    """
    Lance l'enregistrement simultané du micro et de la sortie audio système.
    Si `duration` (en secondes) est fourni, s'arrête automatiquement.
    Sinon, s'arrête sur Ctrl+C.
    """
    default_speaker = sc.default_speaker()
    default_mic = sc.default_microphone()

    # Le micro "loopback" du haut-parleur par défaut capture tout ce qui sort des enceintes/casque
    loopback_mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)

    print(f"🎙️  Micro utilisé      : {default_mic.name}")
    print(f"🔊 Sortie capturée    : {default_speaker.name} (loopback)")
    print("Enregistrement en cours... (Ctrl+C pour arrêter)\n")

    stop_event = threading.Event()

    t_mic = threading.Thread(target=_record_to_file, args=(default_mic, mic_out, stop_event))
    t_sys = threading.Thread(target=_record_to_file, args=(loopback_mic, system_out, stop_event))
    t_mic.start()
    t_sys.start()

    start_time = time.time()
    try:
        if duration:
            while time.time() - start_time < duration:
                time.sleep(0.5)
            stop_event.set()
        else:
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n⏹️  Arrêt demandé, finalisation de l'enregistrement...")
        stop_event.set()

    t_mic.join()
    t_sys.join()
    print("\n✅ Capture terminée.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture audio locale (micro + sortie système) pour une réunion")
    parser.add_argument("--duration", type=float, default=None, help="Durée en secondes (sinon Ctrl+C pour arrêter)")
    parser.add_argument("--mic-out", type=str, default="sample_data/mic.wav")
    parser.add_argument("--system-out", type=str, default="sample_data/system.wav")
    args = parser.parse_args()

    record_meeting(mic_out=args.mic_out, system_out=args.system_out, duration=args.duration)
