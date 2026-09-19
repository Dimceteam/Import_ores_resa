{
    'name': 'Import ORES/RESA - Communauté d\'énergie',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': 'Module pour importer les fichiers ORES/RESA',
    'description': """
        Import des fichiers ORES/RESA pour la communauté d'énergie
        - Support des fichiers RESA (structure partagée)
        - Support des fichiers ORES (production/consommation)
        - Génération automatique des factures
        - Analyse des participants

        Note: la génération du graphique de consommation/production sur les factures
        nécessite le package Python "matplotlib" installé sur le serveur Odoo.
    """,
    'author': 'Wattlabs',
    'website': 'https://www.wattlabs.be',
    'support': 'support@wattlabs.be',
    'license': 'LGPL-3',
    'depends': ['base', 'account', 'web'],
    'external_dependencies': {
        'python': ['matplotlib', 'openpyxl'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/energy_community_views.xml',
        'views/import_ores_wizard_views.xml',
        'views/import_resa_wizard_views.xml',
        'views/generate_invoices_wizard_views.xml',
        'views/dashboard_views.xml',
        'report/invoice_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'import_ores_resa/static/src/js/import_progress.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}