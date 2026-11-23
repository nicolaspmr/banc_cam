"""
config.py — Réglages partagés par TOUS les modules du banc.

Idée : un seul endroit où changer le port, la résolution, etc.
Chaque script fait `import config` puis utilise `config.PORT`, `config.CAPS_RTP`...
Si vous changez la résolution de l'émetteur, changez-la ici aussi.
"""

from pathlib import Path  # Path = manipulation de chemins de fichiers, indépendante du système

# --- Réseau -----------------------------------------------------------------
# Port UDP sur lequel la station sol (WSL) écoute le flux envoyé par le "drone" (Windows).
PORT = 5000

# "Caps" RTP : décrivent le contenu des paquets qui arrivent sur le port UDP.
# udpsrc reçoit des octets bruts sans savoir ce que c'est : on doit lui dire
# "ce sont des paquets RTP contenant de la vidéo H.264, horloge à 90 kHz".
#   - payload=96     : numéro de type dynamique utilisé par rtph264pay côté émetteur
#   - clock-rate=90000 : horloge standard des timestamps RTP vidéo (90 kHz)
CAPS_RTP = "application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000"

# Latence du rtpjitterbuffer (ms) : temps pendant lequel on garde les paquets
# pour les remettre dans l'ordre. Plus grand = plus robuste, mais plus de latence.
LATENCE_JITTERBUFFER_MS = 50

# Taille du tampon de réception UDP du système (octets). Utile en profil sans perte
# (gros débit) pour ne pas perdre de paquets. Voir installer.sh (sysctl rmem_max).
TAMPON_UDP_OCTETS = 8 * 1024 * 1024

# --- Dossiers ---------------------------------------------------------------
# Path(__file__) = chemin de ce fichier ; .parent = le dossier banc_cam/
RACINE = Path(__file__).resolve().parent
DOSSIER_RESULTATS = RACINE / "resultats"   # l'opérateur / assemble des chemins
