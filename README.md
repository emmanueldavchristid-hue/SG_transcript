# SGCI Teams Transcript — Pipeline transcript → fiche de réunion

## Ce que fait ce projet

1. Récupère le transcript d'une réunion Teams 
2. Parse le transcript WebVTT en tours de parole structurés par locuteur
3. Génère automatiquement une fiche de réunion (résumé, sujets, décisions, actions) via un LLM
4. Sauvegarde la fiche en Markdown dans `output/`

## Installation

```bash
python3 -m venv venv
source venv/bin/activate   # ou venv\Scripts\activate sous Windows
pip install -r requirements.txt
cp .env.example .env
```

Puis remplir `.env` avec au minimum `GROQ_API_KEY` (récupérable sur console.groq.com,
gratuit) .

## Test (mode démo, sans accès Graph)

```bash
python main.py --demo
```

Ça fait tourner tout le pipeline sur `sample_data/sample_transcript.vtt` et produit
une vraie fiche de réunion dans `output/`. C'est ce mode qui te permet de valider
l'ensemble de la logique (parsing + prompt + génération) sans dépendre de l'IT.

## Structure du projet

```
config.py             # configuration centralisée (variables d'environnement)
graph_client.py        # authentification + appels Microsoft Graph API
transcript_parser.py   # parsing WebVTT -> segments structurés par locuteur
llm_provider.py         # abstraction du fournisseur LLM (Groq / Ollama)
fiche_generator.py      # génération de la fiche de réunion via LLM
main.py                 # orchestration bout-en-bout (CLI)
sample_data/            # transcript d'exemple pour tester sans accès Graph
output/                 # fiches générées (créé automatiquement)
```

## Passer en mode 100% local (données sensibles, pas d'appel externe)

Dans `.env` :
```
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1:8b        # ou un autre modèle installé localement
OLLAMA_BASE_URL=http://localhost:11434
```
Nécessite [Ollama](https://ollama.com) installé et le modèle téléchargé
(`ollama pull llama3.1:8b`). Dans ce mode, rien ne sort du poste/réseau interne —
recommandé pour la version qui ira en production sur des données réelles SGCI.

## Mode LOCAL (recommandé — aucun accès Graph API requis)

Capture directement le micro + la sortie audio de l'ordinateur pendant la réunion,
sans dépendre d'un consentement admin Microsoft.

### Limite à connaître
La sortie audio système mixe **tous** les participants distants en un seul flux
(c'est Teams qui fait ce mixage avant que le son sorte de tes enceintes). On ne peut
donc pas savoir "qui" parle parmi les autres sans une étape de diarisation (reconnaissance
de "voix différente", pas de nom). C'est fait avec `pyannote.audio` — efficace mais jamais
garanti à 100%, surtout si plusieurs personnes parlent en même temps.

### Setup
```bash
pip install -r requirements.txt
```
Pour la diarisation (`pyannote.audio`) :
1. Créer un compte gratuit sur https://huggingface.co
2. Accepter les conditions d'usage du modèle `pyannote/speaker-diarization-3.1`
3. Générer un token d'accès (Settings > Access Tokens) et le mettre dans `.env` sous `HF_TOKEN`
   (ou le passer en `--hf-token` en ligne de commande)

### Utilisation

**Étape 1 — pendant la réunion**, dans un terminal laissé ouvert :
```bash
python local_capture.py --duration 1800   # 30 min ; ou sans --duration + Ctrl+C pour arrêter manuellement
```
Ça produit `sample_data/mic.wav` (ta voix) et `sample_data/system.wav` (les autres).

**Étape 2 — après la réunion :**
```bash
python main_local.py --mic sample_data/mic.wav --system sample_data/system.wav --titre "Point hebdo" --mon-nom "Christ-Emmanuel"
```
Ça transcrit, diarise, fusionne chronologiquement, génère la fiche et la sauvegarde
dans `output/`.

### Pourquoi ce mode plutôt que Graph API
- Zéro dépendance IT/admin, tu peux l'utiliser dès aujourd'hui
- 100% local jusqu'à l'appel LLM final (bascule sur `LLM_PROVIDER=ollama` pour du 100%
  local de bout en bout, cf. section suivante)
- Fonctionne aussi pour des appels hors Teams (Zoom, Google Meet, appel téléphonique
  sur l'ordi...) puisqu'il capture juste le son de la machine

### Limites honnêtes à garder en tête
- Diarisation imparfaite sur voix très proches ou fort brouhaha/coupures de parole
- Pas de vrais noms sur les autres participants (juste "Participant 1", "Participant 2"...)
  sauf si tu les renseignes manuellement après coup
- Nécessite d'informer les autres participants qu'ils sont enregistrés (même obligation
  légale que pour la transcription Teams native)
- Modèle Whisper "medium" = bon compromis précision/vitesse sur CPU ; passer à "small"
  si le PC rame, "large-v3" si tu as un GPU et veux le maximum de précision

## Prochaines étapes 

- [ ] Obtenir l'accès Graph API (App Registration + consentement admin)
- [ ] Tester sur une vraie réunion Teams SGCI
- [ ] Ajouter la détection automatique des nouvelles réunions terminées (webhook Graph
      `subscriptions` sur la ressource `transcripts`, plutôt qu'un lancement manuel)
- [ ] Décider du canal de diffusion de la fiche (email auto, message Teams, dépôt SharePoint)
- [ ] Valider avec la conformité si Groq (externe) est acceptable, ou basculer sur Ollama local
