"""
module3_debit_qualite/debit_qualite.py — Courbe débit / qualité de l'encodeur H.264.

Pour chaque débit cible (250, 500, 1000, 2000, 4000 kbit/s par défaut) :
  1. on POUSSE la séquence de référence dans un pipeline GStreamer grâce à `appsrc`
     (l'inverse d'appsink : Python -> GStreamer) ;
  2. le pipeline encode en H.264 puis décode : appsrc -> x264enc -> h264parse -> avdec_h264 -> appsink ;
  3. une "sonde" (pad probe) placée après l'encodeur compte les octets produits -> débit RÉEL ;
  4. on compare chaque image décodée à l'originale : PSNR et SSIM.

Vérification préalable (réflexe de métrologue) : on fait d'abord passer la séquence dans le
même pipeline SANS encodeur. Le PSNR doit être infini (images identiques) ; sinon, c'est la
chaîne de mesure elle-même qui dégrade l'image, et toutes les valeurs seraient fausses.

Lancement :  python3 -m module3_debit_qualite.debit_qualite --debits 250 500 1000 2000 4000
"""

import argparse
import math

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402
import gi                         # noqa: E402

gi.require_version("Gst", "1.0")
from gi.repository import Gst     # noqa: E402

from commun import resultats      # noqa: E402

Gst.init(None)
MODULE = "module3_debit_qualite"
FPS = 30


# ----------------------------------------------------------------------------- métriques
def psnr(ref, test):
    """
    PSNR (Peak Signal-to-Noise Ratio), en dB : 10 log10(255² / EQM).
    EQM = erreur quadratique moyenne entre les pixels. Plus c'est haut, mieux c'est.
    Repères : > 40 dB excellent, 30-40 bon, < 30 dégradation visible.
    """
    eqm = np.mean((ref.astype(np.float64) - test.astype(np.float64)) ** 2)
    return math.inf if eqm == 0 else 10 * math.log10(255.0 ** 2 / eqm)


def ssim(ref, test):
    """
    SSIM (Structural SIMilarity), entre 0 et 1 : compare localement luminance, contraste et structure.
    Plus proche de la perception humaine que le PSNR. Implémentation standard (Wang et al. 2004) :
    statistiques locales calculées avec un flou gaussien 11x11, sigma = 1,5.
    """
    x, y = ref.astype(np.float64), test.astype(np.float64)
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2      # constantes de stabilisation
    flou = lambda img: cv2.GaussianBlur(img, (11, 11), 1.5)   # moyenne locale pondérée
    mx, my = flou(x), flou(y)
    vx, vy = flou(x * x) - mx ** 2, flou(y * y) - my ** 2      # variances locales
    cxy = flou(x * y) - mx * my                                # covariance locale
    carte = ((2 * mx * my + C1) * (2 * cxy + C2)) / ((mx ** 2 + my ** 2 + C1) * (vx + vy + C2))
    return float(carte.mean())


# ----------------------------------------------------------------------------- pipeline
def encoder_decoder(sequence, debit_kbits=None):
    """
    Fait passer la séquence (N, h, l) dans GStreamer, avec encodage H.264 si debit_kbits est donné.
    Renvoie (séquence décodée, nombre d'octets H.264 produits).
    """
    n, h, l = sequence.shape
    # Le format GRAY8 impose des lignes de largeur multiple de 4 octets en mémoire GStreamer.
    assert l % 4 == 0, "largeur non multiple de 4 : non géré dans ce script"

    caps = f"video/x-raw,format=GRAY8,width={l},height={h},framerate={FPS}/1"
    # appsrc format=time : nos buffers portent des timestamps en nanosecondes
    description = f"appsrc name=entree format=time caps={caps} ! videoconvert ! video/x-raw,format=I420 "
    if debit_kbits is not None:
        description += (f"! x264enc bitrate={debit_kbits} tune=zerolatency speed-preset=ultrafast key-int-max=30 "
                        "! h264parse name=analyseur ! avdec_h264 ")
    description += "! videoconvert ! video/x-raw,format=GRAY8 ! appsink name=sortie sync=false"

    pipeline = Gst.parse_launch(description)
    entree = pipeline.get_by_name("entree")
    sortie = pipeline.get_by_name("sortie")

    # --- Sonde pour compter les octets H.264 -------------------------------------------
    # Un "pad" est un point de connexion d'un élément. On accroche une fonction (une "probe")
    # sur la sortie (src) de h264parse : elle est appelée pour CHAQUE buffer qui passe.
    octets = [0]                                   # liste = astuce pour modifier depuis la fonction

    def compter(pad, info):
        octets[0] += info.get_buffer().get_size()  # taille du buffer H.264 en octets
        return Gst.PadProbeReturn.OK               # OK = laisser passer le buffer normalement

    if debit_kbits is not None:
        pad = pipeline.get_by_name("analyseur").get_static_pad("src")
        pad.add_probe(Gst.PadProbeType.BUFFER, compter)

    pipeline.set_state(Gst.State.PLAYING)

    # --- On pousse toutes les images -----------------------------------------------------
    duree = Gst.SECOND // FPS                      # durée d'une image en ns
    for i in range(n):
        # Gst.Buffer.new_wrapped : crée un buffer GStreamer à partir d'octets Python
        buf = Gst.Buffer.new_wrapped(sequence[i].tobytes())
        buf.pts = i * duree                        # timestamp de présentation
        buf.duration = duree
        entree.emit("push-buffer", buf)            # action signal : "voici une image"
    entree.emit("end-of-stream")                   # "plus d'images" -> l'encodeur vide ses tampons

    # --- On récupère les images décodées -------------------------------------------------
    decodees = []
    while True:
        sample = sortie.emit("try-pull-sample", 5 * Gst.SECOND)
        if sample is None:                         # None = fin du flux (ou rien depuis 5 s)
            break
        buf = sample.get_buffer()
        ok, carte = buf.map(Gst.MapFlags.READ)
        decodees.append(np.frombuffer(carte.data, np.uint8)[: h * l].reshape(h, l).copy())
        buf.unmap(carte)

    # Erreur éventuelle signalée sur le bus ?
    msg = pipeline.get_bus().timed_pop_filtered(0, Gst.MessageType.ERROR)
    pipeline.set_state(Gst.State.NULL)
    if msg is not None:
        raise RuntimeError(msg.parse_error()[0].message)
    return np.stack(decodees), octets[0]


def main():
    parser = argparse.ArgumentParser(description="Courbe débit / qualité H.264.")
    parser.add_argument("--debits", type=int, nargs="+", default=[250, 500, 1000, 2000, 4000],
                        help="débits cibles en kbit/s")
    args = parser.parse_args()
    dossier = resultats.dossier(MODULE)
    chemin_ref = dossier / "reference.npy"
    if not chemin_ref.exists():
        print("Pas de référence : lancez d'abord enregistre_reference.py")
        return
    ref = np.load(chemin_ref)
    n, h, l = ref.shape
    duree_s = n / FPS
    print(f"Référence : {n} images {l}x{h} ({duree_s:.1f} s)")

    # --- 1. Vérification de la chaîne de mesure ------------------------------------------
    sans_enc, _ = encoder_decoder(ref, None)
    p0 = np.mean([psnr(a, b) for a, b in zip(ref, sans_enc)])
    print(f"Vérification sans encodeur : PSNR = {p0} dB (doit être 'inf')")
    if p0 != math.inf:
        print("  ATTENTION : la conversion de format modifie déjà l'image. Résultats à interpréter avec prudence.")

    # --- 2. Mesure pour chaque débit -------------------------------------------------------
    lignes = []
    exemples = {}
    for d in args.debits:
        dec, nb_octets = encoder_decoder(ref, d)
        m = min(len(dec), n)                       # sécurité si une image manquait
        psnrs = [psnr(ref[i], dec[i]) for i in range(m)]
        ssims = [ssim(ref[i], dec[i]) for i in range(m)]
        debit_reel = nb_octets * 8 / duree_s / 1000   # octets -> bits -> kbit/s
        lignes.append((d, debit_reel, float(np.mean(psnrs)), float(np.min(psnrs)), float(np.mean(ssims))))
        exemples[d] = dec[m // 2]
        print(f"  cible {d:5d} kbit/s | réel {debit_reel:7.0f} kbit/s | PSNR moy {np.mean(psnrs):5.2f} dB "
              f"(min {np.min(psnrs):5.2f}) | SSIM {np.mean(ssims):.4f}")

    # --- 3. Graphiques ---------------------------------------------------------------------
    reel = [x[1] for x in lignes]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    a1.plot(reel, [x[2] for x in lignes], "o-", label="PSNR moyen")
    a1.plot(reel, [x[3] for x in lignes], "s--", alpha=0.6, label="PSNR de la pire image")
    a1.set_xscale("log")                           # échelle log : chaque doublement de débit = même pas
    a1.set_xlabel("Débit réel (kbit/s)")
    a1.set_ylabel("PSNR (dB)")
    a1.set_title(f"Débit / qualité H.264 ({l}x{h})")
    a1.grid(alpha=0.3, which="both")
    a1.legend()
    a2.plot(reel, [x[4] for x in lignes], "o-", color="C2")
    a2.set_xscale("log")
    a2.set_xlabel("Débit réel (kbit/s)")
    a2.set_ylabel("SSIM")
    a2.set_title("SSIM en fonction du débit")
    a2.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(dossier / "courbe_debit_qualite.png", dpi=120)

    # Comparaison visuelle : référence | débit le plus bas | débit le plus haut (même image)
    milieu = ref[n // 2]
    bande = np.hstack([milieu, exemples[min(args.debits)], exemples[max(args.debits)]])
    cv2.imwrite(str(dossier / "comparaison_visuelle.png"), bande)
    print(f"Graphique : {dossier / 'courbe_debit_qualite.png'}")
    print(f"Comparaison visuelle (réf | {min(args.debits)} | {max(args.debits)} kbit/s) : "
          f"{dossier / 'comparaison_visuelle.png'}")

    resultats.ecrire_resume(MODULE, "courbe", {
        "resolution": f"{l}x{h}",
        "verification_chaine_psnr_db": "inf" if p0 == math.inf else round(p0, 2),
        "mesures": [{"cible_kbits": d, "reel_kbits": round(r), "psnr_moyen_db": round(p, 2),
                     "psnr_min_db": round(pm, 2), "ssim": round(s, 4)} for d, r, p, pm, s in lignes],
    })


if __name__ == "__main__":
    main()
