(.venv) PS C:\00_VScode\07_DnoVy\DNoVy\API> python orchestrator.py examples/ta_photo.png

======================================================================
ORCHESTRATEUR DNoVy — Validation Carte Pro + SIRET
======================================================================

[1/2] Validation Carte Pro
----------------------------------------------------------------------

📄 Traitement : ta_photo.png
date_naissance: 30/10/1981
lieu_naissance: BORDEAUX (33)
nationalite: Française
nom: BALUSSAUD
numero_carte: 00615ED0116
prenom: Frederic

  Carte : ✅ VALIDE (1 résultat(s) EME)
  💾 Sauvegardé dans Supabase (table: cartes_coach)

[2/2] Validation SIRET
----------------------------------------------------------------------
  ℹ️  Aucun document SIRET fourni, recherche via nom/prénom extraits de la carte pro.

📄 Recherche SIRET par nom/prénom : BALUSSAUD Frederic
  ➜ Premier candidat trouvé : 79999299500016 (FREDERIC BALUSSAUD)
  ✅ SIRET valide — FREDERIC BALUSSAUD (Actif)
  🔎 Vérifié aussi par recherche publique — FREDERIC BALUSSAUD
  🔧 Colonne inconnue supprimée du payload Supabase : nom
  🔧 Colonne inconnue supprimée du payload Supabase : prenom
  🔧 Colonne inconnue supprimée du payload Supabase : public_adresse
  🔧 Colonne inconnue supprimée du payload Supabase : public_denomination
  🔧 Colonne inconnue supprimée du payload Supabase : public_erreur
  🔧 Colonne inconnue supprimée du payload Supabase : public_etat_label
  🔧 Colonne inconnue supprimée du payload Supabase : public_valide
  💾 Sauvegardé dans Supabase (table: siret_coach)

======================================================================
📋 RÉSUMÉ FINAL
======================================================================

✅ Carte Pro      : VALIDE
   • Nom/Prenom : BALUSSAUD Frederic
   • Numéro carte : 00615ED0116

✅ SIRET          : VALIDE
   • Dénomination : FREDERIC BALUSSAUD
   • État : Actif

======================================================================
🎯 RÉSULTAT GLOBAL : ✅ VALIDÉ
======================================================================