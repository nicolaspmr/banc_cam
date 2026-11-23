"""
module2_etalonnage/capture_damier.py — Capture des vues du damier pour l'étalonnage.

Affiche le flux en direct. Quand le damier est détecté, ses coins sont dessinés en couleur.
  - ESPACE : enregistre l'image (seulement si le damier est détecté)
  - q      : quitter
Visez 20 à 30 images VARIÉES : damier au centre, dans les 4 coins, près, loin, incliné
(jusqu'à ~45°). La variété est ce qui rend l'étalonnage précis, surtout pour la distorsion
qui est forte sur les bords de l'image.

Lancement :  python3 -m module2_etalonnage.capture_damier --coins 9x6
"""

import argparse

import cv2

from commun.recepteur import Recepteur
from commun import resultats

MODULE = "module2_etalonnage"


def main():
    parser = argparse.ArgumentParser(description="Capture d'images du damier.")
    parser.add_argument("--coins", default="9x6", help="coins intérieurs, ex. 9x6")
    args = parser.parse_args()
    nx, ny = (int(v) for v in args.coins.lower().split("x"))

    dossier_img = resultats.dossier(MODULE) / "images"
    dossier_img.mkdir(exist_ok=True)
    n = len(list(dossier_img.glob("*.png")))       # on continue la numérotation existante

    with Recepteur(format="BGR", garder_que_la_derniere=True) as rec:
        rec.attendre_flux()
        print("ESPACE = enregistrer (si damier détecté), q = quitter")
        while True:
            img = rec.lire()
            if img is None:
                continue
            image = img.pixels
            # La détection sur l'image pleine résolution est lente : on cherche sur une image
            # réduite de moitié (cv2.resize), c'est suffisant pour l'aperçu en direct.
            petite = cv2.resize(image, None, fx=0.5, fy=0.5)
            gris = cv2.cvtColor(petite, cv2.COLOR_BGR2GRAY)
            # findChessboardCorners : cherche les nx*ny coins intérieurs.
            # FAST_CHECK abandonne vite s'il n'y a manifestement pas de damier (aperçu fluide).
            trouve, coins = cv2.findChessboardCorners(
                gris, (nx, ny), flags=cv2.CALIB_CB_FAST_CHECK | cv2.CALIB_CB_ADAPTIVE_THRESH)

            apercu = petite.copy()
            if trouve:
                cv2.drawChessboardCorners(apercu, (nx, ny), coins, trouve)   # dessine les coins
            texte = f"{n} images | {'DAMIER OK - ESPACE' if trouve else 'damier non detecte'}"
            # putText écrit du texte sur l'image (pas d'accents : police OpenCV limitée)
            cv2.putText(apercu, texte, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 255, 0) if trouve else (0, 0, 255), 2)
            cv2.imshow("capture_damier", apercu)

            touche = cv2.waitKey(1) & 0xFF
            if touche == ord("q"):
                break
            if touche == ord(" ") and trouve:
                chemin = dossier_img / f"damier_{n:03d}.png"
                cv2.imwrite(str(chemin), image)      # on enregistre l'image PLEINE résolution
                n += 1
                print(f"  enregistrée : {chemin.name}")
    cv2.destroyAllWindows()
    print(f"{n} images dans {dossier_img}. Étape suivante : etalonnage.py")


if __name__ == "__main__":
    main()
