# Mini-banc de caractérisation caméra (GStreamer + Python)

Ce banc caractérise une webcam comme on caractérise une charge utile optronique, en trois étapes qui s'enchaînent :

1. **Chaîne vidéo** : le flux arrive-t-il correctement (cadence, gigue, pertes) ?
2. **Débit / qualité** : que fait la compression H.264 à l'image ?
3. **Bruit** : quel est le bruit du capteur, mesuré en évitant justement cette compression ?

À la fin, il produit une **fiche caméra** qui rassemble les résultats. Aucun accessoire n'est nécessaire : ni impression, ni miroir.

- **Windows joue le drone** : il capture la webcam et l'envoie en H.264 sur RTP/UDP.
- **WSL joue la station sol** : il reçoit le flux, le décode et fait les mesures en Python.

## Installation (une fois, dans WSL)

```bash
cd ~/banc_cam
bash installer.sh
```

GStreamer doit aussi être installé **côté Windows**, en mode « Complete », dans `C:\Program Files\gstreamer`.

## Utilisation : toujours deux terminaux WSL, dans le dossier `banc_cam`

| Terminal 1 : émetteur | Terminal 2 : mesure |
| --- | --- |
| `./emetteur/lancer_emetteur.sh` (webcam, 1280x720, 3000 kbit/s) | module 1 |
| `./emetteur/lancer_emetteur.sh sans_perte` (webcam, 640x480, sans compression destructrice) | modules 2 et 3 |
| `./emetteur/emetteur_test.sh` (mire, sans caméra) | n'importe quel module, pour tester |
| `python3 -m emetteur.camera_virtuelle` (caméra simulée, bruit connu) | validation du module 3 |

| Module | Commandes | Produit |
| --- | --- | --- |
| 1 · Chaîne vidéo | `python3 -m module1_chaine.test_chaine --etiquette standard` | cadence, gigue, pertes |
| 2 · Débit / qualité | `python3 -m module2_debit_qualite.enregistre_reference` puis `python3 -m module2_debit_qualite.debit_qualite` | courbe PSNR/SSIM selon le débit |
| 3 · Bruit | `python3 -m module3_bruit.mesure_bruit --etiquette noir`, `--etiquette scene`, puis `python3 -m module3_bruit.courbe_transfert` | bruit temporel, FPN, courbe de transfert |
| Synthèse | `python3 -m synthese.fiche_camera --camera "Ma webcam"` | `resultats/fiche_camera.md` |

Tous les résultats sont écrits dans `resultats/<module>/`. Chaque script affiche son aide avec `--help`.

## Structure

- `config.py` : réglages partagés (port, caps RTP, dossiers).
- `commun/recepteur.py` : flux RTP/H.264 → images NumPy horodatées. C'est la brique utilisée par tous les modules.
- `commun/resultats.py` : écrit et relit les `resume_*.json` qui relient les modules à la fiche caméra.
