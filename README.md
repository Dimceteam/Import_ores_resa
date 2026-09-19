# Import ORES/RESA - Communauté d'énergie

Module Odoo 19 permettant de gérer une **communauté d'énergie** (partage d'énergie entre participants) : import des fichiers de comptage envoyés par les gestionnaires de réseau **ORES** (CSV) et **RESA** (Excel), suivi de la production/consommation, tableaux de bord, et **génération automatique des factures** clients (consommation) et fournisseurs (production).

- **Auteur / Éditeur** : Wattlabs — https://www.wattlabs.be
- **Support** : support@wattlabs.be
- **Licence** : LGPL-3
- **Catégorie** : Tools
- **Version** : 19.0.1.0.0 (Odoo 19)
- **Dépendances Odoo** : `base`, `account`, `web`
- **Dépendances Python** : `matplotlib` (graphiques sur factures), `openpyxl` (lecture des fichiers RESA au format Excel)

---

## Sommaire

1. [Présentation générale](#présentation-générale)
2. [Fonctionnalités](#fonctionnalités)
3. [Installation](#installation)
4. [Structure du module](#structure-du-module)
5. [Modèles de données](#modèles-de-données)
6. [Assistants (wizards)](#assistants-wizards)
7. [Tableau de bord](#tableau-de-bord)
8. [Facturation automatique](#facturation-automatique)
9. [Rapport de facture (graphique)](#rapport-de-facture-graphique)
10. [Menus](#menus)
11. [Sécurité / droits d'accès](#sécurité--droits-daccès)
12. [Formats de fichiers attendus](#formats-de-fichiers-attendus)
13. [Tarifs facturés](#tarifs-facturés)
14. [Limitations connues / points d'attention](#limitations-connues--points-dattention)
15. [Dépannage (FAQ)](#dépannage-faq)
16. [Licence](#licence)

---

## Présentation générale

Dans le cadre d'une **communauté d'énergie renouvelable** (partage d'énergie entre plusieurs points de comptage EAN), les gestionnaires de réseau de distribution belges (**ORES** en Wallonie, **RESA** dans la région liégeoise) fournissent périodiquement des fichiers détaillant :

- la **production** injectée et allouée au partage,
- la **consommation** couverte par cette production partagée.

Ce module permet d'**importer ces fichiers directement dans Odoo**, de les rattacher automatiquement aux bons participants (contacts), de suivre l'activité via un **tableau de bord** (jour / semaine / mois / année), puis de **générer les factures** correspondantes (facture client pour la consommation, facture fournisseur pour la production) en tenant compte des prix définis par opération de partage.

## Fonctionnalités

- ✅ Import des fichiers **ORES** au format **CSV** (production et/ou consommation)
- ✅ Import des fichiers **RESA** au format **Excel (.xlsx)**
- ✅ **Détection automatique** du type de fichier (production / consommation) à partir des en-têtes
- ✅ **Détection automatique du mois** concerné (à partir du nom de fichier ou du contenu)
- ✅ Détection et **création automatique des participants** (contacts `res.partner`) à partir de leur EAN, avec écran de confirmation avant import
- ✅ Import **idempotent** : une seconde importation du même fichier met à jour les lignes existantes plutôt que de les dupliquer
- ✅ Import par **lots (batch commit)** pour les gros fichiers (fichiers de comptage 15 min = potentiellement plusieurs dizaines de milliers de lignes)
- ✅ Synchronisation automatique des participants d'une opération de partage (ajout/retrait d'un partenaire → réaffectation ou détachement des données historiques)
- ✅ **Tableau de bord** graphique (Consommation / Production) par jour, semaine, mois, année
- ✅ **Génération automatique des factures** :
  - directement à la fin d'un import (case à cocher), ou
  - via un assistant dédié permettant de choisir une **période libre** et un ou plusieurs participants
- ✅ Prévisualisation (kWh, montant estimé, nombre de factures déjà existantes) **avant** de lancer la génération
- ✅ Facture client incluant automatiquement, en plus du prix de l'énergie : le **coût de restitution des CV** et le **droit d'accises spécial 2026**
- ✅ **Anti-doublon de facturation** : une facture n'est jamais recréée si une facture (brouillon ou validée) existe déjà pour le même participant / la même période / la même opération
- ✅ **Rapport de facture enrichi** avec un graphique matplotlib intégré (historique 12 mois de consommation/production du point EAN facturé)
- ✅ Barre de progression JS pendant l'import

## Installation

1. Copier le dossier `import_ores_resa` dans le répertoire `addons` de votre instance Odoo 19.
2. Installer les dépendances Python sur le serveur :
   ```bash
   pip install matplotlib openpyxl
   ```
   > Sans `matplotlib`, le module fonctionne normalement mais le graphique sur les factures ne sera pas généré. `openpyxl` est en revanche indispensable pour l'import RESA (fichiers Excel).
3. Mettre à jour la liste des applications puis installer **« Import ORES/RESA - Communauté d'énergie »** depuis Apps.
4. Vérifier qu'un **journal d'achat** et un **journal de vente** existent dans la comptabilité (nécessaires pour générer respectivement les factures fournisseur/production et client/consommation).

## Structure du module

```
import_ores_resa/
├── __init__.py
├── __manifest__.py
├── LICENSE
├── models/
│   ├── __init__.py
│   ├── models.py            # energy.community, production, consumption, participant
│   └── dashboard.py         # extension account.move : graphique sur facture
├── wizard/
│   ├── __init__.py
│   ├── import_ores_wizard.py        # import CSV ORES
│   ├── import_resa_wizard.py        # import Excel RESA
│   └── generate_invoices_wizard.py  # génération de factures sur période libre
├── views/
│   ├── energy_community_views.xml
│   ├── import_ores_wizard_views.xml
│   ├── import_resa_wizard_views.xml
│   ├── generate_invoices_wizard_views.xml
│   └── dashboard_views.xml
├── report/
│   └── invoice_report.xml   # extension du rapport de facture (graphique)
├── security/
│   └── ir.model.access.csv
└── static/
    ├── description/         # icône + captures d'écran (fiche Apps)
    └── src/js/
        └── import_progress.js   # barre de progression pendant l'import
```

## Modèles de données

| Modèle technique | Description | Champs clés |
|---|---|---|
| `energy.community` | Une **opération de partage** (communauté d'énergie) | `name`, `active`, `partner_ids` (participants), `product_price` (prix de vente €/kWh aux consommateurs), `producer_price` (prix d'achat €/kWh aux producteurs), `month` |
| `energy.community.production` | Une ligne de **production** importée (par EAN et par timestamp) | `timestamp`, `ean`, `production_brute`, `coefficient`, `production_allouee`, `production_autoconsommee`, `production_non_allouee`, `allo_production`, `community_id`, `partner_id`, `month` (calculé) |
| `energy.community.consumption` | Une ligne de **consommation** importée (par EAN, timestamp et itération) | `timestamp`, `ean`, `iteration`, `coefficient`, `prelevement_brut`, `production_mise_disposition`, `prelevement_couvert`, `surplus_production`, `allo_consommation`, `community_id`, `partner_id`, `month` (calculé) |
| `energy.community.participant` | Un participant rattaché à une opération, avec son type | `community_id`, `partner_id`, `ean`, `meter_id`, `participant_type` (`consumption`/`injection`), `active` |

### Logique métier importante : `energy.community.write()`

Lorsqu'on modifie la liste des participants (`partner_ids`) d'une opération de partage :

- **Participant retiré** de l'opération :
  - s'il appartient encore à une **autre** opération de partage → ses données historiques (production/consommation) sont **réaffectées** à cette autre opération ;
  - sinon → ses données sont **détachées** (`community_id = False`), mais **jamais supprimées**.
- **Participant ajouté** à l'opération :
  - si son EAN n'appartient à aucune autre opération de partage active, ses données orphelines existantes sont **rattachées** automatiquement à la nouvelle opération.

Ce comportement garantit qu'aucune donnée de comptage n'est perdue lors d'une réorganisation des participants entre communautés.

## Assistants (wizards)

### 1. Import ORES (CSV) — `import.ores.wizard`

Menu : **Communauté d'énergie ▸ Importer ORES (CSV)**

- Champs : fichier CSV, type de fichier (`auto` / `production` / `consommation`), opération de partage, mois, génération de factures (option), date de facture, condition de paiement.
- À la sélection du fichier (`onchange`) :
  1. Détection automatique du **mois** (nom du fichier, puis contenu si nécessaire, sinon mois courant) ;
  2. Détection automatique du **type de fichier** par analyse des en-têtes CSV (mots-clés production vs consommation) ;
  3. Extraction de tous les **EAN** présents et distinction entre participants **déjà connus** de l'opération et **nouveaux** participants ;
  4. Si de nouveaux participants sont détectés, une **case de confirmation** doit être cochée avant de pouvoir lancer l'import.
- `action_import()` ouvre une fenêtre modale de progression (`view_import_ores_progress_form`), puis `action_do_import()` réalise l'import réel :
  - le fichier est relu ligne par ligne (`csv.DictReader`, délimiteur `;`, encodage `utf-8-sig`) ;
  - un **cache local** des partenaires (par EAN) et des enregistrements existants (par clé timestamp/EAN\[/itération]) évite les recherches répétées en base ;
  - chaque ligne est **créée ou mise à jour** (upsert) selon qu'un enregistrement existe déjà pour la même clé ;
  - un **commit** est effectué toutes les `BATCH_SIZE = 2000` lignes pour limiter la consommation mémoire/transaction sur les gros fichiers ;
  - si la case *« Générer les factures automatiquement »* est cochée, `_generate_invoices()` est appelée en fin d'import.
- Les valeurs numériques sont nettoyées via `_clean_number()` qui gère les formats belges/français (virgule décimale, espace ou espace insécable comme séparateur de milliers).

### 2. Import RESA (Excel) — `import.resa.wizard`

Menu : **Communauté d'énergie ▸ Importer RESA (Excel)**

- Fonctionnement analogue au wizard ORES, mais :
  - lecture du fichier via `openpyxl.load_workbook` (toutes les feuilles du classeur sont parcourues) ;
  - extraction des EAN et de leur type (Prélèvement/Injection) directement depuis les feuilles Excel ;
  - détection du mois également possible en scannant le contenu des cellules (motifs `YYYY-MM` ou `MM-YYYY`) si le nom de fichier ne le permet pas ;
  - à l'issue de l'import, les champs `import_stats`, `invoices_created` et `invoices_skipped` renseignent un résumé du traitement.

### 3. Génération de factures sur période libre — `energy.invoice.generator.wizard`

Menu : **Communauté d'énergie ▸ Générer factures (période)**

Cet assistant permet de **facturer a posteriori** sans repasser par un import, sur une période de dates arbitraire :

- Sélection de l'**opération de partage**, éventuellement filtrée sur un ou plusieurs **participants** (vide = tous) ;
- Choix du **type de données** à facturer : Consommation + Production, Consommation seule, ou Production seule ;
- Période `date_from` → `date_to` (bornée par `_check_dates()` : la date de début doit précéder la date de fin) ;
- Un **panneau de statistiques** calculé en temps réel (`_compute_stats`) affiche avant validation :
  - nombre de lignes de données trouvées,
  - nombre de participants concernés,
  - total de kWh facturables,
  - montant HT estimé (énergie + CV + accises pour la consommation),
  - nombre de factures déjà existantes sur la période (qui seront donc ignorées) ;
- `action_generate()` vérifie qu'il existe bien des données et les journaux comptables nécessaires (`_check_journals()`) **avant** toute création, pour éviter une génération partielle en cas de configuration incomplète ;
- Un résumé textuel détaillé (`result_summary`) est produit : factures créées, ignorées (doublons), échouées, ou non facturées faute de prix configuré (`product_price`/`producer_price` à 0) ;
- Si au moins une facture a été créée, la fenêtre s'ouvre directement sur la liste des factures générées.

## Tableau de bord

Menu : **Communauté d'énergie ▸ Tableau de bord**

Organisé en deux sous-menus (**Consommation** et **Production**), chacun décliné en quatre vues graphiques/pivot/liste :

- Par Jour
- Par Semaine
- Par Mois
- Par Année

Chaque vue s'appuie sur les modèles `energy.community.consumption` / `energy.community.production` avec une vue de recherche dédiée permettant de filtrer par opération de partage, participant et période.

## Facturation automatique

La logique de facturation (dupliquée dans `import_ores_wizard.py`, `import_resa_wizard.py` et factorisée dans `generate_invoices_wizard.py`) suit le principe suivant :

1. **Facture client (`out_invoice`)** — journal de type *vente* :
   - Une ligne par participant consommateur, regroupant le **prélèvement couvert** (kWh) sur la période ;
   - Prix unitaire = `product_price` défini sur l'opération de partage ;
   - Trois lignes de facture sont générées : *Consommation énergie partagée*, *Coût de la restitution des CV*, *Droit d'accises spécial 2026* (voir [Tarifs facturés](#tarifs-facturés)) ;
   - TVA 6% appliquée automatiquement (recherchée ou créée si absente).
2. **Facture fournisseur (`in_invoice`)** — journal de type *achat* :
   - Une ligne par participant producteur, basée sur la **production autoconsommée** (kWh) ;
   - Prix unitaire = `producer_price` défini sur l'opération de partage ;
   - TVA 6% appliquée également.
3. **Anti-doublon** : avant toute création, `_invoice_exists()` recherche une facture brouillon ou validée dont la **référence** (`ref`) contient déjà l'opération, la période et l'EAN concernés. Si trouvée, la facture n'est pas recréée.
4. Toutes les factures sont créées à l'état **brouillon** (`state = draft`) — elles doivent être **relues et validées manuellement** en comptabilité avant envoi/paiement.
5. Si aucun prix (`product_price` ou `producer_price`) n'est configuré sur l'opération de partage, les participants concernés ne sont **pas facturés** (et c'est signalé dans le résumé du wizard de génération sur période).

> ⚠️ Si aucune condition de paiement n'est sélectionnée dans le wizard, le module recherche une condition **existante** dont le nom contient la séquence « 30 » (recherche `ilike '30%'`, où le `%` de fin est redondant avec le comportement normal de `ilike` et ne représente donc pas un caractère `%` littéral à trouver dans le nom). Si une telle condition existe déjà — même sans rapport avec un délai de paiement, par ex. *"Escompte 2/10 net 30"* — c'est **elle** qui sera utilisée par erreur. Ce n'est que si **aucune** condition ne contient « 30 » qu'une nouvelle condition *« 30 jours fin de mois »* est **créée automatiquement**. Il est donc recommandé de toujours choisir explicitement la condition de paiement voulue avant de lancer l'import ou la génération de factures.

## Rapport de facture (graphique)

Le module étend le modèle `account.move` (`models/dashboard.py`) pour ajouter `get_consumption_graph_for_invoice()`, utilisée par le rapport `report/invoice_report.xml` :

- L'**EAN** et l'**opération de partage** sont retrouvés à partir de la **référence** de la facture (`ref`), au format `Opération de partage <nom> - <mois ou période> - <EAN>` ;
- La période du graphique correspond aux **12 mois précédant le mois facturé** (et non la date d'émission de la facture) ;
- Deux graphiques empilés sont générés avec `matplotlib` :
  - **Consommation** : prélèvement brut vs prélèvement couvert, par mois ;
  - **Production** : production brute vs production autoconsommée, par mois ;
- Si aucune donnée n'est disponible, un graphique « vide » avec le message *« Aucune donnée disponible »* est tout de même produit (le rapport ne plante jamais faute de données) ;
- Le graphique est renvoyé en **image PNG encodée en base64**, intégrable directement dans le template QWeb du rapport.

> Nécessite `matplotlib` installé côté serveur. En son absence, la méthode retourne `None` et le template doit gérer l'absence d'image.

## Menus

```
Communauté d'énergie                          (menu_energy_community_root)
├── Tableau de bord                           (menu_energy_dashboard)
│   ├── Consommation
│   │   ├── Par Jour / Par Semaine / Par Mois / Par Année
│   └── Production
│       ├── Par Jour / Par Semaine / Par Mois / Par Année
├── Productions                               (liste énergie.community.production)
├── Consommations                             (liste énergie.community.consumption)
├── Importer ORES (CSV)
├── Importer RESA (Excel)
└── Générer factures (période)
```

## Sécurité / droits d'accès

Tous les modèles du module sont accessibles en **lecture / écriture / création / suppression** au groupe **`base.group_user`** (utilisateur interne standard) :

| Modèle | Accès |
|---|---|
| `energy.community` | CRUD complet — utilisateurs internes |
| `energy.community.production` | CRUD complet — utilisateurs internes |
| `energy.community.consumption` | CRUD complet — utilisateurs internes |
| `energy.community.participant` | CRUD complet — utilisateurs internes |
| `import.ores.wizard` | CRUD complet — utilisateurs internes |
| `import.resa.wizard` | CRUD complet — utilisateurs internes |
| `energy.invoice.generator.wizard` | CRUD complet — utilisateurs internes |

> ⚠️ Aucune restriction par groupe métier spécifique (ex. comptabilité) n'est définie : **tout utilisateur interne** peut importer des données et générer des factures brouillon. Le générateur de factures sur période vérifie néanmoins que l'utilisateur possède le groupe `account.group_account_invoice` avant de créer effectivement des factures. Il est recommandé d'adapter `ir.model.access.csv` (ou d'ajouter des règles d'enregistrement) selon vos besoins de séparation des rôles.

## Formats de fichiers attendus

### Fichier ORES (CSV)

- Encodage : `UTF-8` avec BOM (`utf-8-sig`) accepté ;
- Délimiteur : `;` ;
- Colonne `EAN` obligatoire, colonne `Timestamp` au format `YYYY-MM-DD HH:MM:SS` ou `YYYY-MM-DD HH:MM` ;
- **Fichier de production** — colonnes attendues : `Production brute`, `Coefficient`, `Production allouée au partage`, `Production allouée autoconsommée par le partage`, `Production non allouée au partage`, `Allo Production` ;
- **Fichier de consommation** — colonnes attendues : `Itération`, `Coefficient`, `Prélèvement brut`, `Production mise à disposition par le partage`, `Prélèvement couvert par le partage`, `Surplus de production`, `Allo Consommation` ;
- Les nombres peuvent utiliser la virgule comme séparateur décimal et l'espace (ou espace insécable) comme séparateur de milliers ; ces formats sont normalisés automatiquement.

### Fichier RESA (Excel .xlsx)

- Lu via `openpyxl` (`data_only=True`, donc les formules doivent déjà être calculées dans le fichier source) ;
- Toutes les feuilles du classeur sont analysées pour en extraire les EAN et leur type (Prélèvement/Injection) ;
- Le mois peut être détecté depuis le nom du fichier ou, à défaut, depuis le contenu des cellules (20 premières lignes, 10 premières colonnes de chaque feuille).

## Tarifs facturés

Ces constantes sont définies **en dur** dans le code (`import_ores_wizard.py`, `import_resa_wizard.py`, `generate_invoices_wizard.py`) et s'ajoutent au prix de vente configuré sur l'opération de partage, **uniquement sur les factures client (consommation)** :

| Constante | Valeur | Libellé sur la facture |
|---|---|---|
| `CV_RESTITUTION_PRICE` | 0,026 €/kWh HTVA | Coût de la restitution des CV |
| `ACCISES_2026_PRICE` | 0,046 €/kWh HTVA | Droit d'accises spécial 2026 (tarif unique) |

> ⚠️ Ces montants sont **codés en dur** et non paramétrables depuis l'interface. Toute évolution tarifaire nécessite une modification du code source (les trois fichiers cités doivent être mis à jour de façon cohérente, la logique y étant dupliquée).

## Limitations connues / points d'attention

- **Logique dupliquée** : la génération de factures est implémentée de façon quasi identique dans les trois wizards. Une correction ou évolution tarifaire doit être répercutée dans les trois fichiers.
- **Tarifs en dur** : `CV_RESTITUTION_PRICE` et `ACCISES_2026_PRICE` ne sont pas configurables via l'UI.
- **Un seul journal utilisé** : `_get_invoice_journal()` prend le **premier** journal trouvé du type achat/vente (`search(..., limit=1)`) ; en multi-journaux, il n'y a pas de sélection explicite du journal à utiliser.
- **Dépendance à la référence de facture** : le rattachement du graphique (EAN, opération, période) sur le rapport repose sur le **parsing du champ `ref`** de la facture. Modifier manuellement cette référence casse l'affichage du graphique.
- **Silence des erreurs ligne par ligne** : lors de l'import, une ligne en erreur est journalisée (`_logger.warning`) et **ignorée**, sans interrompre l'import global — vérifier les logs serveur en cas de résultat inattendu.
- **`matplotlib` optionnel mais recommandé** : sans ce paquet, les factures s'impriment sans graphique de consommation/production.
- **Sécurité large** : tous les utilisateurs internes ont un accès complet aux données et aux wizards d'import/facturation (voir section Sécurité).

## Dépannage (FAQ)

**Le type de fichier ORES n'est pas détecté automatiquement.**
→ Vérifiez que les en-têtes du CSV correspondent aux libellés attendus (voir [Formats de fichiers attendus](#formats-de-fichiers-attendus)). Sinon, sélectionnez manuellement *Fichier de production* ou *Fichier de consommation*.

**Le mois détecté est incorrect.**
→ Renommez le fichier en incluant clairement l'année et le mois (ex. `ORES_2026-03.csv`) avant import, ou corrigez le champ *Mois* manuellement dans le wizard avant de lancer l'import.

**Aucune facture n'est générée après import.**
→ Vérifiez que : (1) la case *Générer les factures automatiquement* est cochée, (2) `product_price` et/ou `producer_price` sont renseignés (> 0) sur l'opération de partage, (3) un journal de vente et un journal d'achat existent, (4) aucune facture équivalente n'existe déjà (le système ignore silencieusement les doublons).

**Le graphique n'apparaît pas sur la facture PDF.**
→ Vérifiez que `matplotlib` est bien installé sur le serveur Odoo (`pip install matplotlib`) et consultez les logs serveur (le module journalise abondamment cette étape).

**J'ai déplacé un participant d'une opération à une autre, ses anciennes données ont disparu de la première opération.**
→ Comportement attendu : les données historiques (production/consommation) **suivent** le participant vers sa nouvelle opération de partage (voir [Logique métier `energy.community.write()`](#logique-métier-importante--energycommunitywrite)). Elles ne sont pas dupliquées.

## Licence

Ce module est distribué sous licence **GNU Lesser General Public License v3.0 (LGPL-3)**.
Texte complet : https://www.gnu.org/licenses/lgpl-3.0.html

Copyright (c) 2026 Wattlabs
