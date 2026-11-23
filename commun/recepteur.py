"""
commun/recepteur.py — LA brique commune du banc : flux RTP/H.264 -> images NumPy.

Tous les modules l'utilisent. Elle fait trois choses :
  1. construire un pipeline GStreamer qui reçoit et décode le flux vidéo ;
  2. récupérer chaque image décodée dans Python grâce à l'élément `appsink` ;
  3. la convertir en tableau NumPy, horodatée à sa réception.

Pipeline construit (à comparer avec la commande gst-launch que vous connaissez) :

  udpsrc -> rtpjitterbuffer -> rtph264depay -> h264parse -> avdec_h264
         -> videoconvert -> (caps : format voulu) -> appsink

Utilisation type :

    from commun.recepteur import Recepteur
    with Recepteur(format="GRAY8") as rec:     # démarre le pipeline
        img = rec.lire()                        # attend une image (ou None)
        print(img.t, img.pixels.shape)          # instant de réception + tableau NumPy
    # en sortant du "with", le pipeline est arrêté proprement
"""

import time                                   # time.perf_counter() = horloge haute résolution
from dataclasses import dataclass             # pour définir une petite structure de données

import numpy as np
import gi                                     # "gi" = le pont entre Python et les bibliothèques GNOME/GStreamer

gi.require_version("Gst", "1.0")              # on exige GStreamer 1.x (et pas 0.10)
gi.require_version("GstVideo", "1.0")         # GstVideo : outils pour décrire une image vidéo
from gi.repository import Gst, GstVideo       # noqa: E402  (import après require_version, c'est voulu)

import config                                 # nos réglages partagés (port, caps...)

# Gst.init() initialise GStreamer : charge les plugins, lit les options.
# À faire UNE fois avant toute autre fonction GStreamer. Appeler deux fois ne pose pas de problème.
Gst.init(None)


@dataclass
class Image:
    """Une image reçue : ce que `Recepteur.lire()` renvoie."""
    t: float            # instant de réception (secondes, horloge time.perf_counter)
    pixels: np.ndarray  # tableau NumPy : (hauteur, largeur) en GRAY8, (h, l, 3) en BGR
    numero: int         # numéro de l'image depuis le démarrage (0, 1, 2...)
    pts_s: float        # timestamp de présentation GStreamer (s) — horloge du flux, pas du PC


class Recepteur:
    """Reçoit le flux RTP/H.264 envoyé par l'émetteur et fournit des images NumPy."""

    def __init__(self, port=config.PORT, format="GRAY8", garder_que_la_derniere=True,
                 latence_ms=config.LATENCE_JITTERBUFFER_MS):
        """
        port                   : port UDP d'écoute
        format                 : "GRAY8" (niveaux de gris, 1 octet/pixel) ou "BGR" (couleur, format d'OpenCV)
        garder_que_la_derniere : True  -> l'appsink ne garde que l'image la plus récente et jette les autres.
                                          Idéal pour un aperçu en direct (on veut l'image la plus fraîche).
                                 False -> l'appsink garde jusqu'à 300 images en file d'attente.
                                          Idéal pour enregistrer TOUTES les images (bruit, vibrations).
        latence_ms             : latence du jitterbuffer (voir config.py)
        """
        self.format = format
        self.nb_canaux = 1 if format == "GRAY8" else 3
        self.compteur = 0

        # Réglages de l'appsink selon l'usage :
        #   max-buffers : nombre max d'images en attente dans l'appsink
        #   drop        : que faire quand la file est pleine (true = jeter les plus anciennes)
        if garder_que_la_derniere:
            reglage_appsink = "max-buffers=1 drop=true"
        else:
            reglage_appsink = "max-buffers=300 drop=false"

        # La description textuelle du pipeline : EXACTEMENT la même syntaxe que gst-launch-1.0.
        #   - udpsrc buffer-size : taille du tampon de réception (évite les pertes à gros débit)
        #   - avdec_h264         : décodeur H.264 (issu de FFmpeg / libav)
        #   - videoconvert       : convertit le format décodé (I420) vers le format demandé
        #   - video/x-raw,format=... : "caps filter" qui force le format de sortie
        #   - appsink sync=false : livre chaque image dès qu'elle est décodée, sans attendre
        #                          son "heure" de présentation -> latence minimale
        description = (
            f'udpsrc port={port} buffer-size={config.TAMPON_UDP_OCTETS} caps="{config.CAPS_RTP}" '
            f"! rtpjitterbuffer latency={latence_ms} "
            "! rtph264depay ! h264parse ! avdec_h264 "
            f"! videoconvert ! video/x-raw,format={format} "
            f"! appsink name=sortie sync=false {reglage_appsink}"
        )

        # Gst.parse_launch() transforme le texte en un vrai pipeline (objet Gst.Pipeline),
        # en créant chaque élément et en les reliant ("!" = relier).
        self.pipeline = Gst.parse_launch(description)

        # get_by_name() retrouve un élément du pipeline par son nom (name=sortie ci-dessus)
        self.appsink = self.pipeline.get_by_name("sortie")

        # Le "bus" est la boîte aux lettres du pipeline : erreurs, fin de flux, changements d'état...
        self.bus = self.pipeline.get_bus()

    # ------------------------------------------------------------------ démarrage / arrêt
    def demarrer(self):
        # set_state(PLAYING) fait passer le pipeline par NULL -> READY -> PAUSED -> PLAYING.
        # Pour une source live (udpsrc), il n'y a pas de "preroll" : il attend simplement les paquets.
        self.pipeline.set_state(Gst.State.PLAYING)
        return self

    def arreter(self):
        # Revenir à NULL libère toutes les ressources (port UDP, décodeur, mémoire).
        self.pipeline.set_state(Gst.State.NULL)

    # "with Recepteur(...) as rec:" appelle __enter__ au début et __exit__ à la fin,
    # même si le programme plante ou si vous faites Ctrl+C : le pipeline est toujours arrêté.
    def __enter__(self):
        return self.demarrer()

    def __exit__(self, *exc):
        self.arreter()

    # ------------------------------------------------------------------ lecture d'une image
    def _verifier_erreurs(self):
        """Lit les messages d'erreur du bus sans bloquer et lève une exception s'il y en a."""
        # timed_pop_filtered(0, ...) : regarde s'il y a un message ERROR, attend 0 ns (= ne bloque pas)
        msg = self.bus.timed_pop_filtered(0, Gst.MessageType.ERROR)
        if msg is not None:
            erreur, details = msg.parse_error()   # parse_error() -> (GError, texte de debug)
            raise RuntimeError(f"Erreur GStreamer : {erreur.message}\n{details}")

    def lire(self, timeout_s=1.0):
        """
        Attend la prochaine image pendant au plus `timeout_s` secondes.
        Renvoie un objet Image, ou None si rien n'est arrivé (émetteur arrêté ?).
        """
        self._verifier_erreurs()

        # "try-pull-sample" est une "action signal" de l'appsink : on l'appelle avec emit().
        # Elle attend un échantillon au plus N nanosecondes (Gst.SECOND = 1e9 ns).
        # Un "sample" = un buffer (les octets de l'image) + ses caps (format, taille).
        sample = self.appsink.emit("try-pull-sample", int(timeout_s * Gst.SECOND))
        t_reception = time.perf_counter()        # on horodate AU PLUS TÔT après réception
        if sample is None:
            return None

        # Les caps du sample décrivent l'image : format, largeur, hauteur, et surtout le "stride".
        # VideoInfo.new_from_caps() lit ces caps et calcule la disposition mémoire.
        info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
        largeur, hauteur = info.width, info.height
        # stride = nombre d'octets par ligne EN MÉMOIRE. GStreamer arrondit souvent les lignes
        # à un multiple de 4 octets : une ligne peut donc contenir quelques octets de bourrage.
        stride = info.stride[0]

        buf = sample.get_buffer()                # le Gst.Buffer : les données + timestamps
        # buf.pts = timestamp de présentation (en ns) ; Gst.CLOCK_TIME_NONE s'il est absent
        pts_s = buf.pts / Gst.SECOND if buf.pts != Gst.CLOCK_TIME_NONE else float("nan")

        # map() donne accès aux octets du buffer en lecture (sans copie).
        ok, carte = buf.map(Gst.MapFlags.READ)
        if not ok:
            return None
        try:
            # np.frombuffer : vue NumPy sur les octets (pas de copie)
            brut = np.frombuffer(carte.data, dtype=np.uint8)
            # On découpe en lignes de `stride` octets, puis on enlève le bourrage de fin de ligne.
            lignes = brut[: hauteur * stride].reshape(hauteur, stride)
            pixels = lignes[:, : largeur * self.nb_canaux]
            if self.nb_canaux == 3:
                pixels = pixels.reshape(hauteur, largeur, 3)
            # .copy() est INDISPENSABLE : après unmap(), la mémoire du buffer peut être réutilisée.
            pixels = pixels.copy()
        finally:
            buf.unmap(carte)                     # on rend toujours la mémoire, même en cas d'erreur

        image = Image(t=t_reception, pixels=pixels, numero=self.compteur, pts_s=pts_s)
        self.compteur += 1
        return image

    def attendre_flux(self, timeout_s=30.0, message=True):
        """Bloque jusqu'à la première image (ou lève une erreur après timeout_s secondes)."""
        if message:
            print(f"En attente du flux sur le port UDP {config.PORT}... "
                  "(lancez l'émetteur si ce n'est pas fait)")
        debut = time.perf_counter()
        while time.perf_counter() - debut < timeout_s:
            img = self.lire(timeout_s=1.0)
            if img is not None:
                if message:
                    h, l = img.pixels.shape[:2]
                    print(f"Flux reçu : {l}x{h}, format {self.format}")
                return img
        raise TimeoutError("Aucune image reçue. Vérifiez l'émetteur, l'IP de WSL et le port.")
