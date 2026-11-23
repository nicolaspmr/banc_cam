"""
module1_latence/analyse_latence.py — Compare les configurations mesurées avec mesure_latence.py.

Lit tous les fichiers resultats/module1_latence/latence_*.csv et trace :
  - à gauche : un histogramme par configuration (forme de la distribution) ;
  - à droite : une "boîte à moustaches" par configuration (médiane, quartiles, extrêmes).
Exemple de campagne : standard_3000k, standard_500k, lent_3000k -> quel réglage coûte combien ?

Lancement :  python3 -m module1_latence.analyse_latence
"""

import csv

import matplotlib
matplotlib.use("Agg")            # "Agg" = dessine dans un fichier PNG, sans ouvrir de fenêtre
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np               # noqa: E402

from commun import resultats     # noqa: E402

MODULE = "module1_latence"


def lire_csv(chemin):
    """Renvoie un tableau NumPy des latences valides (ms) d'un fichier CSV."""
    with open(chemin) as f:
        # csv.DictReader : chaque ligne devient un dictionnaire {"cycle": ..., "latence_ms": ...}
        return np.array([float(l["latence_ms"]) for l in csv.DictReader(f) if l["latence_ms"]])


def main():
    dossier = resultats.dossier(MODULE)
    fichiers = sorted(dossier.glob("latence_*.csv"))
    if not fichiers:
        print("Aucune mesure trouvée : lancez d'abord mesure_latence.py")
        return

    # Le nom de la configuration = le nom du fichier sans "latence_" ni ".csv"
    donnees = {f.stem.removeprefix("latence_"): lire_csv(f) for f in fichiers}
    donnees = {k: v for k, v in donnees.items() if len(v) > 0}

    print(f"{'configuration':22s} {'N':>4s} {'moyenne':>8s} {'médiane':>8s} {'écart-t.':>8s} {'p95':>7s}  (ms)")
    for nom, lat in donnees.items():
        print(f"{nom:22s} {len(lat):4d} {lat.mean():8.1f} {np.median(lat):8.1f} "
              f"{lat.std(ddof=1) if len(lat) > 1 else 0:8.1f} {np.percentile(lat, 95):7.1f}")

    # plt.subplots(1, 2) : une figure avec 2 graphiques côte à côte
    fig, (ax_h, ax_b) = plt.subplots(1, 2, figsize=(12, 5))
    toutes = np.concatenate(list(donnees.values()))
    # Classes de 10 ms couvrant toutes les mesures
    classes = np.arange(np.floor(toutes.min() / 10) * 10, toutes.max() + 10, 10)
    for nom, lat in donnees.items():
        ax_h.hist(lat, bins=classes, alpha=0.5, label=f"{nom} (N={len(lat)})")
    ax_h.set_xlabel("Latence glass-to-glass (ms)")
    ax_h.set_ylabel("Nombre de mesures")
    ax_h.set_title("Distribution des latences")
    ax_h.legend()

    # boxplot : la boîte va du 1er au 3e quartile, le trait = médiane
    ax_b.boxplot(list(donnees.values()), labels=list(donnees.keys()))
    ax_b.set_ylabel("Latence (ms)")
    ax_b.set_title("Comparaison des configurations")
    ax_b.tick_params(axis="x", rotation=20)
    ax_b.grid(axis="y", alpha=0.3)

    fig.tight_layout()                       # évite que les textes se chevauchent
    chemin = dossier / "comparaison_latences.png"
    fig.savefig(chemin, dpi=120)
    print(f"Graphique : {chemin}")


if __name__ == "__main__":
    main()
