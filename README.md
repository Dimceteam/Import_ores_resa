# Import ORES/RESA - Communauté d'énergie

Module Odoo 19 pour gérer les communautés d'énergie belges : import des fichiers de relevés ORES (CSV) et RESA (Excel), calcul du partage d'énergie, facturation automatique et tableau de bord de consommation/production.

[![Odoo](https://img.shields.io/badge/Odoo-19.0-875A7B.svg)](https://www.odoo.com)
[![License](https://img.shields.io/badge/License-LGPL--3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![Version](https://img.shields.io/badge/Version-1.00-brightgreen.svg)](#)

---

## 📖 Table des matières

- [Présentation](#-présentation)
- [Fonctionnalités](#-fonctionnalités)
- [Prérequis](#-prérequis)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Utilisation](#-utilisation)
- [Structure des fichiers importés](#-structure-des-fichiers-importés)
- [Tarifs appliqués](#-tarifs-appliqués)
- [Capture d'écran](#-capture-décran)
- [Dépannage](#-dépannage)
- [Feuille de route](#-feuille-de-route)
- [Support](#-support)
- [Licence](#-licence)

---

## 🎯 Présentation

Ce module permet aux **communautés d'énergie** belges (partage d'énergie entre particuliers) de :

1. **Importer** les relevés de consommation et production provenant des gestionnaires de réseau **ORES** et **RESA**
2. **Calculer automatiquement** la répartition de l'énergie partagée entre les participants
3. **Générer les factures** clients (consommation) et fournisseurs (production) avec les taxes en vigueur
4. **Visualiser** la consommation et la production via un tableau de bord et un graphique intégré aux factures

Le module a été développé pour répondre aux besoins spécifiques du marché belge de l'énergie (CV, droits d'accises, TVA 6% sur l'énergie).

---

## ✨ Fonctionnalités

### 📥 Import de fichiers

- **ORES (CSV)** : import des fichiers de consommation et de production avec détection automatique du type et du mois
- **RESA (Excel)** : import des fichiers multi-feuilles (Brut, Partagé, Net) avec extraction automatique des EAN
- **Détection automatique** : le mois et le type de fichier sont détectés à partir du nom du fichier ou de son contenu
- **Gestion des participants** : création automatique des contacts pour les nouveaux EAN, avec demande de confirmation
- **Anti-doublon** : mise à jour intelligente des enregistrements existants (pas de duplication)

### 📊 Tableau de bord

- **Vues graphiques** par jour, semaine, mois et année
- **Filtres multi-critères** : par opération de partage, participant, EAN
- **Vues Pivot et Liste** pour l'analyse détaillée
- **Panneau de recherche** avec compteurs par participant

### 🧾 Facturation

- **Génération automatique** des factures brouillon après import
- **Facturation par période** (entre deux dates) via un assistant dédié
- **Factures client** (consommation) : journal de vente, TVA 6%
- **Factures fournisseur** (production) : journal d'achat, TVA 6%
- **Lignes détaillées** :
  - Consommation énergie partagée (prix de vente de l'opération)
  - Coût de la restitution des CV : **0,026 €/kWh HTVA**
  - Droit d'accises spécial 2026 : **0,046 €/kWh HTVA** (tarif unique)
- **Anti-doublon** : détection des factures déjà existantes par référence
- **Conditions de paiement** : 30 jours fin de mois par défaut
- **Communication structurée belge** : génération automatique (+++000/0000/XXXXX+++)

### 📄 Rapport de facture personnalisé

- **3 pages** générées automatiquement :
  - Page 1 : facture standard Odoo (avec les 3 postes)
  - Page 2 : graphique de consommation/production sur 12 mois
  - Page 3 : conditions générales de vente
- **Graphique intégré** : barres empilées par mois, distingue prélèvement brut/couvert et production brute/autoconsommée
- **Fallback** : graphique vide généré si aucune donnée n'est disponible (pas de page manquante)

### 👥 Gestion des participants

- Association automatique des EAN aux contacts (`res.partner.ref`)
- Synchronisation automatique des données production/consommation lors de l'ajout/retrait d'un participant
- Réaffectation intelligente entre communautés d'énergie

---

## 🔧 Prérequis

- **Odoo 19.0** (Enterprise ou Community)
- **PostgreSQL** ≥ 12
- **Python** ≥ 3.10
- Modules Odoo requis :
  - `base`
  - `account` (Comptabilité)
  - `web`

### Bibliothèques Python

- `openpyxl` (pour l'import RESA Excel)
- `matplotlib` (pour la génération des graphiques)
- `python-dateutil`

Installation :

```bash
pip install openpyxl matplotlib python-dateutil
