"""
module1_chaine/test_chaine.py — Vérifier et caractériser la chaîne vidéo elle-même.

Question posée : "le flux arrive-t-il, à quelle cadence réelle, avec quelle régularité ?"
C'est la première mesure à faire : si la chaîne perd des images ou a une cadence irrégulière,
toutes les mesures suivantes seront faussées.

Ce que le script mesure pendant DUREE secondes :
  - la cadence réelle (images/s) ;
  - l'intervalle entre deux images reçues et sa GIGUE (écart-type de cet intervalle) ;
  - les "trous" : intervalles > 1,5 x la période nominale (= images probablement perdues) ;
  - la luminosité moyenne et l'écart-type spatial de l'image (pour observer l'exposition auto).
Il écrit un CSV (une ligne par image) + un résumé JSON pour la fiche caméra.

Lancement (depuis banc_cam/) :
    python3 -m module1_chaine.test_chaine --duree 30 --etiquette standard_3000k
"""

import argparse          # lecture des options en ligne de commande (--duree, --etiquette)
import csv               # écriture de fichiers CSV (lisibles dans Excel)

import numpy as np

from commun.recepteur import Recepteur
from commun import resultats

MODULE = "module1_chaine"


def main():
    # argparse : on déclare les options acceptées, il fabrique l'aide (--help) tout seul
    parser = argparse.ArgumentParser(description="Caractérise la chaîne vidéo (cadence, gigue, pertes).")
    parser.add_argument("--duree", type=float, default=30, help="durée de mesure en secondes")
    parser.add_argument("--etiquette", default="standard", help="nom de la configuration testée")
    parser.add_argument("--fps-nominal", type=float, default=30, help="cadence attendue (i/s)")
    args = parser.parse_args()

    dossier = resultats.dossier(MODULE)
    temps, moyennes, ecarts = [], [], []

    # garder_que_la_derniere=False : on veut voir TOUTES les images pour compter les pertes
    with Recepteur(format="GRAY8", garder_que_la_derniere=False) as rec:
        premiere = rec.attendre_flux()
        t0 = premiere.t
        print(f"Mesure pendant {args.duree} s...")
        while True:
            img = rec.lire(timeout_s=2.0)
            if img is None:
                print("Plus d'images depuis 2 s : arrêt.")
                break
            temps.append(img.t - t0)
            # .mean() / .std() de NumPy : moyenne et écart-type sur TOUS les pixels de l'image
            moyennes.append(float(img.pixels.mean()))
            ecarts.append(float(img.pixels.std()))
            if temps[-1] >= args.duree:
                break
            # Affichage d'un point d'étape chaque seconde environ (toutes les 30 images)
            if len(temps) % 30 == 0:
                print(f"  t = {temps[-1]:5.1f} s | moyenne = {moyennes[-1]:6.1f} | écart-type = {ecarts[-1]:5.1f}")

    if len(temps) < 3:
        print("Pas assez d'images pour conclure.")
        return

    # --- Analyse --------------------------------------------------------------
    t = np.array(temps)
    # np.diff : différences successives -> intervalle entre deux images consécutives
    intervalles_ms = np.diff(t) * 1000
    periode_nominale_ms = 1000 / args.fps_nominal
    fps_mesure = (len(t) - 1) / (t[-1] - t[0])
    # Un intervalle 1,5 fois plus long que prévu = au moins une image manquante
    nb_trous = int(np.sum(intervalles_ms > 1.5 * periode_nominale_ms))
    # Estimation du nombre d'images perdues : dans chaque trou, round(intervalle/période) - 1
    trous = intervalles_ms[intervalles_ms > 1.5 * periode_nominale_ms]
    images_perdues = int(np.sum(np.round(trous / periode_nominale_ms) - 1))

    print("\n=== Résultats ===")
    print(f"Images reçues        : {len(t)}")
    print(f"Cadence mesurée      : {fps_mesure:.2f} i/s (nominal {args.fps_nominal})")
    print(f"Intervalle moyen     : {intervalles_ms.mean():.1f} ms (nominal {periode_nominale_ms:.1f} ms)")
    print(f"Gigue (écart-type)   : {intervalles_ms.std():.1f} ms")
    print(f"Intervalle min / max : {intervalles_ms.min():.1f} / {intervalles_ms.max():.1f} ms")
    print(f"Trous détectés       : {nb_trous} (~{images_perdues} images perdues)")

    # --- Sauvegarde -----------------------------------------------------------
    chemin_csv = dossier / f"chaine_{args.etiquette}.csv"
    with open(chemin_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "intervalle_ms", "moyenne", "ecart_type"])
        for i in range(len(t)):
            inter = "" if i == 0 else f"{intervalles_ms[i - 1]:.2f}"
            w.writerow([f"{t[i]:.4f}", inter, f"{moyennes[i]:.2f}", f"{ecarts[i]:.2f}"])
    print(f"Données brutes : {chemin_csv}")

    resultats.ecrire_resume(MODULE, args.etiquette, {
        "images_recues": len(t),
        "fps_mesure": round(fps_mesure, 2),
        "intervalle_moyen_ms": round(float(intervalles_ms.mean()), 2),
        "gigue_ms": round(float(intervalles_ms.std()), 2),
        "images_perdues_estimees": images_perdues,
    })


if __name__ == "__main__":   # vrai seulement quand on lance ce fichier directement
    main()
