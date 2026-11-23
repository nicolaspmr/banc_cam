"""
commun/resultats.py — Sauvegarde et relecture des résultats des modules.

Convention du banc : chaque module écrit dans resultats/<module>/ :
  - ses fichiers bruts (CSV, images, .npy) ;
  - un fichier resume_<etiquette>.json avec ses chiffres clés.
La synthèse (synthese/fiche_camera.py) relit tous les resume_*.json pour faire la fiche caméra.
C'est ce mécanisme qui RELIE les modules entre eux.
"""

import json                     # lecture/écriture de fichiers JSON (dictionnaires Python <-> texte)
import platform                 # infos sur la machine (pour tracer les conditions de mesure)
from datetime import datetime   # date et heure de la mesure

import config


def dossier(module):
    """Renvoie (et crée si besoin) le dossier resultats/<module>/."""
    d = config.DOSSIER_RESULTATS / module
    # mkdir(parents=True, exist_ok=True) : crée aussi les dossiers parents, sans erreur s'il existe déjà
    d.mkdir(parents=True, exist_ok=True)
    return d


def ecrire_resume(module, etiquette, valeurs):
    """
    Écrit resultats/<module>/resume_<etiquette>.json.
    `valeurs` est un dictionnaire de chiffres clés, par ex. {"fps_mesure": 30.1}.
    On ajoute automatiquement la date et la machine : une mesure sans ses conditions ne vaut rien.
    """
    contenu = {
        "module": module,
        "etiquette": etiquette,
        "date": datetime.now().isoformat(timespec="seconds"),
        "machine": platform.node(),
        "valeurs": valeurs,
    }
    chemin = dossier(module) / f"resume_{etiquette}.json"
    # json.dumps(..., indent=2) : texte JSON lisible ; ensure_ascii=False garde les accents
    chemin.write_text(json.dumps(contenu, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Résumé écrit : {chemin.relative_to(config.RACINE)}")
    return chemin


def lire_resumes(module=None):
    """Relit tous les resume_*.json (d'un module, ou de tous si module=None)."""
    motif = f"{module}/resume_*.json" if module else "*/resume_*.json"
    # glob() liste les fichiers qui correspondent au motif ; sorted() pour un ordre stable
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(config.DOSSIER_RESULTATS.glob(motif))]


def lire_etalonnage():
    """
    Relit un étalonnage caméra (focale, distorsion) s'il existe. Renvoie None sinon.
    Utilisé en option par le module 5 pour convertir des pixels en angles.
    (Le module d'étalonnage a été retiré du banc : sans lui, le module 5 travaille en pixels.)
    """
    chemin = config.DOSSIER_RESULTATS / "module2_etalonnage" / "etalonnage.json"
    if not chemin.exists():
        return None
    return json.loads(chemin.read_text(encoding="utf-8"))
