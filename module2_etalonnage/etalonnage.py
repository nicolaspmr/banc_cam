"""
module2_etalonnage/etalonnage.py — Étalonnage géométrique de la caméra (méthode de Zhang).

Modèle "sténopé" (pinhole) + distorsion. Un point 3D (X, Y, Z) se projette en pixel (u, v) :
    u = fx * X/Z + cx        v = fy * Y/Z + cy        (+ termes de distorsion)
  - fx, fy : focale exprimée en PIXELS (focale en mm / taille d'un pixel en mm)
  - cx, cy : centre optique (là où l'axe optique perce le capteur)
  - k1, k2, p1, p2, k3 : distorsion radiale (k) et tangentielle (p)
Méthode de Zhang : on montre un objet plan connu (le damier) sous plusieurs angles ;
chaque vue donne une homographie, et l'ensemble permet de retrouver fx, fy, cx, cy et la distorsion.

Sorties :
  - resultats/module2_etalonnage/etalonnage.json : paramètres + incertitudes (RÉUTILISÉ par le module 5)
  - une image avant/après correction de la distorsion
  - le résumé pour la fiche caméra

Lancement :  python3 -m module2_etalonnage.etalonnage --coins 9x6 --case-mm 25
"""

import argparse
import json
import math

import cv2
import numpy as np

from commun import resultats

MODULE = "module2_etalonnage"


def main():
    parser = argparse.ArgumentParser(description="Étalonnage caméra à partir des images de damier.")
    parser.add_argument("--coins", default="9x6", help="coins intérieurs, ex. 9x6")
    parser.add_argument("--case-mm", type=float, default=25.0, help="côté d'une case MESURÉ à la règle (mm)")
    parser.add_argument("--images", default="images", help="sous-dossier des images de damier")
    parser.add_argument("--avec-k3", action="store_true",
                        help="estimer aussi k3 (utile seulement pour les objectifs très déformants, type fisheye)")
    args = parser.parse_args()
    nx, ny = (int(v) for v in args.coins.lower().split("x"))
    dossier = resultats.dossier(MODULE)
    fichiers = sorted((dossier / args.images).glob("*.png"))
    if len(fichiers) < 10:
        print(f"Seulement {len(fichiers)} images : il en faut au moins 10 (idéalement 20-30).")
        if not fichiers:
            return

    # Coordonnées 3D des coins dans le repère du damier (plan Z = 0), en mm :
    # (0,0,0), (25,0,0), (50,0,0)... -> np.mgrid fabrique cette grille
    objet = np.zeros((nx * ny, 3), np.float32)
    objet[:, :2] = np.mgrid[0:nx, 0:ny].T.reshape(-1, 2) * args.case_mm

    points_3d, points_2d, noms = [], [], []
    taille_image = None
    # Critère d'arrêt pour l'affinage sous-pixel : 30 itérations max ou déplacement < 0,001 px
    critere = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    for f in fichiers:
        gris = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)        # lecture directe en niveaux de gris
        taille_image = gris.shape[::-1]                        # (largeur, hauteur)
        trouve, coins = cv2.findChessboardCorners(
            gris, (nx, ny), flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not trouve:
            print(f"  {f.name} : damier non trouvé, image ignorée")
            continue
        # cornerSubPix affine la position de chaque coin au dixième de pixel près,
        # en exploitant les gradients d'intensité autour du coin (fenêtre de 11x11 px).
        coins = cv2.cornerSubPix(gris, coins, (11, 11), (-1, -1), critere)
        points_3d.append(objet)
        points_2d.append(coins)
        noms.append(f.name)

    print(f"{len(noms)} images exploitables sur {len(fichiers)}")
    if len(noms) < 3:
        print("Pas assez d'images exploitables.")
        return

    # calibrateCameraExtended : comme calibrateCamera, mais renvoie EN PLUS l'écart-type
    # estimé de chaque paramètre -> on obtient une incertitude, pas juste une valeur.
    # Par défaut on FIXE k3 = 0 : avec une webcam peu déformante, estimer k3 donne un coefficient
    # instable qui "absorbe" le bruit de mesure (surajustement). Moins de paramètres = plus robuste.
    drapeaux = 0 if args.avec_k3 else cv2.CALIB_FIX_K3
    (rms, K, dist, rvecs, tvecs, std_intr, _std_extr, err_par_vue) = cv2.calibrateCameraExtended(
        points_3d, points_2d, taille_image, None, None, flags=drapeaux)
    # rms = erreur de reprojection moyenne (px) : écart entre les coins détectés et les coins
    #       re-projetés avec le modèle trouvé. < 0,5 px = bon étalonnage.

    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    s_fx, s_fy, s_cx, s_cy = (float(v) for v in std_intr[:4, 0])
    largeur, hauteur = taille_image
    # Champ de vision : demi-largeur de l'image / focale = tangente du demi-angle
    fov_h = 2 * math.degrees(math.atan(largeur / (2 * fx)))
    fov_v = 2 * math.degrees(math.atan(hauteur / (2 * fy)))
    fov_d = 2 * math.degrees(math.atan(math.hypot(largeur, hauteur) / (2 * (fx + fy) / 2)))
    # IFOV (champ instantané d'un pixel) en milliradians : utile pour exprimer une résolution angulaire
    ifov_mrad = 1000 / fx

    print("\n=== Résultats ===")
    print(f"Erreur de reprojection RMS : {rms:.3f} px")
    print(f"fx = {fx:.1f} ± {s_fx:.1f} px   fy = {fy:.1f} ± {s_fy:.1f} px")
    print(f"cx = {cx:.1f} ± {s_cx:.1f} px   cy = {cy:.1f} ± {s_cy:.1f} px  (centre image : {largeur/2:.0f}, {hauteur/2:.0f})")
    print(f"Distorsion [k1 k2 p1 p2 k3] = {np.round(dist.ravel(), 4)}")
    print(f"Champ de vision : H {fov_h:.1f}°  V {fov_v:.1f}°  diagonale {fov_d:.1f}°")
    print(f"IFOV (1 pixel)  : {ifov_mrad:.3f} mrad")
    print("Erreur par image (repérez les images aberrantes) :")
    for nom, e in zip(noms, err_par_vue.ravel()):
        print(f"  {nom} : {e:.3f} px{'   <-- à vérifier' if e > 2 * rms else ''}")

    etalonnage = {
        "largeur": largeur, "hauteur": hauteur, "nb_images": len(noms),
        "K": K.tolist(), "distorsion": dist.ravel().tolist(),
        "fx": fx, "fy": fy, "cx": cx, "cy": cy,
        "incertitude_fx": s_fx, "incertitude_fy": s_fy,
        "rms_reprojection_px": rms,
        "fov_h_deg": fov_h, "fov_v_deg": fov_v, "fov_diag_deg": fov_d, "ifov_mrad": ifov_mrad,
    }
    (dossier / "etalonnage.json").write_text(json.dumps(etalonnage, indent=2))
    print(f"Paramètres sauvegardés : {dossier / 'etalonnage.json'} (utilisé par le module 5)")

    # Avant / après : undistort() applique le modèle inverse pour redresser les lignes courbées
    exemple = cv2.imread(str(dossier / args.images / noms[0]))
    corrige = cv2.undistort(exemple, K, dist)
    cv2.imwrite(str(dossier / "avant_apres_distorsion.png"), np.hstack([exemple, corrige]))
    print(f"Avant/après : {dossier / 'avant_apres_distorsion.png'}")

    resultats.ecrire_resume(MODULE, "etalonnage", {
        "nb_images": len(noms),
        "rms_reprojection_px": round(rms, 3),
        "fx_px": round(fx, 1), "incertitude_fx_px": round(s_fx, 1),
        "fy_px": round(fy, 1),
        "cx_px": round(cx, 1), "cy_px": round(cy, 1),
        "k1": round(float(dist.ravel()[0]), 4), "k2": round(float(dist.ravel()[1]), 4),
        "fov_h_deg": round(fov_h, 1), "fov_v_deg": round(fov_v, 1), "fov_diag_deg": round(fov_d, 1),
        "ifov_mrad": round(ifov_mrad, 3),
    })


if __name__ == "__main__":
    main()
