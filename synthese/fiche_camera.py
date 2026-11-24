"""
synthese/fiche_camera.py — Assemble la FICHE CAMÉRA à partir des résultats de tous les modules.

C'est l'aboutissement du banc : comme une fiche de caractérisation de charge utile, une page
qui résume, pour UNE caméra, tout ce que les modules ont mesuré, avec leurs conditions.
Chaque module a écrit des resultats/<module>/resume_<etiquette>.json (voir commun/resultats.py) ;
ce script les relit tous et écrit resultats/fiche_camera.md (lisible sur GitHub).

Lancement :  python3 -m synthese.fiche_camera --camera "USB2.0 FHD UVC WebCam"
"""

import argparse
from datetime import date

import config
from commun import resultats

# Titre lisible de chaque module, dans l'ordre de la fiche
TITRES = {
    "module1_chaine": "Chaîne vidéo (cadence, gigue, pertes)",
    "module2_debit_qualite": "Débit / qualité H.264",
    "module3_bruit": "Bruit",
}


def formater(valeur):
    """Met une valeur en forme pour un tableau Markdown."""
    if isinstance(valeur, list):            # ex. la liste des mesures du module 2
        return "voir détail"
    return str(valeur)


def main():
    parser = argparse.ArgumentParser(description="Génère la fiche caméra.")
    parser.add_argument("--camera", default="Webcam", help="nom de la caméra caractérisée")
    args = parser.parse_args()

    tous = resultats.lire_resumes()          # tous les resume_*.json de tous les modules
    lignes = [f"# Fiche de caractérisation — {args.camera}", "",
              f"Générée le {date.today().isoformat()} par le mini-banc GStreamer.", ""]

    for module, titre in TITRES.items():
        resumes = [r for r in tous if r["module"] == module]
        lignes += [f"## {titre}", ""]
        if not resumes:
            lignes += ["*Pas encore mesuré.*", ""]
            continue
        for r in resumes:
            lignes += [f"**Condition : {r['etiquette']}** (mesuré le {r['date']})", "",
                       "| Grandeur | Valeur |", "| --- | --- |"]
            for cle, val in r["valeurs"].items():
                lignes.append(f"| {cle} | {formater(val)} |")
            lignes.append("")
            # Détail spécial pour la courbe débit/qualité (liste de mesures)
            if module == "module2_debit_qualite" and "mesures" in r["valeurs"]:
                lignes += ["| Débit cible (kbit/s) | Débit réel (kbit/s) | PSNR moyen (dB) | SSIM |",
                           "| --- | --- | --- | --- |"]
                for m in r["valeurs"]["mesures"]:
                    lignes.append(f"| {m['cible_kbits']} | {m['reel_kbits']} | {m['psnr_moyen_db']} | {m['ssim']} |")
                lignes.append("")

    lignes += ["## Limites connues", "",
               "- La webcam applique un traitement interne (exposition auto, gamma, débruitage, MJPEG) : "
               "les mesures portent sur toute la chaîne, pas sur le capteur brut.",
               ""]

    chemin = config.DOSSIER_RESULTATS / "fiche_camera.md"
    chemin.write_text("\n".join(lignes), encoding="utf-8")
    print("\n".join(lignes))
    print(f"\nFiche écrite : {chemin}")


if __name__ == "__main__":
    main()
