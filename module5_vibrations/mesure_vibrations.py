"""
module5_vibrations/mesure_vibrations.py — Mesure du déplacement de l'image (vibrations, stabilité).

Principe : la caméra filme une scène FIXE et texturée. Si la caméra vibre, toute l'image se
décale. On mesure ce décalage entre chaque image et une image de référence par CORRÉLATION
DE PHASE (cv2.phaseCorrelate) : précision sous-pixel, basée sur la transformée de Fourier.

Deux mesures à faire :
  --etiquette repos       : rien ne bouge -> PLANCHER DE MESURE (le bruit du capteur, cf. module 4,
                            crée un faux déplacement : c'est la limite de résolution du banc)
  --etiquette tapotement  : tapotez la table / la caméra -> vibrations à mesurer

Lien avec le module 2 : si l'étalonnage existe, on convertit les pixels en ANGLES (mrad),
grandeur utilisée pour spécifier la stabilisation d'une charge utile optronique.
  angle (rad) ≈ déplacement (px) / focale (px)   (petits angles)

Limite fondamentale (théorème de Shannon-Nyquist) : à 30 i/s, on ne voit correctement que les
fréquences < 15 Hz. Une vibration d'hélice (souvent > 100 Hz) apparaîtrait REPLIÉE (aliasing)
à une fausse fréquence basse, ou en flou de bougé. À dire en entretien.

Lancement :  python3 -m module5_vibrations.mesure_vibrations --etiquette repos --duree 15
"""

import argparse
import csv

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402

from commun.recepteur import Recepteur   # noqa: E402
from commun import resultats             # noqa: E402

MODULE = "module5_vibrations"
TAILLE = 512   # zone centrale analysée (px) : une puissance de 2 rend la FFT plus rapide


def zone_centrale(img):
    """Découpe un carré TAILLE x TAILLE au centre et le convertit en flottants (requis par phaseCorrelate)."""
    h, l = img.shape
    t = min(TAILLE, h, l)
    y0, x0 = (h - t) // 2, (l - t) // 2
    return img[y0:y0 + t, x0:x0 + t].astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description="Mesure de vibrations par corrélation de phase.")
    parser.add_argument("--etiquette", default="repos", help="nom de la condition (repos, tapotement...)")
    parser.add_argument("--duree", type=float, default=15, help="durée de mesure (s)")
    args = parser.parse_args()
    dossier = resultats.dossier(MODULE)

    temps, dx, dy, confiance = [], [], [], []
    with Recepteur(format="GRAY8", garder_que_la_derniere=False) as rec:
        premiere = rec.attendre_flux()
        ref = zone_centrale(premiere.pixels)
        # Fenêtre de Hanning : atténue les bords de la zone pour éviter que la FFT "voie" une
        # discontinuité aux bords (sinon le pic de corrélation est pollué).
        fenetre = cv2.createHanningWindow(ref.shape[::-1], cv2.CV_32F)
        t0 = premiere.t
        print(f"Mesure pendant {args.duree} s (étiquette : {args.etiquette})...")
        while True:
            img = rec.lire(timeout_s=2.0)
            if img is None:
                break
            # phaseCorrelate renvoie ((décalage_x, décalage_y), réponse).
            # réponse ∈ [0, 1] = netteté du pic de corrélation = confiance dans la mesure.
            (sx, sy), rep = cv2.phaseCorrelate(ref, zone_centrale(img.pixels), fenetre)
            temps.append(img.t - t0)
            dx.append(sx)
            dy.append(sy)
            confiance.append(rep)
            if temps[-1] >= args.duree:
                break

    if len(temps) < 30:
        print("Pas assez d'images.")
        return
    t, dx, dy = np.array(temps), np.array(dx), np.array(dy)

    # --- Conversion en angles si l'étalonnage (module 2) existe --------------------------
    etal = resultats.lire_etalonnage()
    if etal:
        fx, fy = etal["fx"], etal["fy"]
        # Attention : l'étalonnage doit avoir été fait à la MÊME résolution que cette mesure
        if etal["largeur"] != premiere.pixels.shape[1]:
            print(f"  Étalonnage fait en {etal['largeur']} px de large, mesure en {premiere.pixels.shape[1]} : "
                  "on remet la focale à l'échelle.")
            echelle = premiere.pixels.shape[1] / etal["largeur"]
            fx, fy = fx * echelle, fy * echelle
        ax_mrad, ay_mrad = dx / fx * 1000, dy / fy * 1000
    else:
        print("  Pas d'étalonnage (module 2) : résultats en pixels seulement.")

    # --- Analyse temporelle ----------------------------------------------------------------
    dxc, dyc = dx - dx.mean(), dy - dy.mean()        # on retire la position moyenne
    rms_x, rms_y = float(dxc.std()), float(dyc.std())
    crete = float(np.max(np.hypot(dxc, dyc)))        # déplacement maximal (norme)

    # --- Analyse fréquentielle -------------------------------------------------------------
    # Les images n'arrivent pas à intervalles parfaitement réguliers (gigue, cf. module 0) :
    # on ré-échantillonne sur une grille régulière (np.interp) avant la FFT.
    fe = (len(t) - 1) / (t[-1] - t[0])               # fréquence d'échantillonnage réelle
    grille = np.arange(t[0], t[-1], 1 / fe)
    signal = np.interp(grille, t, dxc)               # on analyse l'axe x, plus simple à interpréter
    signal = signal - signal.mean()
    # rfft = FFT pour un signal réel ; fenêtre de Hann pour limiter les fuites spectrales
    spectre = np.abs(np.fft.rfft(signal * np.hanning(len(signal)))) * 2 / len(signal)
    freqs = np.fft.rfftfreq(len(signal), d=1 / fe)
    utile = freqs > 0.3                              # on ignore la dérive très lente
    f_pic = float(freqs[utile][np.argmax(spectre[utile])]) if utile.any() else float("nan")

    print("\n=== Résultats ===")
    print(f"Images : {len(t)} | fréquence d'échantillonnage : {fe:.1f} Hz -> Nyquist {fe / 2:.1f} Hz")
    print(f"Déplacement RMS : x {rms_x:.3f} px, y {rms_y:.3f} px | crête : {crete:.2f} px")
    print(f"Confiance moyenne de la corrélation : {np.mean(confiance):.2f}")
    print(f"Fréquence dominante (axe x) : {f_pic:.2f} Hz")
    valeurs = {"images": len(t), "fe_hz": round(fe, 1), "nyquist_hz": round(fe / 2, 1),
               "rms_x_px": round(rms_x, 4), "rms_y_px": round(rms_y, 4), "crete_px": round(crete, 3),
               "frequence_dominante_hz": round(f_pic, 2)}
    if etal:
        rx, ry = float(np.std(ax_mrad)), float(np.std(ay_mrad))
        print(f"Déplacement angulaire RMS : x {rx:.3f} mrad, y {ry:.3f} mrad")
        valeurs.update({"rms_x_mrad": round(rx, 4), "rms_y_mrad": round(ry, 4)})

    # --- Sauvegardes -----------------------------------------------------------------------
    with open(dossier / f"vibrations_{args.etiquette}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "dx_px", "dy_px", "confiance"])
        w.writerows(zip(np.round(t, 4), np.round(dx, 4), np.round(dy, 4), np.round(confiance, 3)))

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7))
    a1.plot(t, dxc, label="x")
    a1.plot(t, dyc, label="y")
    a1.set_xlabel("Temps (s)")
    a1.set_ylabel("Déplacement (px)")
    a1.set_title(f"Déplacement de l'image — {args.etiquette}")
    a1.grid(alpha=0.3)
    a1.legend()
    a2.plot(freqs, spectre)
    a2.axvline(fe / 2, color="r", ls="--", label=f"Nyquist {fe / 2:.1f} Hz")
    a2.set_xlabel("Fréquence (Hz)")
    a2.set_ylabel("Amplitude (px)")
    a2.set_title("Spectre du déplacement (axe x)")
    a2.grid(alpha=0.3)
    a2.legend()
    fig.tight_layout()
    fig.savefig(dossier / f"vibrations_{args.etiquette}.png", dpi=120)
    print(f"Graphique : {dossier / f'vibrations_{args.etiquette}.png'}")

    resultats.ecrire_resume(MODULE, args.etiquette, valeurs)


if __name__ == "__main__":
    main()
