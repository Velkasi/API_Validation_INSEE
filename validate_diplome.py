"""
DNoVy — Validation du diplôme par recoupement avec l'API EME.

Stratégie :
  1. Extraction VLM locale du diplôme
  2. Récupération des qualifications EME du coach (par nom/prénom)
  3. Calcul de similarité entre l'intitulé extrait et les qualifications officielles
  4. Validation si score ≥ seuil (0.6 par défaut)

Note de fragilité : SequenceMatcher est sensible aux libellés EME longs.
Pour améliorer le matching, prévoir une tokenisation/dictionnaire de synonymes
(BPJEPS, BEES, DEJEPS, DESJEPS, CQP, BP, BE…).
"""
import os
import sys
import json
import re
from difflib import SequenceMatcher
from typing import Optional

import requests
import yaml
from pydantic import Field
from dotenv import load_dotenv

import litellm
from supabase import create_client
from extract_thinker import Extractor, LLM, Contract

load_dotenv()

# LM Studio — VLM local
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://192.168.1.181:12000/v1")
MODEL_NAME = os.getenv("VLM_MODEL", "qwen/qwen3-vl-4b")
EME_ENDPOINT = "https://eme-api-core.sports.gouv.fr/api/Educateur/GetAllPubliEdu"

litellm.api_base = LMSTUDIO_BASE_URL
litellm.api_key = "local"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL or SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY missing in environment")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def json_to_yaml(json_dict):
    if not isinstance(json_dict, dict):
        raise ValueError("json_dict must be a dictionary")
    return yaml.dump(json_dict, allow_unicode=True)


class DiplomeContract(Contract):
    nom: str = Field(description="Nom de famille du titulaire")
    prenom: str = Field(description="Prénom du titulaire")
    intitule: Optional[str] = Field(default=None, description="Intitulé exact du diplôme")
    specialite: Optional[str] = Field(default=None, description="Spécialité ou mention")
    organisme: Optional[str] = Field(default=None, description="Organisme délivrant le diplôme")
    date_obtention: Optional[str] = Field(default=None, description="Date d'obtention JJ/MM/AAAA")
    niveau: Optional[str] = Field(default=None, description="Niveau (BPJEPS, DEJEPS, DESJEPS, licence, master…)")


def setup_extractor():
    extractor = Extractor()
    llm = LLM(f"openai/{MODEL_NAME}")
    extractor.load_llm(llm)
    return extractor


def get_qualifications_eme(nom: str, prenom: str) -> list[dict]:
    """Récupère les qualifications officielles via l'API EME."""
    try:
        r = requests.post(
            EME_ENDPOINT,
            json={
                "nomFamille": nom,
                "prenom": prenom,
                "itemByPage": 10,
                "numeroPage": 0,
                "typeUser": "EducUser",
            },
            timeout=10,
        )
        r.raise_for_status()
        educateurs = r.json().get("educateurs", [])
        return educateurs[0].get("qualifications", []) if educateurs else []
    except requests.RequestException as e:
        print(f"  ⚠️  Erreur API EME : {e}")
        return []


def _similarite(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def verifier_diplome(diplome: dict, seuil: float = 0.6) -> dict:
    """Croise diplôme extrait avec qualifications EME, retourne best match + score."""
    nom = diplome.get("nom", "")
    prenom = diplome.get("prenom", "")
    intitule = diplome.get("intitule", "") or ""
    specialite = diplome.get("specialite", "") or ""
    niveau = diplome.get("niveau", "") or ""

    qualifications = get_qualifications_eme(nom, prenom)
    if not qualifications:
        return {
            "valide": False,
            "message": "Aucune qualification trouvée dans EME pour cet éducateur",
            "best_match": None,
            "score": 0.0,
            "qualifications_eme": [],
        }

    recherche = " ".join(filter(None, [intitule, specialite, niveau]))
    best_score, best_match = 0.0, None

    for q in qualifications:
        ref_text = f"{q.get('libelle', '')} {q.get('discipline', '')}"
        score = _similarite(recherche, ref_text)
        if score > best_score:
            best_score, best_match = score, q

    valide = best_score >= seuil
    return {
        "valide": valide,
        "score": round(best_score, 3),
        "message": "Diplôme reconnu dans EME" if valide else f"Aucune correspondance (score {best_score:.2f} < {seuil})",
        "best_match": best_match,
        "qualifications_eme": qualifications,
    }


def process_diplome(doc_path: str) -> Optional[dict]:
    """Pipeline complet image → VLM → EME match → Supabase."""
    extractor = setup_extractor()
    print(f"\n📄 Traitement Diplôme : {os.path.basename(doc_path)}")

    result = extractor.extract(doc_path, DiplomeContract, vision=True)

    try:
        doc = json.loads(result.model_dump_json())
        print(json_to_yaml(doc))

        verification = verifier_diplome(doc)
        doc.update({k: v for k, v in verification.items() if k != "qualifications_eme"})
        doc["qualifications_eme_raw"] = json.dumps(verification["qualifications_eme"], ensure_ascii=False)
        doc["fichier"] = os.path.basename(doc_path)

        if verification["valide"]:
            match = verification["best_match"] or {}
            print(f"  ✅ Diplôme reconnu — {match.get('libelle', '')} (score {verification['score']})")
        else:
            print(f"  ❌ {verification['message']}")

        try:
            supabase.table("diplomes_coach").upsert(doc, on_conflict="fichier").execute()
        except Exception as e:
            message = str(e)
            match = re.search(r"Could not find the '([^']+)' column", message)
            if match:
                missing_column = match.group(1)
                if missing_column in doc:
                    print(f"  ⚠️  Colonne Supabase manquante : {missing_column}. Retrait et nouvel essai.")
                    doc.pop(missing_column, None)
                    supabase.table("diplomes_coach").upsert(doc, on_conflict="fichier").execute()
                else:
                    raise
            else:
                raise

        print("  💾 Sauvegardé dans Supabase (table: diplomes_coach)")
        return doc

    except (json.JSONDecodeError, ValueError) as e:
        print(f"  ❌ Erreur extraction : {e}")
        return None


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "coach_docs/files/diplome.jpg"
    # MODIFY THIS LINE FOR TESTING: Replace path with test image location
    # Example: path = "API/examples/placeholder.jpg"
    if not os.path.exists(path):
        sys.exit(f"Fichier introuvable : {path}")
    process_diplome(path)
