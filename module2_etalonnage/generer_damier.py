"""
module2_etalonnage/generer_damier.py — Crée une mire damier à imprimer (A4, 300 dpi).

Par défaut : 10 x 7 cases de 25 mm -> 9 x 6 coins INTÉRIEURS (c'est ce que détecte OpenCV).
Après impression, MESUREZ une case à la règle : l'imprimante peut redimensionner.
Collez la feuille bien à plat sur un carton (un damier gondolé fausse l'étalonnage).

Lancement :  python3 -m module2_etalonnage.generer_damier
"""

import argparse

import cv2
import numpy as np

from commun import resultats


def main():
    parser = argparse.ArgumentParser(description="Génère un damier à imprimer.")
    parser.add_argument("--cases-x", type=int, default=10, help="nombre de cases en largeur")
    parser.add_argument("--cases-y", type=int, default=7, help="nombre de cases en hauteur")
    parser.add_argument("--taille-mm", type=float, default=25.0, help="côté d'une case (mm)")
    args = parser.parse_args()

    dpi = 300
    px_par_mm = dpi / 25.4                         # 1 pouce = 25,4 mm
    a4_l, a4_h = int(297 * px_par_mm), int(210 * px_par_mm)   # A4 paysage, en pixels
    case = int(round(args.taille_mm * px_par_mm))

    page = np.full((a4_h, a4_l), 255, dtype=np.uint8)          # page blanche
    x0 = (a4_l - args.cases_x * case) // 2                     # centrage du damier
    y0 = (a4_h - args.cases_y * case) // 2
    for i in range(args.cases_y):
        for j in range(args.cases_x):
            if (i + j) % 2 == 0:                               # une case sur deux en noir
                page[y0 + i * case: y0 + (i + 1) * case, x0 + j * case: x0 + (j + 1) * case] = 0

    chemin = resultats.dossier("module2_etalonnage") / "damier_a_imprimer.png"
    cv2.imwrite(str(chemin), page)
    print(f"Damier : {chemin}")
    print(f"Imprimez à 100 % (sans 'ajuster à la page'). Coins intérieurs : "
          f"{args.cases_x - 1} x {args.cases_y - 1}, case = {args.taille_mm} mm")


if __name__ == "__main__":
    main()
