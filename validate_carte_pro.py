"""
DNoVy — Validation carte professionnelle d'éducateur sportif.

Pipeline :
  1. Extraction VLM locale (LM Studio, aucune donnée ne sort du LAN)
  2. Vérification officielle API EME (Ministère des Sports)
  3. Persistance Supabase

Usage :
  python validate_carte_pro.py <chemin_image>
"""
import os
import sys
import json
import re
from typing import Optional

import litellm
import requests
import yaml
from pydantic import Field
from dotenv import load_dotenv
from extract_thinker import Extractor, LLM, Contract

load_dotenv()

LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://192.168.1.181:12000/v1")
MODEL_NAME = os.getenv("VLM_MODEL", "qwen/qwen3-vl-4b")
EME_ENDPOINT = "https://eme-api-core.sports.gouv.fr/api/Educateur/GetAllPubliEdu"

litellm.api_base = LMSTUDIO_BASE_URL
litellm.api_key = "local"


class CarteCoach(Contract):
    nom: str = Field(description="Nom de famille")
    prenom: str = Field(description="Prénom")
    numero_carte: str = Field(description="Numéro de carte professionnelle")
    nationalite: Optional[str] = Field(default=None, description="Nationalité")
    date_naissance: Optional[str] = Field(default=None, description="Date de naissance JJ/MM/AAAA")
    lieu_naissance: Optional[str] = Field(default=None, description="Lieu de naissance")


def verifier_carte(nom: str, prenom: str, numero_carte: str) -> dict:
    """Interroge l'API EME. Retourne valide + qualifications brutes pour recoupement diplôme."""
    try:
        r = requests.post(
            EME_ENDPOINT,
            json={
                "nomFamille": nom,
                "prenom": prenom,
                "cartePro": numero_carte,
                "itemByPage": 10,
                "numeroPage": 0,
                "typeUser": "EducUser",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        nb = data.get("nbResults", 0)
        educateurs = data.get("educateurs", [])
        qualifs = educateurs[0].get("qualifications", []) if educateurs else []
        return {"valide": nb > 0, "nb_resultats": nb, "qualifications": qualifs}
    except requests.RequestException as e:
        print(f"  ⚠️  Erreur API EME : {e}")
        return {"valide": False, "nb_resultats": 0, "qualifications": []}


def process_carte(carte_path: str) -> Optional[dict]:
    """Pipeline complet image → VLM → EME → Supabase. Utilisé par orchestrator.py."""
    from supabase import create_client
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY missing in environment")
    supabase = create_client(supabase_url, supabase_key)

    print(f"\n📄 Traitement : {os.path.basename(carte_path)}")
    extractor = Extractor()
    extractor.load_llm(LLM(f"openai/{MODEL_NAME}"))
    result = extractor.extract(carte_path, CarteCoach, vision=True)

    try:
        carte = json.loads(result.model_dump_json())
        print(yaml.dump(carte, allow_unicode=True))

        verification = verifier_carte(carte["nom"], carte["prenom"], carte.get("numero_carte", ""))
        carte["valide"] = verification["valide"]
        carte["qualifications_eme"] = json.dumps(verification["qualifications"], ensure_ascii=False)
        carte["fichier"] = os.path.basename(carte_path)

        statut = "✅ VALIDE" if carte["valide"] else "❌ INVALIDE"
        print(f"  Carte : {statut} ({verification['nb_resultats']} résultat(s) EME)")

        try:
            supabase.table("cartes_coach").upsert(carte, on_conflict="numero_carte").execute()
        except Exception as e:
            message = str(e)
            match = re.search(r"Could not find the '([^']+)' column", message)
            if match:
                missing_column = match.group(1)
                if missing_column in carte:
                    print(f"  ⚠️  Colonne Supabase manquante : {missing_column}. Retrait et nouvel essai.")
                    carte.pop(missing_column, None)
                    supabase.table("cartes_coach").upsert(carte, on_conflict="numero_carte").execute()
                else:
                    raise
            else:
                raise

        print("  💾 Sauvegardé dans Supabase (table: cartes_coach)")
        return carte

    except (json.JSONDecodeError, ValueError) as e:
        print(f"  ❌ Erreur extraction : {e}")
        return None


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "carte_coach/files/cartes/carte-pro.jpg"
    if not os.path.exists(path):
        sys.exit(f"Fichier introuvable : {path}")
    process_carte(path)
