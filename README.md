# Mini-banc de caractérisation caméra (GStreamer + Python)

Ce banc caractérise une webcam de la même façon qu'on caractérise une charge utile optronique : latence, géométrie, qualité vidéo, bruit, stabilité. À la fin, il produit une **fiche caméra** qui rassemble les résultats.

- **Windows joue le drone** : il capture la webcam et l'envoie en H.264 sur RTP/UDP.
- **WSL joue la station sol** : il reçoit le flux, le décode et fait les mesures en Python.

La feuille de route détaillée (étapes, liens entre modules, explications) est dans le doc qui accompagne ce projet.

## Installation (une fois, dans WSL)

```bash
cd ~/banc_cam
bash installer.sh
```

GStreamer doit aussi être installé **côté Windows**, en mode « Complete », dans `C:\Program Files\gstreamer`.

## Utilisation : toujours deux terminaux WSL, dans le dossier `banc_cam`

| Terminal 1 : émetteur | Terminal 2 : mesure |
| --- | --- |
| `./emetteur/lancer_emetteur.sh` (webcam, 1280x720, 3000 kbit/s) | `python3 -m module0_chaine.test_chaine` |
| `./emetteur/emetteur_test.sh` (mire, sans caméra) | n'importe quel module, pour tester |
| `./emetteur/lancer_emetteur.sh sans_perte` | modules 3 et 4 |
| `python3 -m emetteur.camera_virtuelle` (bruit connu) | validation du module 4 |

| Module | Commandes | Produit |
| --- | --- | --- |
| 0 Chaîne | `python3 -m module0_chaine.test_chaine --etiquette standard` | cadence, gigue, pertes |
| 1 Latence | `python3 -m module1_latence.mesure_latence --etiquette standard_3000k` puis `python3 -m module1_latence.analyse_latence` | distribution des latences |
| 2 Étalonnage | `generer_damier`, `valider_synthetique`, `capture_damier`, `etalonnage` | focale, distorsion, FOV → `etalonnage.json` |
| 3 Débit/qualité | `enregistre_reference` puis `debit_qualite` | courbe PSNR/SSIM selon le débit |
| 4 Bruit | `mesure_bruit --etiquette noir`, `mesure_bruit --etiquette mire --mire`, puis `courbe_transfert` | bruit temporel, FPN, courbe de transfert |
| 5 Vibrations | `mesure_vibrations --etiquette repos`, puis `--etiquette tapotement` | déplacement (px, mrad), spectre |
| Synthèse | `python3 -m synthese.fiche_camera --camera "Ma webcam"` | `resultats/fiche_camera.md` |

Tous les résultats sont écrits dans `resultats/<module>/`. Chaque script affiche son aide avec `--help`.

## Structure

- `config.py` : réglages partagés (port, caps RTP, dossiers).
- `commun/recepteur.py` : flux RTP/H.264 → images NumPy horodatées. C'est la brique utilisée par tous les modules.
- `commun/resultats.py` : écrit et relit les `resume_*.json` qui relient les modules à la fiche caméra.
