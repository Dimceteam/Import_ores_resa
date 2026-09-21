{
    'name': 'Import ORES/RESA - Communauté d\'énergie',
    'version': '19.0.1.0.1',
    'category': 'Tools',
    'summary': 'Module pour importer les fichiers ORES/RESA',
    'description': """
        Import des fichiers ORES/RESA pour la communauté d'énergie
        - Support des fichiers RESA (structure partagée)
        - Support des fichiers ORES (production/consommation)
        - Génération automatique des factures
        - Analyse des participants

        Note: le graphique de consommation/production sur les factures est généré
        nativement en SVG (aucune dépendance Python externe, type matplotlib, requise).
    """,
    'author': 'Wattlabs',
    'website': 'https://www.wattlabs.be',
    'support': 'support@wattlabs.be',
    'license': 'LGPL-3',
    'depends': ['base', 'account', 'web'],
    'external_dependencies': {
        'python': ['openpyxl'],
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
    'images': [
        'static/description/banner.png',
        'static/description/screenshot1.png',
        'static/description/screenshot2.png',
        'static/description/screenshot3.png',
        'static/description/screenshot4.png',
        'static/description/screenshot5.png',
        'static/description/screenshot6.png',
        'static/description/screenshot7.png',
        'static/description/screenshot8.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
