"""
DNoVy — Validation SIRET via API SIRENE INSEE V3.11.

Pipeline :
  1. Extraction VLM depuis image URSSAF/Kbis
  2. Vérification officielle SIRENE INSEE V3.11
  3. Persistance Supabase

Usage :
  python validate_siret.py <chemin_image>
  python validate_siret.py <siret_14_chiffres>   # vérif directe sans VLM

Prérequis :
  - .env : INSEE_API_KEY, SUPABASE_URL, SUPABASE_KEY
  - LM Studio local sur LMSTUDIO_BASE_URL
"""
import os
import sys
import json
import re
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

litellm.api_base = LMSTUDIO_BASE_URL
litellm.api_key = "local"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL or SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY missing in environment")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
INSEE_API_KEY = os.environ.get("INSEE_API_KEY", "")
SIRENE_BASE = "https://api.insee.fr/api-sirene/3.11"
RECHERCHE_ENTREPRISES_BASE = "https://recherche-entreprises.api.gouv.fr/search"


def json_to_yaml(json_dict):
    if not isinstance(json_dict, dict):
        raise ValueError("json_dict must be a dictionary")
    return yaml.dump(json_dict, allow_unicode=True)


class SiretContract(Contract):
    siret: Optional[str] = Field(default=None, description="Numéro SIRET 14 chiffres")
    siren: Optional[str] = Field(default=None, description="Numéro SIREN 9 chiffres")
    nom_entreprise: Optional[str] = Field(default=None, description="Dénomination ou raison sociale")
    code_ape: Optional[str] = Field(default=None, description="Code APE / NAF")
    date_creation: Optional[str] = Field(default=None, description="Date de création")


def setup_extractor():
    extractor = Extractor()
    llm = LLM(f"openai/{MODEL_NAME}")
    extractor.load_llm(llm)
    return extractor


def verifier_siret(siret: str) -> dict:
    """Interroge l'API SIRENE V3.11. Retourne {valide, actif, denomination, ...}."""
    if not INSEE_API_KEY:
        return {"valide": False, "actif": False, "erreur": "INSEE_API_KEY manquante"}

    siret_clean = siret.replace(" ", "").replace("-", "")
    if len(siret_clean) != 14 or not siret_clean.isdigit():
        return {"valide": False, "actif": False, "erreur": f"format_invalide ({len(siret_clean)} chiffres)"}

    headers = {"X-INSEE-Api-Key-Integration": INSEE_API_KEY, "Accept": "application/json"}
    try:
        r = requests.get(f"{SIRENE_BASE}/siret/{siret_clean}", headers=headers, timeout=10)
        if r.status_code == 404:
            return {"valide": False, "actif": False, "erreur": "siret_introuvable"}
        r.raise_for_status()

        et = r.json()["etablissement"]
        ul = et["uniteLegale"]
        adr = et["adresseEtablissement"]
        etat = et["periodesEtablissement"][0]["etatAdministratifEtablissement"]

        denomination = ul.get("denominationUniteLegale") or " ".join(filter(None, [
            ul.get("prenom1UniteLegale"), ul.get("nomUniteLegale"),
        ])).strip()

        return {
            "valide": True,
            "actif": etat == "A",
            "etat_label": "Actif" if etat == "A" else f"Cessé ({etat})",
            "siret": et["siret"],
            "siren": et["siren"],
            "denomination": denomination,
            "activite_principale": ul.get("activitePrincipaleUniteLegale"),
            "categorie_juridique": ul.get("categorieJuridiqueUniteLegale"),
            "date_creation": et.get("dateCreationEtablissement"),
            "adresse": " ".join(filter(None, [
                adr.get("numeroVoieEtablissement"),
                adr.get("typeVoieEtablissement"),
                adr.get("libelleVoieEtablissement"),
                adr.get("codePostalEtablissement"),
                adr.get("libelleCommuneEtablissement"),
            ])),
        }
    except requests.RequestException as e:
        return {"valide": False, "actif": False, "erreur": str(e)}


def verifier_siret_publique(siret: str) -> dict:
    """Vérifie l'existence d'un SIRET via l'API publique recherche-entreprises.api.gouv.fr."""
    siret_clean = siret.replace(" ", "").replace("-", "")
    if len(siret_clean) != 14 or not siret_clean.isdigit():
        return {"public_valide": False, "public_erreur": "format_invalide"}

    params = {"q": siret_clean, "size": 1}
    try:
        r = requests.get(RECHERCHE_ENTREPRISES_BASE, params=params, timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return {"public_valide": False, "public_erreur": "introuvable"}

        result = results[0]
        etablissements = result.get("matching_etablissements") or []
        first_etab = etablissements[0] if etablissements else result.get("siege", {})
        return {
            "public_valide": True,
            "public_siren": result.get("siren"),
            "public_denomination": result.get("nom_raison_sociale") or result.get("nom_complet"),
            "public_etat_label": "Actif" if first_etab.get("etat_administratif") == "A" else f"{first_etab.get('etat_administratif')}",
            "public_adresse": " ".join(filter(None, [
                first_etab.get("numero_voie"),
                first_etab.get("type_voie"),
                first_etab.get("libelle_voie"),
                first_etab.get("code_postal"),
                first_etab.get("libelle_commune"),
            ])),
        }
    except requests.RequestException as e:
        return {"public_valide": False, "public_erreur": str(e)}


def _supabase_upsert_siret_coach(payload: dict) -> None:
    """Upsert in siret_coach en réessayant sans colonnes inconnues si le schéma n'est pas à jour."""
    payload = dict(payload)
    while True:
        try:
            supabase.table("siret_coach").upsert(payload, on_conflict="siret").execute()
            return
        except Exception as e:
            message = str(e)
            match = re.search(r"Could not find the '([^']+)' column", message)
            if not match:
                raise
            missing_col = match.group(1)
            if missing_col not in payload:
                raise
            payload.pop(missing_col)
            print(f"  🔧 Colonne inconnue supprimée du payload Supabase : {missing_col}")


def rechercher_siret_par_nom(nom: str, prenom: str, limit: int = 5) -> list[dict]:
    """Recherche des SIRET candidats via l'API publique recherche-entreprises.api.gouv.fr."""
    query = f"{nom} {prenom}".strip()
    if not query:
        return []

    url = "https://recherche-entreprises.api.gouv.fr/search"
    params = {"q": query, "size": limit}

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
        candidates = []
        for result in results[:limit]:
            etablissements = result.get("matching_etablissements") or []
            first_etab = etablissements[0] if etablissements else result.get("siege", {})
            adresse = " ".join(filter(None, [
                first_etab.get("numero_voie"),
                first_etab.get("type_voie"),
                first_etab.get("libelle_voie"),
                first_etab.get("code_postal"),
                first_etab.get("libelle_commune"),
            ]))
            candidates.append({
                "siret": first_etab.get("siret"),
                "siren": result.get("siren"),
                "denomination": result.get("nom_raison_sociale") or result.get("nom_complet"),
                "nom": result.get("nom_raison_sociale"),
                "prenom": prenom,
                "adresse": adresse,
            })
        return candidates
    except requests.RequestException:
        return []


def process_siret(doc_path: Optional[str] = None, nom: Optional[str] = None, prenom: Optional[str] = None) -> Optional[dict]:
    """Pipeline complet image → VLM → INSEE → Supabase, ou recherche par nom/prénom."""
    if doc_path:
        extractor = setup_extractor()
        print(f"\n📄 Traitement SIRET : {os.path.basename(doc_path)}")

        result = extractor.extract(doc_path, SiretContract, vision=True)

        try:
            doc = json.loads(result.model_dump_json())
            print(json_to_yaml(doc))

            siret = doc.get("siret") or doc.get("siren", "")
            if not siret:
                print("  ⚠️  Aucun SIRET détecté dans le document.")
                return None

            verification = verifier_siret(siret)
            verification_public = verifier_siret_publique(siret)
            doc.update(verification)
            doc["public_valide"] = verification_public.get("public_valide", False)
            doc["public_erreur"] = verification_public.get("public_erreur")
            doc["public_etat_label"] = verification_public.get("public_etat_label")
            doc["public_denomination"] = verification_public.get("public_denomination")
            doc["public_adresse"] = verification_public.get("public_adresse")
            doc["fichier"] = os.path.basename(doc_path)

            if not verification["valide"]:
                print(f"  ❌ SIRET invalide — {verification.get('erreur', '')}")
            elif not verification.get("actif"):
                print(f"  ⚠️  SIRET valide mais ENTREPRISE CESSÉE")
            else:
                print(f"  ✅ SIRET valide — {verification['denomination']} ({verification['etat_label']})")
            if verification_public.get("public_valide"):
                print(f"  🔎 Vérifié aussi par recherche publique — {verification_public.get('public_denomination')}")
            else:
                print(f"  ⚠️  Recherche publique SIRET invalide — {verification_public.get('public_erreur')}")

            _supabase_upsert_siret_coach(doc)
            print("  💾 Sauvegardé dans Supabase (table: siret_coach)")
            return doc

        except (json.JSONDecodeError, ValueError) as e:
            print(f"  ❌ Erreur extraction : {e}")
            return None

    if nom and prenom:
        print(f"\n📄 Recherche SIRET par nom/prénom : {nom} {prenom}")
        candidates = rechercher_siret_par_nom(nom, prenom)
        if not candidates:
            print("  ⚠️  Aucun candidat SIRET trouvé via recherche par nom/prénom.")
            doc = {
                "nom": nom,
                "prenom": prenom,
                "siret": "",
                "siren": "",
                "denomination": "",
                "adresse": "",
                "source": "carte_pro",
                "candidats_siret": json.dumps(candidates, ensure_ascii=False),
                "valide": False,
                "actif": False,
                "etat_label": "siret_non_trouve",
                "fichier": f"carte_pro_{nom}_{prenom}",
            }
            _supabase_upsert_siret_coach(doc)
            print("  💾 Enregistrement créé dans Supabase même sans SIRET trouvé.")
            return doc

        candidate = candidates[0]
        print(f"  ➜ Premier candidat trouvé : {candidate.get('siret')} ({candidate.get('denomination')})")
        verification = verifier_siret(candidate["siret"])
        verification_public = verifier_siret_publique(candidate["siret"])
        doc = {
            "nom": nom,
            "prenom": prenom,
            "siret": candidate.get("siret"),
            "siren": candidate.get("siren"),
            "denomination": candidate.get("denomination"),
            "adresse": candidate.get("adresse"),
            "source": "carte_pro",
            "candidats_siret": json.dumps(candidates, ensure_ascii=False),
            "public_valide": verification_public.get("public_valide", False),
            "public_erreur": verification_public.get("public_erreur"),
            "public_etat_label": verification_public.get("public_etat_label"),
            "public_denomination": verification_public.get("public_denomination"),
            "public_adresse": verification_public.get("public_adresse"),
        }
        doc.update(verification)
        doc["fichier"] = f"carte_pro_{nom}_{prenom}"

        if verification["valide"]:
            print(f"  ✅ SIRET valide — {verification['denomination']} ({verification['etat_label']})")
        else:
            print(f"  ❌ SIRET invalide — {verification.get('erreur', '')}")
        if verification_public.get("public_valide"):
            print(f"  🔎 Vérifié aussi par recherche publique — {verification_public.get('public_denomination')}")
        else:
            print(f"  ⚠️  Recherche publique SIRET invalide — {verification_public.get('public_erreur')}")

        _supabase_upsert_siret_coach(doc)
        print("  💾 Sauvegardé dans Supabase (table: siret_coach)")
        return doc

    print("  ⚠️  Aucun chemin de document SIRET ni nom/prénom fournis.")
    return None


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else input("Image ou SIRET : ").strip()
    # MODIFY THIS LINE FOR TESTING: Replace 'arg' with path to test image or SIRET
    # Example: arg = "API/examples/placeholder.jpg"  OR  arg = "41816609600051"
    if os.path.exists(arg):
        process_siret(arg)
    else:
        result = verifier_siret(arg)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("actif"):
            print(f"\n✓ {result['denomination']} — actif depuis {result.get('date_creation', '?')}")
        else:
            print(f"\n✗ SIRET {arg} : {result.get('erreur', 'établissement fermé')}")
