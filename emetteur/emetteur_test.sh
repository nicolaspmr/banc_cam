#!/usr/bin/env bash
# =============================================================================
# emetteur/emetteur_test.sh — Émetteur de TEST, entièrement dans WSL, sans caméra.
# Envoie une mire (videotestsrc) au lieu de la webcam. Sert à vérifier qu'un module
# fonctionne avant de brancher la vraie caméra.
#
# Utilisation : ./emetteur/emetteur_test.sh [motif] [debit_kbits]
#   motif : smpte (barres couleur, défaut), ball (balle qui bouge), snow (bruit pur)
# =============================================================================
MOTIF="${1:-smpte}"
DEBIT="${2:-3000}"
echo "Mire '$MOTIF' -> 127.0.0.1:5000  (Ctrl+C pour arrêter)"
# is-live=true : la mire se comporte comme une caméra (produit les images en temps réel)
# timeoverlay  : incruste l'horloge du flux dans l'image
gst-launch-1.0 videotestsrc is-live=true pattern="$MOTIF" \
  ! video/x-raw,width=1280,height=720,framerate=30/1 ! timeoverlay ! videoconvert \
  ! x264enc tune=zerolatency speed-preset=ultrafast bitrate="$DEBIT" key-int-max=30 \
  ! rtph264pay config-interval=1 pt=96 ! udpsink host=127.0.0.1 port=5000
