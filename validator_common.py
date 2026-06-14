import os
import json
import yaml
from typing import Type

import litellm
from dotenv import load_dotenv
from supabase import create_client
from extract_thinker import Extractor, LLM, Contract

load_dotenv()

# MODIFY IF NEEDED: Adjust LM Studio URL and model name for local VLM inference
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://192.168.1.181:12000/v1")
DEFAULT_MODEL = os.getenv("VLM_MODEL", "qwen/qwen3-vl-4b")

# Configure litellm (local LM Studio by default)
litellm.api_base = LMSTUDIO_BASE_URL
litellm.api_key = os.getenv("LMSTUDIO_API_KEY", "local")


def setup_extractor(model_name: str | None = None) -> Extractor:
    """Initialise et retourne un `Extractor` avec LLM chargé."""
    model = model_name or DEFAULT_MODEL
    extractor = Extractor()
    extractor.load_llm(LLM(f"openai/{model}"))
    return extractor


def get_supabase_client():
    # MODIFY IF NEEDED: Ensure SUPABASE_URL and SUPABASE_KEY are set in .env
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_KEY missing in environment")
    return create_client(url, key)


def extract_document(extractor: Extractor, doc_path: str, contract_cls: Type[Contract], vision: bool = True) -> dict:
    """Extract using extractor and return a python dict from the Contract result."""
    result = extractor.extract(doc_path, contract_cls, vision=vision)
    return json.loads(result.model_dump_json())


def upsert_supabase(supabase, table: str, doc: dict, on_conflict: str = "fichier") -> None:
    """Upsert `doc` into Supabase table."""
    supabase.table(table).upsert(doc, on_conflict=on_conflict).execute()


def pretty_print(doc: dict) -> None:
    try:
        print(yaml.dump(doc, allow_unicode=True))
    except Exception:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
