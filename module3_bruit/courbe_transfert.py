"""
module3_bruit/courbe_transfert.py — Trace et ajuste la courbe de transfert (variance vs niveau).

Relit les courbe_<etiquette>.npy produits par mesure_bruit.py et trace, pour chaque acquisition :
  variance temporelle (DN²) en fonction du niveau moyen (DN).

Interprétation :
  - Capteur linéaire idéal : variance = variance_noir + K x (niveau - niveau_noir)
      K (pente)  = gain de conversion apparent, en DN par électron
      ordonnée   = bruit de lecture + courant d'obscurité (le "plancher")
  - Webcam réelle : le traitement interne (gamma, débruitage, netteté) COURBE cette droite.
    Une courbe non linéaire est donc un RÉSULTAT : elle prouve que l'on ne mesure pas le capteur
    brut mais toute la chaîne. C'est exactement ce qu'il faut savoir dire en entretien.

Lancement :  python3 -m module3_bruit.courbe_transfert
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402

from commun import resultats      # noqa: E402

MODULE = "module3_bruit"


def main():
    dossier = resultats.dossier(MODULE)
    fichiers = sorted(dossier.glob("courbe_*.npy"))
    if not fichiers:
        print("Aucune courbe : lancez d'abord mesure_bruit.py")
        return

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    tous_m, tous_v = [], []
    for f in fichiers:
        c = np.load(f)
        if len(c) == 0:
            continue
        nom = f.stem.removeprefix("courbe_")
        a1.plot(c[:, 0], c[:, 1], "o", ms=4, label=nom)
        # RSB = niveau / écart-type ; en log-log, un régime "photonique" a une pente de 1/2
        a2.loglog(c[:, 0], c[:, 0] / np.sqrt(np.maximum(c[:, 1], 1e-6)), "o", ms=4, label=nom)
        tous_m.append(c[:, 0])
        tous_v.append(c[:, 1])

    m = np.concatenate(tous_m)
    v = np.concatenate(tous_v)
    # Ajustement linéaire sur la zone non écrêtée (entre 5 et 240 DN).
    zone = (m > 5) & (m < 240)
    valeurs = {}
    if zone.sum() >= 3:
        # np.polyfit(x, y, 1) : droite des moindres carrés -> [pente, ordonnée à l'origine]
        pente, ordonnee = np.polyfit(m[zone], v[zone], 1)
        # Coefficient de détermination R² : 1 = droite parfaite. Faible = la chaîne n'est pas linéaire.
        ajuste = pente * m[zone] + ordonnee
        r2 = 1 - np.sum((v[zone] - ajuste) ** 2) / np.sum((v[zone] - v[zone].mean()) ** 2)
        xs = np.linspace(m[zone].min(), m[zone].max(), 50)
        a1.plot(xs, pente * xs + ordonnee, "k--", label=f"ajustement : pente {pente:.3f} DN, R² {r2:.2f}")
        print(f"Pente (gain apparent K)  : {pente:.4f} DN/e-   (soit {1 / pente:.1f} e-/DN)" if pente > 0
              else f"Pente : {pente:.4f} (négative : régime non photonique, voir commentaires)")
        print(f"Ordonnée à l'origine     : {ordonnee:.3f} DN²")
        print(f"Linéarité (R²)           : {r2:.3f}")
        if r2 < 0.9:
            print("  R² faible : la chaîne n'est pas linéaire (gamma / débruitage de la webcam).")
        valeurs = {"pente_dn_par_e": round(float(pente), 4), "ordonnee_dn2": round(float(ordonnee), 3),
                   "r2_linearite": round(float(r2), 3)}

    a1.set_xlabel("Niveau moyen (DN)")
    a1.set_ylabel("Variance temporelle (DN²)")
    a1.set_title("Courbe de transfert (type EMVA 1288)")
    a1.grid(alpha=0.3)
    a1.legend(fontsize=8)
    a2.set_xlabel("Niveau moyen (DN)")
    a2.set_ylabel("Rapport signal/bruit")
    a2.set_title("RSB en fonction du niveau")
    a2.grid(alpha=0.3, which="both")
    a2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(dossier / "courbe_transfert.png", dpi=120)
    print(f"Graphique : {dossier / 'courbe_transfert.png'}")
    if valeurs:
        resultats.ecrire_resume(MODULE, "courbe_transfert", valeurs)


if __name__ == "__main__":
    main()
