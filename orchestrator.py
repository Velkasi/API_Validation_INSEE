"""
DNoVy Orchestrator — Flux carte pro + SIRET.

Chaîne l'exécution minimale :
  1. process_carte(carte_pro_path) → extrait nom/prénom et vérifie la carte pro
  2. process_siret(...) → vérifie l'existence du SIRET via document ou recherche nom/prénom

Usage :
  python orchestrator.py <chemin_carte> [<chemin_siret>]

Ou modifier le chemin en dur ci-dessous.
"""
import os
import sys
from typing import Optional

from validate_carte_pro import process_carte
from validate_siret import process_siret


def run_orchestration(carte_path: str, siret_path: Optional[str] = None):
    """Exécute le pipeline minimal : carte professionnelle puis vérification SIRET."""
    
    print("\n" + "="*70)
    print("ORCHESTRATEUR DNoVy — Validation Carte Pro + SIRET")
    print("="*70)

    results = {
        "carte": None,
        "siret": None
    }

    # 1. Carte Pro (point de départ)
    print("\n[1/2] Validation Carte Pro")
    print("-" * 70)
    if os.path.exists(carte_path):
        try:
            results["carte"] = process_carte(carte_path)
        except Exception as e:
            print(f"❌ Erreur lors du traitement de la carte : {e}")
    else:
        print(f"❌ Carte introuvable : {carte_path}")

    # 2. SIRET
    print("\n[2/2] Validation SIRET")
    print("-" * 70)
    if siret_path:
        if os.path.exists(siret_path):
            try:
                results["siret"] = process_siret(siret_path)
            except Exception as e:
                print(f"❌ Erreur lors du traitement du SIRET : {e}")
        else:
            print(f"❌ SIRET introuvable : {siret_path}")
    elif results["carte"] and results["carte"].get("nom") and results["carte"].get("prenom"):
        print("  ℹ️  Aucun document SIRET fourni, recherche via nom/prénom extraits de la carte pro.")
        try:
            results["siret"] = process_siret(None, nom=results["carte"]["nom"], prenom=results["carte"]["prenom"])
        except Exception as e:
            print(f"❌ Erreur lors de la recherche SIRET par nom/prénom : {e}")
    else:
        print("⚠️  Aucune vérification SIRET disponible (ni document ni nom/prénom valide).")

    # Résumé final
    print("\n" + "="*70)
    print("📋 RÉSUMÉ FINAL")
    print("="*70)

    carte_ok = results["carte"] and results["carte"].get("valide")
    siret_ok = results["siret"] and results["siret"].get("valide")

    print(f"\n✅ Carte Pro      : {'VALIDE' if carte_ok else 'NON VALIDE'}")
    if results["carte"]:
        print(f"   • Nom/Prenom : {results['carte'].get('nom')} {results['carte'].get('prenom')}")
        print(f"   • Numéro carte : {results['carte'].get('numero_carte')}")

    print(f"\n✅ SIRET          : {'VALIDE' if siret_ok else 'NON VALIDE'}")
    if results["siret"]:
        print(f"   • Dénomination : {results['siret'].get('denomination', 'N/A')}")
        print(f"   • État : {results['siret'].get('etat_label', 'N/A')}")

    overall = carte_ok and siret_ok
    print(f"\n{'='*70}")
    print(f"🎯 RÉSULTAT GLOBAL : {'✅ VALIDÉ' if overall else '❌ À VÉRIFIER'}")
    print(f"{'='*70}\n")

    return results


if __name__ == "__main__":
    # MODIFY THESE LINES: Path to test images
    # Example:
    #   carte_path = "API/examples/placeholder.jpg"
    #   siret_path = "API/examples/placeholder.jpg"
    
    if len(sys.argv) == 3:
        carte_path = sys.argv[1]
        siret_path = sys.argv[2]
    elif len(sys.argv) == 2:
        carte_path = sys.argv[1]
        siret_path = None
    else:
        # Fallback path (modify as needed)
        carte_path = "carte_pro/files/carte-pro.jpg"
        siret_path = None

    run_orchestration(carte_path, siret_path=siret_path)
