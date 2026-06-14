# Guide de Test — Pipeline d'intégration DNoVy

## Quickstart

Après avoir adapté les chemins d'images réelles, lancez l'orchestrateur complet :

```powershell
cd c:\00_VScode\07_DnoVy\DNoVy\API
python orchestrator.py <chemin_carte> <chemin_identité> <chemin_diplôme> <chemin_SIRET>
```

Ou avec arguments en dur (modifier les chemins dans `orchestrator.py` > `if __name__ == "__main__"`).

## Flux détaillé

### 1. Tester la Carte Pro

**Point de départ** : validé et fonctionnel dans `carte_processor.py`

```powershell
python validate_carte_pro.py <chemin_carte_coach_image>
```

**Résultat attendu** : extraction nom/prénom → vérification EME → enregistrement Supabase

**Ligne à modifier** : dans `validate_carte_pro.py`, ligne `__main__`, remplacer le chemin par celui de votre image réelle

**Sortie** :
```
📄 Traitement : carte-pro.jpg
nom: "DUPONT"
prenom: "Jean"
numero_carte: "12AB34567"
valide: true
Carte : ✓ VALIDE
💾 Sauvegardé dans Supabase.
```

### 2. Tester l'Identité

Utiliser les **mêmes identifiants (nom/prénom)** extraits de la carte

```powershell
python validate_identite.py <chemin_identité_image>
```

**Résultat attendu** : extraction champs + MRZ → vérification checksums → enregistrement

**Ligne à modifier** : dans `validate_identite.py`, ligne `__main__`, remplacer le chemin par celui de votre image réelle

**Sortie** :
```
📄 Traitement Identité : identite.jpg
type_doc: "PASSEPORT"
nom: "DUPONT"
prenom: "Jean"
mrz_ligne1: "P<FRDUPONT<<JEAN..."
mrz_ligne2: "19AB123456FRA..."
Identité : ✅ VALIDE (MRZ OK)
💾 Sauvegardé dans Supabase (table: identites_coach).
```

### 3. Tester le Diplôme

Même personne (nom/prénom) mais diplôme différent

```powershell
python validate_diplome.py <chemin_diplôme_image>
```

**Résultat attendu** : extraction champs → appel API EME → matching score → enregistrement

**Ligne à modifier** : dans `validate_diplome.py`, ligne `__main__`, remplacer le chemin par celui de votre image réelle

**Sortie** :
```
📄 Traitement Diplôme : diplome.jpg
nom: "DUPONT"
prenom: "Jean"
intitule: "BPJEPS Activités de la forme"
Diplôme reconnu — BPJEPS ... (score 0.876)
💾 Sauvegardé dans Supabase (table: diplomes_coach).
```

### 4. Tester le SIRET

Entreprise/SIREN correspondant à la même personne (si applicable)

```powershell
python validate_siret.py <chemin_SIRET_image>
```

**Résultat attendu** : extraction SIRET → appel INSEE → enregistrement

**Ligne à modifier** : dans `validate_siret.py`, ligne `__main__`, remplacer le chemin par celui de votre image réelle

**Sortie** :
```
📄 Traitement SIRET : siret.jpg
siret: "41816609600051"
siren: "418166096"
SIRET valide — ACME CORP FRANCE (Actif)
💾 Sauvegardé dans Supabase (table: siret_coach).
```

### 5. Orchestrateur complet

Une fois tous les tests individuels validés :

```powershell
python orchestrator.py <chemin_carte> <chemin_identité> <chemin_diplôme> <chemin_SIRET>
```

**Résultat** : résumé cohérent de tous les validateurs + cohérence croisée (nom/prénom)

```
======================================================================
📋 RÉSUMÉ FINAL
======================================================================

✅ Carte Pro      : VALIDE
   • Nom/Prenom : DUPONT Jean
   • Numéro carte : 12AB34567

✅ Identité       : VALIDE
   • MRZ lisible : true
   • MRZ valide : true

✅ Diplôme        : VALIDE
   • Score matching : 0.876

✅ SIRET          : VALIDE
   • Dénomination : ACME CORP FRANCE
   • État : Actif

🔍 Cohérence nom (Carte vs Identité) : ✅ OK

======================================================================
🎯 RÉSULTAT GLOBAL : ✅ VALIDÉ
======================================================================
```

## Variables d'environnement requises

Créer un fichier `.env` à la racine `API/` avec :

```bash
# LM Studio (VLM local)
LMSTUDIO_BASE_URL=http://192.168.1.181:12000/v1
VLM_MODEL=qwen/qwen3-vl-8b

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_anon_key

# INSEE (pour SIRET)
INSEE_API_KEY=your_insee_api_key

# (Optionnel) Monitoring
SENTRY_DSN=
```

## Clé API SIRENE / INSEE

Pour obtenir la clé `INSEE_API_KEY` :

1. Aller sur https://portail-api.insee.fr/ en mode “Connexion pour les externes”.
2. Créer un compte et une application.
3. Choisir le mode de création “simple”.
4. Souscrire à l’API Sirene dans le catalogue.
5. Utiliser le plan `Public`.
6. Récupérer la clé dans l’onglet “souscriptions” de l’application.

La clé doit ensuite être placée dans le fichier `.env` sous la variable `INSEE_API_KEY`.

## Supabase et sécurité des lignes (RLS)

Si vous exécutez ce projet depuis un script serveur local, utilisez une clé de service Supabase plutôt qu’une clé publique.

- Dans le dashboard Supabase : `Settings > API`
- Copiez la `Service_role key`
- Ajoutez-la à votre `.env` :

```env
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

Puis, dans le code, chargez-la dans `SUPABASE_KEY` ou utilisez une logique serveur qui prend la valeur de `SUPABASE_SERVICE_ROLE_KEY` lorsque vous écrivez dans la base.

Cette clé permet d’ignorer les règles RLS côté serveur, mais ne doit jamais être exposée en frontend.

Si vous préférez utiliser une clé publique (`SUPABASE_KEY`), activez des policies `INSERT`/`UPDATE` appropriées sur les tables concernées et autorisez l’accès pour l’utilisateur public.

## Utilisation de la clé SIRENE dans le code

Le script `validate_siret.py` utilise déjà l’en-tête HTTP suivant :

```python
headers = {
    "X-INSEE-Api-Key-Integration": INSEE_API_KEY,
    "Accept": "application/json",
}
```

Ce qui correspond à l’usage attendu par l’API Sirene.

## Points de vérification

- [ ] `.env` complété avec vraies clés/URLs
- [ ] `carte_processor.py` fonctionnel (test unitaire)
- [ ] `validate_identite.py` exécutable avec image réelle
- [ ] `validate_diplome.py` exécutable avec image réelle
- [ ] `validate_siret.py` exécutable avec image réelle
- [ ] Données cohérentes (même nom/prénom dans carte + identité)
- [ ] Tables Supabase créées : `cartes_coach`, `identites_coach`, `diplomes_coach`, `siret_coach`
- [ ] Orchestrateur exécuté sans erreur et affiche résumé correct

## Dépannage

- **Erreur LLM** : Vérifier que LM Studio tourne sur `LMSTUDIO_BASE_URL`
- **Erreur Supabase** : Vérifier que les clés `.env` sont correctes
- **Erreur INSEE** : Vérifier que `INSEE_API_KEY` est fournie (optionnel)
- **Image illisible** : Essayer avec images meilleures qualité ou prétraitement OCR
