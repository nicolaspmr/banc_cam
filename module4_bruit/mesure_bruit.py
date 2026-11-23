"""
module4_bruit/mesure_bruit.py — Bruit temporel, bruit spatial fixe (FPN) et courbe de transfert.

À LANCER AVEC L'ÉMETTEUR EN PROFIL SANS PERTE : ./emetteur/lancer_emetteur.sh sans_perte
(la compression H.264 classique lisse le bruit et fausserait tout).

On enregistre N images d'une scène PARFAITEMENT IMMOBILE (caméra posée, rien ne bouge),
puis pour chaque pixel on calcule sa moyenne et sa variance dans le temps.
  - Bruit temporel : fluctuation d'un pixel d'une image à l'autre (photons, lecture, électronique).
  - FPN (Fixed Pattern Noise) : différence fixe entre pixels voisins (dispersion de fabrication).
  - Courbe de transfert (inspirée de la norme EMVA 1288) : variance temporelle en fonction du
    niveau moyen. Pour un capteur idéal, le bruit photonique suit une loi de Poisson :
    variance (en électrons) = signal (en électrons) -> la courbe est une DROITE dont la pente
    donne le gain de conversion (niveaux numériques par électron).

Astuce pour contourner l'exposition automatique de la webcam : au lieu de faire varier
l'éclairage (l'expo auto compenserait), on filme UNE scène fixe contenant beaucoup de niveaux
de gris (option --mire : une échelle de gris affichée à l'écran, filmée via le miroir),
et on regroupe les pixels par niveau moyen. Toute la courbe sort d'une seule acquisition,
avec un réglage d'exposition constant.

Lancement :
    python3 -m module4_bruit.mesure_bruit --etiquette noir      (objectif masqué)
    python3 -m module4_bruit.mesure_bruit --etiquette scene     (scène fixe texturée)
    python3 -m module4_bruit.mesure_bruit --etiquette mire --mire
"""

import argparse

import cv2
import numpy as np

from commun.recepteur import Recepteur
from commun import resultats

MODULE = "module4_bruit"


def afficher_mire_gris():
    """Affiche une échelle de 8 niveaux de gris (bandes verticales) dans une fenêtre."""
    niveaux = np.linspace(0, 255, 8).astype(np.uint8)        # 0, 36, 73 ... 255
    # np.repeat répète chaque niveau 100 fois en largeur -> bandes de 100 px
    ligne = np.repeat(niveaux, 100)
    mire = np.tile(ligne, (600, 1))                           # 600 lignes identiques
    cv2.namedWindow("mire_gris", cv2.WINDOW_NORMAL)
    cv2.imshow("mire_gris", mire)
    cv2.waitKey(500)                                          # laisse le temps de s'afficher


def main():
    parser = argparse.ArgumentParser(description="Mesure du bruit capteur.")
    parser.add_argument("--etiquette", default="scene", help="nom de la condition (noir, scene, mire...)")
    parser.add_argument("--images", type=int, default=100, help="nombre d'images enregistrées")
    parser.add_argument("--ignorer", type=int, default=60, help="images ignorées au début (expo auto)")
    parser.add_argument("--mire", action="store_true", help="afficher une échelle de gris à filmer")
    args = parser.parse_args()
    dossier = resultats.dossier(MODULE)

    if args.mire:
        afficher_mire_gris()

    images = []
    with Recepteur(format="GRAY8", garder_que_la_derniere=False) as rec:
        rec.attendre_flux()
        print(f"NE BOUGEZ PLUS RIEN. Stabilisation ({args.ignorer} images) puis {args.images} images...")
        while len(images) < args.images:
            img = rec.lire(timeout_s=2.0)
            if args.mire:
                cv2.waitKey(1)                                # garde la fenêtre mire vivante
            if img is None:
                print("Flux interrompu.")
                break
            if img.numero >= args.ignorer:
                images.append(img.pixels)
    cv2.destroyAllWindows()
    if len(images) < 10:
        print("Pas assez d'images.")
        return

    # Bloc 3D (N, hauteur, largeur) en flottants pour les calculs
    pile = np.stack(images).astype(np.float32)
    n = pile.shape[0]

    # --- Statistiques temporelles pixel par pixel --------------------------------------
    moyenne_px = pile.mean(axis=0)            # image moyenne (moyenne dans le temps de chaque pixel)
    var_px = pile.var(axis=0, ddof=1)         # variance temporelle de chaque pixel (ddof=1 : estimateur non biaisé)
    bruit_temporel = float(np.sqrt(var_px.mean()))   # bruit temporel RMS (niveaux numériques, "DN")

    # Vérification indépendante façon EMVA 1288 : variance de la DIFFÉRENCE de deux images / 2.
    # La différence supprime tout ce qui est fixe (scène + FPN) ; il ne reste que le bruit temporel.
    bruit_diff = float(np.sqrt(np.var(pile[0] - pile[1]) / 2))

    # --- Bruit spatial fixe (FPN) ------------------------------------------------------
    # On enlève les variations lentes (éclairage, vignettage, scène) avec un gros flou gaussien,
    # il reste les écarts fixes de pixel à pixel.
    haute_freq = moyenne_px - cv2.GaussianBlur(moyenne_px, (31, 31), 0)
    var_spatiale = float(haute_freq.var())
    # L'image moyenne contient encore un résidu de bruit temporel, de variance (bruit_t²)/N :
    # on le soustrait pour ne garder que le vrai bruit fixe.
    fpn = float(np.sqrt(max(var_spatiale - bruit_temporel ** 2 / n, 0.0)))

    satures = float(np.mean((moyenne_px > 250) | (moyenne_px < 2)) * 100)   # % de pixels écrêtés
    niveau = float(moyenne_px.mean())
    rsb = niveau / bruit_temporel if bruit_temporel > 0 else float("inf")

    # --- Courbe de transfert par regroupement des pixels -------------------------------
    # On exclut les pixels sur des contours : un micro-mouvement y crée une fausse variance.
    # Sobel = dérivée de l'image ; magnitude du gradient élevée = contour.
    gx = cv2.Sobel(moyenne_px, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(moyenne_px, cv2.CV_32F, 0, 1, ksize=3)
    lisse = np.hypot(gx, gy) < 8                       # pixels en zone uniforme
    classes = np.arange(0, 257, 4)                     # tranches de 4 niveaux
    # np.digitize : numéro de tranche de chaque pixel selon son niveau moyen
    idx = np.digitize(moyenne_px[lisse], classes) - 1
    v = var_px[lisse]
    m = moyenne_px[lisse]
    courbe = []
    for k in range(len(classes) - 1):
        sel = idx == k
        if sel.sum() >= 200:                           # au moins 200 pixels pour une moyenne fiable
            courbe.append((float(m[sel].mean()), float(v[sel].mean()), int(sel.sum())))
    courbe = np.array(courbe) if courbe else np.zeros((0, 3))

    print("\n=== Résultats ===")
    print(f"Images analysées           : {n} ({pile.shape[2]}x{pile.shape[1]})")
    print(f"Niveau moyen               : {niveau:.1f} DN")
    print(f"Bruit temporel RMS         : {bruit_temporel:.2f} DN  (vérif. par différence : {bruit_diff:.2f} DN)")
    print(f"FPN (bruit spatial fixe)   : {fpn:.2f} DN")
    print(f"Rapport signal/bruit       : {rsb:.1f}  ({20 * np.log10(rsb):.1f} dB)")
    print(f"Pixels écrêtés (0 ou 255)  : {satures:.1f} %")
    print(f"Points de courbe de transfert : {len(courbe)} niveaux")
    if bruit_temporel < 0.3:
        print("  Bruit quasi nul : l'émetteur est-il en profil sans_perte ? La webcam débruite-t-elle ?")

    # --- Sauvegardes -------------------------------------------------------------------
    # Carte du bruit temporel, étirée sur 0-255 pour être visible (cv2.normalize)
    carte = cv2.normalize(np.sqrt(var_px), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    cv2.imwrite(str(dossier / f"carte_bruit_{args.etiquette}.png"), cv2.applyColorMap(carte, cv2.COLORMAP_JET))
    cv2.imwrite(str(dossier / f"image_moyenne_{args.etiquette}.png"), moyenne_px.astype(np.uint8))
    np.save(dossier / f"courbe_{args.etiquette}.npy", courbe)       # relu par courbe_transfert.py
    print(f"Cartes et courbe sauvegardées dans {dossier}")

    resultats.ecrire_resume(MODULE, args.etiquette, {
        "images": n,
        "niveau_moyen_dn": round(niveau, 2),
        "bruit_temporel_dn": round(bruit_temporel, 3),
        "bruit_temporel_par_difference_dn": round(bruit_diff, 3),
        "fpn_dn": round(fpn, 3),
        "rsb_db": round(float(20 * np.log10(rsb)), 1),
        "pixels_ecretes_pct": round(satures, 2),
    })


if __name__ == "__main__":
    main()
