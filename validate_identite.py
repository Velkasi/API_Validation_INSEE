"""
DNoVy — Validation pièce d'identité (CNI / passeport).

Méthode :
  1. Extraction VLM des champs visuels + MRZ
  2. Vérification des checksums MRZ (ICAO Doc 9303) sur passeport TD3
  3. Cohérence VLM ↔ MRZ
  4. Persistance Supabase

Note : la CNI FR utilise un format TD1 (3 lignes × 30 caractères) non géré ici.
Pour authentifier réellement, prévoir un prestataire KYC (Onfido, Netheos, Stripe Identity).
"""
import os
import sys
import json
import re
from typing import Optional, Literal

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


class IdentiteContract(Contract):
    type_doc: Literal["CNI", "PASSEPORT", "TITRE_SEJOUR", "INCONNU"] = Field(
        default="INCONNU", description="Type de document d'identité"
    )
    nom: str = Field(description="Nom de famille")
    prenom: str = Field(description="Prénom(s)")
    date_naissance: Optional[str] = Field(default=None, description="Date de naissance JJ/MM/AAAA")
    lieu_naissance: Optional[str] = Field(default=None, description="Lieu de naissance")
    nationalite: Optional[str] = Field(default=None, description="Nationalité")
    numero_document: Optional[str] = Field(default=None, description="Numéro du document")
    date_expiration: Optional[str] = Field(default=None, description="Date d'expiration JJ/MM/AAAA")
    sexe: Optional[Literal["M", "F"]] = Field(default=None, description="Sexe (M ou F)")
    mrz_ligne1: Optional[str] = Field(default=None, description="Première ligne MRZ si visible (44 car.)")
    mrz_ligne2: Optional[str] = Field(default=None, description="Deuxième ligne MRZ si visible (44 car.)")


MRZ_WEIGHTS = [7, 3, 1]


def _mrz_checksum(s: str) -> int:
    """Chiffre de contrôle ICAO 9303."""
    total = 0
    for i, c in enumerate(s.upper()):
        if c.isdigit():
            val = int(c)
        elif c.isalpha():
            val = ord(c) - 55  # A=10, B=11…
        else:
            val = 0  # '<'
        total += val * MRZ_WEIGHTS[i % 3]
    return total % 10


def valider_mrz(mrz1: str, mrz2: str, type_doc: str = "PASSEPORT") -> dict:
    """Chiffre de contrôle ICAO 9303."""
    total = 0
    for i, c in enumerate(s.upper()):
        if c.isdigit():
            val = int(c)
        elif c.isalpha():
            val = ord(c) - 55  # A=10, B=11…
        else:
            val = 0  # '<'
        total += val * MRZ_WEIGHTS[i % 3]
    return total % 10


def valider_mrz(mrz1: str, mrz2: str, type_doc: str = "PASSEPORT") -> dict:
    """
    Valide checksums MRZ TD3 (passeport, 44 char). Retourne :
      - mrz_lisible : True si format reconnu (TD3 longueur 44)
      - mrz_valide  : True si tous checksums OK (None si non lisible)
      - mrz_erreurs : liste des erreurs
      - mrz_champs  : champs extraits depuis MRZ
    """
    mrz1 = (mrz1 or "").upper().replace(" ", "")
    mrz2 = (mrz2 or "").upper().replace(" ", "")
    erreurs = []
    champs = {}

    if type_doc != "PASSEPORT" or len(mrz1) != 44 or len(mrz2) != 44:
        return {
            "mrz_lisible": False,
            "mrz_valide": None,
            "mrz_erreurs": [f"MRZ TD3 non reconnue (type={type_doc}, l1={len(mrz1)}, l2={len(mrz2)})"],
            "mrz_champs": {},
        }

    num_passeport = mrz2[0:9]
    check_num = int(mrz2[9]) if mrz2[9].isdigit() else -1
    dob = mrz2[13:19]
    check_dob = int(mrz2[19]) if mrz2[19].isdigit() else -1
    expiry = mrz2[21:27]
    check_exp = int(mrz2[27]) if mrz2[27].isdigit() else -1
    composite = mrz2[0:10] + mrz2[13:20] + mrz2[21:43]
    check_comp = int(mrz2[43]) if mrz2[43].isdigit() else -1

    if _mrz_checksum(num_passeport) != check_num:
        erreurs.append("Checksum numéro passeport invalide")
    if _mrz_checksum(dob) != check_dob:
        erreurs.append("Checksum date naissance invalide")
    if _mrz_checksum(expiry) != check_exp:
        erreurs.append("Checksum date expiration invalide")
    if _mrz_checksum(composite) != check_comp:
        erreurs.append("Checksum composite invalide")

    noms_raw = mrz1[5:44].split("<<", 1)
    siecle_naissance = "20" if int(dob[:2]) < 30 else "19"
    siecle_expiration = "20"
    champs = {
        "nom_mrz": noms_raw[0].replace("<", " ").strip(),
        "prenom_mrz": noms_raw[1].replace("<", " ").strip() if len(noms_raw) > 1 else "",
        "numero_passeport": num_passeport.replace("<", ""),
        "date_naissance_mrz": f"{dob[4:6]}/{dob[2:4]}/{siecle_naissance}{dob[:2]}",
        "date_expiration_mrz": f"{expiry[4:6]}/{expiry[2:4]}/{siecle_expiration}{expiry[:2]}",
        "nationalite_mrz": mrz2[10:13].replace("<", ""),
        "sexe_mrz": mrz2[20],
    }

    return {
        "mrz_lisible": True,
        "mrz_valide": len(erreurs) == 0,
        "mrz_erreurs": erreurs,
        "mrz_champs": champs,
    }


def verifier_coherence(doc: dict, mrz_champs: dict) -> list[str]:
    """Compare champs VLM vs MRZ. Retourne liste d'incohérences."""
    alertes = []

    def _norm(s: str) -> str:
        return re.sub(r"[^A-Z]", "", (s or "").upper())

    nom_vlm, nom_mrz = _norm(doc.get("nom", "")), _norm(mrz_champs.get("nom_mrz", ""))
    if nom_vlm and nom_mrz and nom_vlm not in nom_mrz and nom_mrz not in nom_vlm:
        alertes.append(f"Nom incohérent : VLM='{doc.get('nom')}' vs MRZ='{mrz_champs.get('nom_mrz')}'")

    dob_vlm = re.sub(r"[^\d]", "", doc.get("date_naissance", "") or "")
    dob_mrz = re.sub(r"[^\d]", "", mrz_champs.get("date_naissance_mrz", "") or "")
    if dob_vlm and dob_mrz and dob_vlm != dob_mrz:
        alertes.append(f"Date naissance incohérente : VLM={doc.get('date_naissance')} vs MRZ={mrz_champs.get('date_naissance_mrz')}")

    return alertes


def process_identite(doc_path: str) -> Optional[dict]:
    """Pipeline complet image → VLM → MRZ → cohérence → Supabase."""
    extractor = setup_extractor()
    print(f"\n📄 Traitement Identité : {os.path.basename(doc_path)}")

    result = extractor.extract(doc_path, IdentiteContract, vision=True)

    try:
        doc = json.loads(result.model_dump_json())
        print(json_to_yaml(doc))

        mrz_result = {}
        alertes = []
        if doc.get("mrz_ligne1") and doc.get("mrz_ligne2"):
            mrz_result = valider_mrz(doc["mrz_ligne1"], doc["mrz_ligne2"], doc.get("type_doc", "PASSEPORT"))
            if mrz_result["mrz_lisible"]:
                print(f"\n  MRZ {'✅ valide' if mrz_result['mrz_valide'] else '❌ INVALIDE'}")
                for err in mrz_result["mrz_erreurs"]:
                    print(f"    • {err}")
                alertes = verifier_coherence(doc, mrz_result.get("mrz_champs", {}))
            else:
                print("  ℹ️  MRZ illisible — validation par VLM seul")
        else:
            print("  ℹ️  Pas de MRZ détectée — validation par VLM seul")

        doc["mrz_lisible"] = mrz_result.get("mrz_lisible", False)
        doc["mrz_valide"] = mrz_result.get("mrz_valide", None)
        doc["mrz_erreurs"] = json.dumps(mrz_result.get("mrz_erreurs", []), ensure_ascii=False)
        doc["mrz_champs"] = json.dumps(mrz_result.get("mrz_champs", {}), ensure_ascii=False)
        doc["alertes"] = json.dumps(alertes, ensure_ascii=False)
        doc["fichier"] = os.path.basename(doc_path)

        if mrz_result.get("mrz_lisible"):
            doc["valide"] = bool(mrz_result.get("mrz_valide")) and len(alertes) == 0
        else:
            doc["valide"] = None

        if alertes:
            print(f"\n  ⚠️  Alertes cohérence :")
            for a in alertes:
                print(f"    • {a}")

        statut = {True: "✅ VALIDE (MRZ OK)", False: "❌ INVALIDE", None: "⚠️  NON VÉRIFIÉ (pas de MRZ)"}
        print(f"\n  Identité : {statut[doc['valide']]}")

        supabase.table("identites_coach").upsert(doc, on_conflict="fichier").execute()
        print("  💾 Sauvegardé dans Supabase (table: identites_coach)")
        return doc

    except (json.JSONDecodeError, ValueError) as e:
        print(f"  ❌ Erreur extraction : {e}")
        return None


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "coach_docs/files/identite.jpg"
    # MODIFY THIS LINE FOR TESTING: Replace path with test image location
    # Example: path = "API/examples/placeholder.jpg"
    if not os.path.exists(path):
        sys.exit(f"Fichier introuvable : {path}")
    process_identite(path)
