"""
emetteur/camera_virtuelle.py — Une caméra SIMULÉE dont on connaît le bruit (vérité terrain).

Sert à valider le module 4 : si mesure_bruit.py + courbe_transfert.py retrouvent le gain
et le bruit de lecture qu'on a programmés ici, la méthode est juste.

Modèle physique simulé, pour chaque pixel et chaque image :
    électrons = Poisson(niveau_idéal / K)        bruit photonique (loi de Poisson)
    sortie    = K x électrons + N(0, bruit_lecture)   conversion + bruit de lecture gaussien
Donc : variance = K x niveau + bruit_lecture²  -> pente K, ordonnée bruit_lecture².

La scène est un dégradé horizontal (tous les niveaux de 10 à 245) + quelques motifs fixes.
Envoi en H.264 SANS PERTE vers le port 5000, comme l'émetteur Windows.

Lancement :  python3 -m emetteur.camera_virtuelle --gain 0.5 --bruit-lecture 1.5
"""

import argparse
import time

import numpy as np
import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

Gst.init(None)


def main():
    parser = argparse.ArgumentParser(description="Caméra virtuelle à bruit connu.")
    parser.add_argument("--gain", type=float, default=0.5, help="K en DN par électron")
    parser.add_argument("--bruit-lecture", type=float, default=1.5, help="bruit de lecture (DN RMS)")
    parser.add_argument("--hote", default="127.0.0.1")
    args = parser.parse_args()
    l, h, fps = 640, 480, 30

    # Scène idéale (sans bruit) : dégradé horizontal de 10 à 245
    scene = np.tile(np.linspace(10, 245, l), (h, 1))
    rng = np.random.default_rng()

    pipeline = Gst.parse_launch(
        f"appsrc name=src is-live=true format=time caps=video/x-raw,format=GRAY8,width={l},height={h},framerate={fps}/1 "
        "! videoconvert ! video/x-raw,format=I420 "
        "! x264enc pass=quant quantizer=0 speed-preset=ultrafast tune=zerolatency key-int-max=30 "
        f"! rtph264pay config-interval=1 pt=96 ! udpsink host={args.hote} port=5000")
    src = pipeline.get_by_name("src")
    pipeline.set_state(Gst.State.PLAYING)
    print(f"Caméra virtuelle : K = {args.gain} DN/e-, bruit de lecture = {args.bruit_lecture} DN (Ctrl+C pour arrêter)")
    print(f"Attendu : pente = {args.gain}, ordonnée = {args.bruit_lecture ** 2:.2f} DN²")

    i, debut = 0, time.perf_counter()
    try:
        while True:
            electrons = rng.poisson(scene / args.gain)                       # tirage de Poisson
            img = args.gain * electrons + rng.normal(0, args.bruit_lecture, scene.shape)
            img = np.clip(np.round(img), 0, 255).astype(np.uint8)            # quantification 8 bits
            buf = Gst.Buffer.new_wrapped(img.tobytes())
            buf.pts = i * Gst.SECOND // fps
            buf.duration = Gst.SECOND // fps
            src.emit("push-buffer", buf)
            i += 1
            # On attend l'heure de l'image suivante pour tenir 30 i/s
            attente = debut + i / fps - time.perf_counter()
            if attente > 0:
                time.sleep(attente)
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.set_state(Gst.State.NULL)


if __name__ == "__main__":
    main()
