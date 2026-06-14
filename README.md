**API - Validateurs**

Ce dossier contient des scripts de validation pour différents types de documents/identifiants utilisés par le projet : SIRET, identité, diplôme, carte professionnelle, etc.

**Fichiers principaux**
- `validate_siret.py` : validation d'un SIRET.
- `validate_identite.py` : validation d'identité (nom, prénom, date de naissance, etc.).
- `validate_diplome.py` : validation de diplômes.
- `validate_carte_pro.py` : validation de carte professionnelle.

**Exécution locale (exemples)**
- Lancer un validateur :

```bash
python API/validate_siret.py
python API/validate_identite.py
```

Selon les scripts, des arguments ou fichiers d'entrée peuvent être attendus. Vérifier l'en-tête des scripts pour les options.

**Variables d'environnement importantes**
- `OPENAI_API_KEY` / `OPENAI_MODEL` ou `LLM_MODEL` — si les validateurs appellent un modèle LLM.
- `AZURE_API_KEY`, `AZURE_REGION` — pour les intégrations Azure.
- `GOOGLE_APPLICATION_CREDENTIALS` — chemin vers JSON si utilisation des APIs Google.
- `SUPABASE_URL`, `SUPABASE_KEY` — si les validateurs écrivent/consultent des métadonnées dans Supabase.

**Points d'attention**
- Ne pas committer de clefs dans le dépôt. Utiliser `.env` non tracké ou un secret manager.
- Les validateurs peuvent dépendre de l'output du pipeline OCR ; tester avec des images/texte réels.
- Contrôler les formats d'entrée (images, PDF, JSON). Certains scripts supposent des chemins de fichiers locaux.
- S'assurer que les quotas API (LLM, OCR cloud) sont suffisants pour vos tests.

**Bonnes pratiques**
- Fournir un fichier `./API/.env.example` pour lister les variables requises.
- Ajouter des tests unitaires pour les règles de validation (SIRET format, checksum, etc.).
- Logger les erreurs et sorties dans un dossier `logs/` pour audit.

**Aide / Support**
- Pour questions, ouvrir une issue et préciser quel validateur et exemples d'entrée.

**Exemples d'exécution et `.env`**
- Copiez `API/.env.example` en `API/.env` et remplissez les valeurs sensibles.
- Exemple d'exécution en local (PowerShell) :

```powershell
# charger les variables depuis .env (si vous utilisez "python-dotenv" ou équivalent)
python API/validate_siret.py --input examples/siret_sample.json
python API/validate_identite.py --input examples/identite_sample.jpg
```

Si un validateur attend d'autres arguments, consultez l'en-tête du script pour les options.
