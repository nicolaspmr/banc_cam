"""
module2_etalonnage/valider_synthetique.py — Valider l'algorithme sur une VÉRITÉ TERRAIN connue.

Réflexe de physique de la mesure : avant de croire un résultat sur la vraie caméra, on vérifie
que la méthode retrouve des valeurs CONNUES. Ici on fabrique 15 photos virtuelles du damier
avec une caméra parfaite de focale fx = fy = 1000 px, centre (640, 360), sans distorsion,
puis on lance etalonnage.py dessus. Il doit retrouver ~1000 px (à son incertitude près).

Lancement :
    python3 -m module2_etalonnage.generer_damier
    python3 -m module2_etalonnage.valider_synthetique
    python3 -m module2_etalonnage.etalonnage --images images_synthetiques
(puis relancez etalonnage.py sur vos vraies images pour écraser etalonnage.json)
"""

import cv2
import numpy as np

from commun import resultats

MODULE = "module2_etalonnage"


def main():
    dossier = resultats.dossier(MODULE)
    damier = cv2.imread(str(dossier / "damier_a_imprimer.png"), cv2.IMREAD_GRAYSCALE)
    if damier is None:
        print("Lancez d'abord generer_damier.py")
        return

    # Caméra virtuelle : matrice intrinsèque K (la "vérité")
    K = np.array([[1000.0, 0, 640], [0, 1000.0, 360], [0, 0, 1]])
    mm_par_px = 25.4 / 300                       # le PNG du damier est à 300 dpi
    # S convertit un pixel du PNG en mm dans le plan du damier, origine au centre de la page A4
    S = np.array([[mm_par_px, 0, -148.5], [0, mm_par_px, -105.0], [0, 0, 1]])

    sortie = dossier / "images_synthetiques"
    sortie.mkdir(exist_ok=True)
    rng = np.random.default_rng(0)               # graine fixe -> mêmes images à chaque fois
    for i in range(15):
        # Orientation aléatoire du damier (vecteur de rotation, en radians) et position (mm)
        rvec = rng.uniform(-0.5, 0.5, 3)
        rvec[2] *= 0.3
        R, _ = cv2.Rodrigues(rvec)               # Rodrigues : vecteur rotation -> matrice 3x3
        t = np.array([rng.uniform(-60, 60), rng.uniform(-40, 40), rng.uniform(450, 650)])
        # Pour un objet plan (Z = 0), la projection est une homographie H = K [r1 r2 t]
        H = K @ np.column_stack([R[:, 0], R[:, 1], t]) @ S
        # warpPerspective applique l'homographie : on "photographie" le damier virtuellement
        vue = cv2.warpPerspective(damier, H, (1280, 720), borderValue=128)
        vue = cv2.GaussianBlur(vue, (3, 3), 0)   # léger flou, comme une vraie optique
        cv2.imwrite(str(sortie / f"synth_{i:03d}.png"), vue)
    print(f"15 vues synthétiques dans {sortie}")
    print("Vérité : fx = fy = 1000 px, cx = 640, cy = 360, distorsion nulle.")
    print("Lancez : python3 -m module2_etalonnage.etalonnage --images images_synthetiques")


if __name__ == "__main__":
    main()
