#!/usr/bin/env bash
# =============================================================================
# emetteur/lancer_emetteur.sh — Le "drone" : capture la webcam SOUS WINDOWS et
# l'envoie en RTP/H.264 vers WSL. Se lance DEPUIS un terminal WSL.
#
# Astuce : WSL sait exécuter les programmes Windows (.exe). On appelle donc
# directement le gst-launch-1.0.exe installé côté Windows : il a accès à la webcam,
# et on n'a plus à se battre avec les guillemets de PowerShell.
#
# Utilisation (depuis le dossier banc_cam) :
#   ./emetteur/lancer_emetteur.sh                  -> profil "standard", 3000 kbit/s
#   ./emetteur/lancer_emetteur.sh standard 1000    -> profil standard, 1000 kbit/s
#   ./emetteur/lancer_emetteur.sh sans_perte       -> H.264 sans perte (pour les pistes d'étude : bruit, qualité)
# Arrêt : Ctrl+C
# =============================================================================

PROFIL="${1:-standard}"     # ${1:-standard} = 1er argument, ou "standard" s'il est absent
DEBIT="${2:-3000}"          # débit cible en kbit/s

# Chemin du GStreamer Windows vu depuis WSL (le disque C: est monté sur /mnt/c)
GST="/mnt/c/Program Files/gstreamer/1.0/msvc_x86_64/bin/gst-launch-1.0.exe"
if [ ! -f "$GST" ]; then
  echo "GStreamer Windows introuvable : $GST"
  echo "Vérifiez le dossier d'installation et corrigez la variable GST dans ce script."
  exit 1
fi

# IP de WSL : c'est là que Windows doit envoyer les paquets.
# hostname -I liste les IP de la machine ; awk '{print $1}' garde la première.
IP_WSL=$(hostname -I | awk '{print $1}')
PORT=5000

case "$PROFIL" in
  standard)
    # 1280x720 à 30 i/s (format NV12 proposé par mfvideosrc, voir gst-device-monitor)
    CAPS="video/x-raw,format=NV12,width=1280,height=720,framerate=30/1"
    # tune=zerolatency : pas de B-frames ni d'anticipation -> latence minimale
    # speed-preset=ultrafast : encodage le plus rapide (moins efficace en compression)
    # key-int-max=30 : une I-frame (image complète) au moins toutes les 30 images = 1 s
    ENC="x264enc tune=zerolatency speed-preset=ultrafast bitrate=$DEBIT key-int-max=30"
    ;;
  sans_perte)
    # H.264 SANS PERTE (quantizer=0) : l'image décodée est identique bit à bit à l'image encodée.
    # Indispensable pour mesurer un jour le bruit ou faire une référence de qualité :
    # sinon la compression lisse le bruit et fausse la mesure.
    # 640x480 seulement : en sans perte le débit est énorme (plusieurs dizaines de Mbit/s).
    CAPS="video/x-raw,format=NV12,width=640,height=480,framerate=30/1"
    ENC="x264enc pass=quant quantizer=0 speed-preset=ultrafast tune=zerolatency key-int-max=30"
    ;;
  *)
    echo "Profil inconnu : $PROFIL (choix : standard, sans_perte)"; exit 1 ;;
esac

echo "Profil $PROFIL -> envoi vers $IP_WSL:$PORT   (Ctrl+C pour arrêter)"

# Le pipeline émetteur :
#   mfvideosrc        : la webcam via Media Foundation (Windows)
#   $CAPS             : impose résolution, format, cadence
#   videoconvert      : conversion de format si l'encodeur en a besoin
#   $ENC              : encodage H.264
#   rtph264pay        : découpe le flux H.264 en paquets RTP ; config-interval=1 renvoie
#                       les paramètres SPS/PPS chaque seconde (un récepteur lancé en retard s'y retrouve)
#   udpsink           : envoie les paquets en UDP vers WSL
# On n'écrit pas les "!" entre guillemets : chaque mot est un argument passé au .exe.
"$GST" mfvideosrc ! $CAPS ! videoconvert ! $ENC \
  ! rtph264pay config-interval=1 pt=96 ! udpsink host="$IP_WSL" port=$PORT
