# Mini-banc de caractérisation caméra (GStreamer + Python)

Ce banc est la première brique d'un outil de caractérisation de caméra, construit comme on caractérise une charge utile optronique de drone :

- **Windows joue le drone** : il capture la webcam et l'envoie en H.264 sur RTP/UDP.
- **WSL joue la station sol** : il reçoit le flux, le décode et fait les mesures en Python.

Le module réalisé caractérise **la chaîne vidéo elle-même** (cadence réelle, gigue, images perdues). C'est la mesure à faire en premier : si la chaîne est irrégulière, toutes les autres mesures sont faussées. Les résultats sont rassemblés automatiquement dans une **fiche caméra**.

## Installation (une fois, dans WSL)

```bash
cd ~/banc_cam
bash installer.sh
```

GStreamer doit aussi être installé **côté Windows**, en mode « Complete », dans `C:\Program Files\gstreamer`.

## Utilisation : deux terminaux WSL, dans le dossier `banc_cam`

| Terminal 1 : émetteur | Terminal 2 : mesure |
| --- | --- |
| `./emetteur/lancer_emetteur.sh` (webcam, 1280x720, 3000 kbit/s) | `python3 -m module1_chaine.test_chaine --duree 30 --etiquette standard_3000k` |
| `./emetteur/emetteur_test.sh` (mire, sans caméra) | même commande, pour tester sans caméra |

Ensuite, pour générer la fiche : `python3 -m synthese.fiche_camera --camera "Ma webcam"`, qui produit `resultats/fiche_camera.md`.

Chaque script affiche son aide avec `--help`.

## Ce que le module 1 mesure

- **Cadence réelle** (images/s) : à comparer aux 30 i/s nominaux.
- **Gigue** : écart-type de l'intervalle entre deux images reçues.
- **Images perdues** : intervalles anormalement longs.
- **Luminosité et contraste de chaque image** : pour relier une chute de cadence à l'exposition automatique.

Premier résultat observé : dans le noir, la webcam passe de 30 à 15 i/s. Son exposition automatique allonge le temps de pose au-delà d'une période image, puis monte le gain jusqu'à un plancher d'environ 51 niveaux de gris.

## Pistes d'étude

L'architecture (brique de réception commune, un module par mesure, résumés JSON assemblés dans la fiche) est prévue pour accueillir d'autres mesures :

| Piste | Question | Méthode envisagée |
| --- | --- | --- |
| Débit / qualité | Que fait la compression H.264 à l'image ? | Rejouer une séquence de référence dans GStreamer (`appsrc`) à plusieurs débits, mesurer PSNR et SSIM, et le débit réel avec une sonde sur le pad de l'encodeur. |
| Bruit capteur | Quel est le bruit temporel, le bruit spatial fixe, le SNR ? | Scène immobile, flux sans perte, variance temporelle par pixel ; courbe de transfert variance/signal inspirée de la norme EMVA 1288. Méthode à valider d'abord sur une caméra simulée au bruit connu. |
| Latence glass-to-glass | Combien de temps entre un événement et son affichage côté sol ? | Mire qui alterne noir et blanc, filmée par la caméra, détection de la bascule dans le flux reçu, avec la même horloge ; distribution sur une centaine de mesures. |
| Étalonnage géométrique | Focale, centre optique, distorsion, champ de vision ? | Mire damier sous plusieurs angles, méthode de Zhang (`cv2.calibrateCamera`), erreur de reprojection. |
| Stabilité / vibrations | De combien l'image bouge-t-elle, à quelle fréquence ? | Corrélation de phase entre images, spectre du déplacement ; conversion en mrad grâce à l'étalonnage ; limite de Nyquist à 15 Hz pour 30 i/s. |

L'émetteur propose déjà un profil `sans_perte` (`./emetteur/lancer_emetteur.sh sans_perte`), nécessaire pour les pistes bruit et qualité.

## Structure

- `config.py` : réglages partagés (port, caps RTP, dossiers).
- `commun/recepteur.py` : flux RTP/H.264 → images NumPy horodatées. C'est la brique réutilisable par toutes les mesures.
- `commun/resultats.py` : écrit et relit les `resume_*.json` qui alimentent la fiche caméra.
- `emetteur/` : l'émetteur webcam (Windows, lancé depuis WSL) et un émetteur de mire pour tester sans caméra.
- `module1_chaine/` : la mesure de la chaîne vidéo.
- `synthese/fiche_camera.py` : assemble la fiche caméra.
