"""
module2_debit_qualite/enregistre_reference.py — Enregistre une séquence de RÉFÉRENCE.

La référence doit être aussi fidèle que possible à ce que voit le capteur : lancez l'émetteur
en profil SANS PERTE (./emetteur/lancer_emetteur.sh sans_perte). Sinon, on comparerait des
images compressées à d'autres images compressées.

Conseil de scène : une scène texturée (bureau, livres, plante) avec un peu de mouvement
(bougez lentement la main). Le contenu change tout : une scène fixe et uniforme se compresse
presque sans perte même à bas débit, une scène détaillée et mobile non.

Lancement :  python3 -m module2_debit_qualite.enregistre_reference --images 150
"""

import argparse

import numpy as np

from commun.recepteur import Recepteur
from commun import resultats

MODULE = "module2_debit_qualite"


def main():
    parser = argparse.ArgumentParser(description="Enregistre une séquence de référence.")
    parser.add_argument("--images", type=int, default=150, help="nombre d'images (150 = 5 s à 30 i/s)")
    parser.add_argument("--ignorer", type=int, default=30, help="images ignorées au début (expo auto)")
    args = parser.parse_args()

    images = []
    # garder_que_la_derniere=False : on veut une séquence CONTINUE, sans image sautée
    with Recepteur(format="GRAY8", garder_que_la_derniere=False) as rec:
        rec.attendre_flux()
        print(f"On ignore {args.ignorer} images (stabilisation de l'exposition), puis on enregistre...")
        while len(images) < args.images:
            img = rec.lire(timeout_s=2.0)
            if img is None:
                print("Flux interrompu.")
                break
            if img.numero >= args.ignorer:
                images.append(img.pixels)

    if not images:
        return
    # np.stack : liste de N images (h, l) -> un seul tableau (N, h, l)
    sequence = np.stack(images)
    chemin = resultats.dossier(MODULE) / "reference.npy"
    np.save(chemin, sequence)                 # format binaire NumPy, relu avec np.load
    print(f"Référence : {sequence.shape[0]} images {sequence.shape[2]}x{sequence.shape[1]} -> {chemin}")


if __name__ == "__main__":
    main()
