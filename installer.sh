#!/usr/bin/env bash
# =============================================================================
# installer.sh — Installe tout ce dont le banc a besoin sous WSL (Ubuntu 24.04).
# À lancer une fois :  bash installer.sh
# =============================================================================
set -e   # arrête le script à la première erreur

sudo apt update
# GStreamer + plugins, le pont Python<->GStreamer (python3-gi + gir1.2-*),
# NumPy (calcul), OpenCV (traitement d'image), Matplotlib (graphiques)
sudo apt install -y gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-x \
  python3-gi gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  python3-numpy python3-opencv python3-matplotlib git

# Autorise un gros tampon de réception UDP (sinon pertes de paquets en profil sans perte).
# À refaire après chaque redémarrage de WSL (ou ajouter la ligne dans /etc/sysctl.conf).
sudo sysctl -w net.core.rmem_max=26214400

# Rend les scripts d'émetteur exécutables
chmod +x emetteur/*.sh

echo "Installation terminée. Test rapide :"
python3 -c "import gi, numpy, cv2, matplotlib; gi.require_version('Gst','1.0'); from gi.repository import Gst; Gst.init(None); print('OK', Gst.version_string())"
