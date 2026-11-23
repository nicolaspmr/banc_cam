"""
module1_latence/mesure_latence.py — Latence "glass-to-glass" automatisée.

Principe (même horloge pour tout -> pas de problème de synchronisation) :
  1. Le script affiche une fenêtre qui passe du NOIR au BLANC (et inversement) à des instants connus.
  2. La caméra filme cette fenêtre (via un miroir si la webcam est intégrée à l'écran).
  3. Le flux fait le trajet complet : caméra -> encodage H.264 (Windows) -> RTP/UDP -> décodage (WSL).
  4. Un "thread" surveille la luminosité d'une petite zone de l'image reçue (la ROI) et détecte
     l'instant où elle bascule.
  5. Latence = instant de détection - instant du changement d'affichage.

Ce qui est inclus dans la mesure (c'est voulu, c'est "glass to glass") :
  rafraîchissement de l'écran + exposition caméra + transfert USB + encodage + réseau
  + jitterbuffer + décodage.
Limite de résolution : on ne voit le changement qu'à la réception d'une image, soit toutes
les ~33 ms à 30 i/s. Chaque mesure contient donc une erreur aléatoire de 0 à 33 ms : c'est
pour ça qu'on répète la mesure ~100 fois et qu'on regarde la distribution.

Lancement (depuis banc_cam/, émetteur déjà lancé) :
    python3 -m module1_latence.mesure_latence --cycles 100 --etiquette standard_3000k
"""

import argparse
import csv
import random            # tirage aléatoire des instants de bascule
import threading         # pour recevoir les images EN PARALLÈLE de l'affichage
import time

import cv2               # OpenCV : affichage de fenêtres + traitement d'image
import numpy as np

from commun.recepteur import Recepteur
from commun import resultats

MODULE = "module1_latence"
FENETRE = "mire_latence"


class Surveillant(threading.Thread):
    """
    Thread qui reçoit les images en continu et note (instant, luminosité de la ROI).
    Pourquoi un thread ? Le programme principal est occupé à afficher la mire et à attendre.
    Si on lisait les images seulement entre deux affichages, on les horodaterait en retard.
    """

    def __init__(self, recepteur):
        super().__init__(daemon=True)   # daemon=True : le thread s'arrête avec le programme
        self.rec = recepteur
        self.verrou = threading.Lock()  # protège les données partagées entre les deux threads
        self.roi = None                 # (x, y, largeur, hauteur) de la zone surveillée
        self.mesures = []               # liste de (t, luminosité moyenne dans la ROI)
        self.dernieres_images = []      # images récentes, utilisées pendant le calibrage
        self.actif = True

    def run(self):                      # run() est appelé automatiquement par .start()
        while self.actif:
            img = self.rec.lire(timeout_s=0.5)
            if img is None:
                continue
            with self.verrou:           # "with verrou" : un seul thread à la fois dans ce bloc
                if self.roi is None:
                    # Pendant le calibrage on garde les images (au plus 60) pour les moyenner
                    self.dernieres_images.append((img.t, img.pixels))
                    self.dernieres_images = self.dernieres_images[-60:]
                else:
                    x, y, l, h = self.roi
                    zone = img.pixels[y:y + h, x:x + l]   # découpe NumPy [lignes, colonnes]
                    self.mesures.append((img.t, float(zone.mean())))

    def images_depuis(self, t):
        """Renvoie la moyenne des images reçues après l'instant t (pour le calibrage)."""
        with self.verrou:
            imgs = [p for (ti, p) in self.dernieres_images if ti > t]
        if not imgs:
            return None
        # np.stack empile les images en un bloc 3D (N, h, l) ; mean(axis=0) moyenne image par image
        return np.stack(imgs).astype(np.float32).mean(axis=0)


def afficher(niveau, taille):
    """Affiche une image uniforme (0 = noir, 255 = blanc) et renvoie l'instant d'affichage."""
    # np.full crée une image remplie d'une seule valeur
    cv2.imshow(FENETRE, np.full((taille, taille), niveau, dtype=np.uint8))
    # waitKey(1) : laisse 1 ms à la fenêtre pour se redessiner (sans lui, rien ne s'affiche !)
    cv2.waitKey(1)
    return time.perf_counter()


def attendre(duree_s):
    """Attend en gardant la fenêtre réactive (waitKey traite les événements de la fenêtre)."""
    fin = time.perf_counter() + duree_s
    while time.perf_counter() < fin:
        if cv2.waitKey(5) & 0xFF == ord("q"):   # touche q = abandon
            raise KeyboardInterrupt


def calibrer(surv, taille, dossier):
    """
    Trouve automatiquement OÙ est la mire dans l'image de la caméra.
    Méthode : image moyenne quand la mire est blanche - image moyenne quand elle est noire.
    Les pixels qui changent beaucoup = la mire. On en prend le rectangle englobant.
    """
    print("Calibrage : la fenêtre va passer au blanc puis au noir (2 s chacun)...")
    t = afficher(255, taille)
    attendre(2.0)
    blanc = surv.images_depuis(t + 1.0)     # on ignore la 1re seconde (latence + expo auto)
    t = afficher(0, taille)
    attendre(2.0)
    noir = surv.images_depuis(t + 1.0)
    if blanc is None or noir is None:
        raise RuntimeError("Pas d'images reçues pendant le calibrage : l'émetteur tourne-t-il ?")

    diff = blanc - noir                      # grand là où la mire est visible
    seuil_diff = 0.5 * np.percentile(diff, 99.5)   # moitié du changement "max" (robuste au bruit)
    masque = (diff > seuil_diff).astype(np.uint8)
    # findContours trouve les zones blanches du masque ; on garde la plus grande (contourArea)
    contours, _ = cv2.findContours(masque, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise RuntimeError("Mire introuvable dans l'image : la caméra voit-elle la fenêtre ?")
    plus_grand = max(contours, key=cv2.contourArea)
    x, y, l, h = cv2.boundingRect(plus_grand)   # rectangle englobant (x, y, largeur, hauteur)
    # On rétrécit le rectangle de 20 % de chaque côté pour éviter les bords flous
    x, y, l, h = x + l // 5, y + h // 5, max(1, l * 3 // 5), max(1, h * 3 // 5)

    niveau_blanc = float(blanc[y:y + h, x:x + l].mean())
    niveau_noir = float(noir[y:y + h, x:x + l].mean())
    contraste = niveau_blanc - niveau_noir
    print(f"  ROI trouvée : x={x} y={y} {l}x{h} px | noir = {niveau_noir:.1f} | blanc = {niveau_blanc:.1f}")
    if contraste < 20:
        raise RuntimeError(f"Contraste trop faible ({contraste:.1f}) : rapprochez la caméra / le miroir, "
                           "augmentez la luminosité de l'écran.")

    # Image de contrôle : ce que voit la caméra, avec la ROI en rectangle -> à vérifier à l'œil !
    controle = cv2.cvtColor(blanc.astype(np.uint8), cv2.COLOR_GRAY2BGR)
    cv2.rectangle(controle, (x, y), (x + l, y + h), (0, 0, 255), 3)
    cv2.imwrite(str(dossier / "controle_roi.png"), controle)
    print(f"  Image de contrôle : {dossier / 'controle_roi.png'}")
    return (x, y, l, h), niveau_noir, niveau_blanc


def detecter(mesures, t_bascule, t_fin, seuil, vers_blanc):
    """Premier instant après t_bascule où la luminosité franchit le seuil dans le bon sens."""
    for t, lum in mesures:
        if t_bascule < t < t_fin:
            if (vers_blanc and lum > seuil) or (not vers_blanc and lum < seuil):
                return t
    return None


def main():
    parser = argparse.ArgumentParser(description="Mesure de latence glass-to-glass.")
    parser.add_argument("--cycles", type=int, default=100, help="nombre de bascules mesurées")
    parser.add_argument("--etiquette", default="standard", help="nom de la configuration testée")
    parser.add_argument("--taille", type=int, default=500, help="taille de la fenêtre-mire (px)")
    parser.add_argument("--attente-min", type=float, default=0.8, help="attente min entre bascules (s)")
    parser.add_argument("--attente-max", type=float, default=1.3, help="attente max entre bascules (s)")
    args = parser.parse_args()
    dossier = resultats.dossier(MODULE)

    # namedWindow + WINDOW_NORMAL : fenêtre redimensionnable ; on la place en haut à gauche
    cv2.namedWindow(FENETRE, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(FENETRE, args.taille, args.taille)
    cv2.moveWindow(FENETRE, 0, 0)
    afficher(0, args.taille)

    rec = Recepteur(format="GRAY8", garder_que_la_derniere=True).demarrer()
    rec.attendre_flux()
    surv = Surveillant(rec)
    surv.start()                                  # lance run() dans un thread séparé

    lignes = []
    try:
        roi, noir, blanc = calibrer(surv, args.taille, dossier)
        seuil = (noir + blanc) / 2                # bascule détectée à mi-chemin noir/blanc
        with surv.verrou:
            surv.roi = roi                        # à partir d'ici le thread mesure la ROI

        print(f"Mesure de {args.cycles} bascules (touche q dans la fenêtre pour arrêter)...")
        niveau = 0
        for i in range(args.cycles):
            # Attente ALÉATOIRE avant chaque bascule : si l'attente était fixe, la bascule tomberait
            # toujours au même moment par rapport aux images de la caméra -> biais de mesure.
            attendre(random.uniform(args.attente_min, args.attente_max))
            niveau = 255 - niveau                 # alterne noir <-> blanc
            t_bascule = afficher(niveau, args.taille)
            # On laisse le temps au changement de traverser la chaîne avant de chercher
            attendre(args.attente_min * 0.9)
            with surv.verrou:
                copie = list(surv.mesures)
            t_det = detecter(copie, t_bascule, time.perf_counter(), seuil, vers_blanc=(niveau == 255))
            sens = "noir->blanc" if niveau == 255 else "blanc->noir"
            if t_det is None:
                print(f"  [{i + 1:3d}] {sens} : non détectée")
                lignes.append([i + 1, sens, ""])
            else:
                latence_ms = (t_det - t_bascule) * 1000
                print(f"  [{i + 1:3d}] {sens} : {latence_ms:6.1f} ms")
                lignes.append([i + 1, sens, f"{latence_ms:.2f}"])
    except KeyboardInterrupt:
        print("Arrêt demandé.")
    finally:
        surv.actif = False
        rec.arreter()
        cv2.destroyAllWindows()

    # --- Statistiques ------------------------------------------------------
    lat = np.array([float(l[2]) for l in lignes if l[2] != ""])
    chemin_csv = dossier / f"latence_{args.etiquette}.csv"
    with open(chemin_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cycle", "sens", "latence_ms"])
        w.writerows(lignes)
    print(f"Données brutes : {chemin_csv}")
    if len(lat) == 0:
        print("Aucune bascule détectée.")
        return

    # np.percentile(lat, 95) : 95 % des mesures sont en dessous de cette valeur
    stats = {
        "mesures_valides": int(len(lat)),
        "non_detectees": int(len(lignes) - len(lat)),
        "latence_moyenne_ms": round(float(lat.mean()), 1),
        "ecart_type_ms": round(float(lat.std(ddof=1)) if len(lat) > 1 else 0.0, 1),
        "mediane_ms": round(float(np.median(lat)), 1),
        "p95_ms": round(float(np.percentile(lat, 95)), 1),
        "min_ms": round(float(lat.min()), 1),
        "max_ms": round(float(lat.max()), 1),
        # Incertitude-type sur la MOYENNE = écart-type / racine(N) (loi en 1/sqrt(N))
        "incertitude_moyenne_ms": round(float(lat.std(ddof=1) / np.sqrt(len(lat))) if len(lat) > 1 else 0.0, 1),
    }
    print("\n=== Résultats ===")
    for cle, val in stats.items():
        print(f"  {cle:24s}: {val}")
    resultats.ecrire_resume(MODULE, args.etiquette, stats)


if __name__ == "__main__":
    main()
