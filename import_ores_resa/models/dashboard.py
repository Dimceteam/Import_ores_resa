from odoo import models, fields, api, _
import base64
import io
import logging
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def get_consumption_graph_for_invoice(self):
        """
        Génère un graphique de consommation/production pour la facture.
        Retourne TOUJOURS une image base64 (graphique vide si pas de données).
        """
        self.ensure_one()

        _logger.info("=" * 60)
        _logger.info("get_consumption_graph_for_invoice appelé")
        _logger.info(f"Facture ID: {self.id}")
        _logger.info(f"Référence: {self.ref}")
        _logger.info(f"Date facture: {self.invoice_date}")

        ean = self._extract_ean_from_ref()
        _logger.info(f"EAN extrait: {ean}")

        community = self._get_community_from_invoice()
        _logger.info(f"Communauté: {community.name if community else 'None'}")

        # Calcul de la période : 12 mois avant le MOIS FACTURÉ (pas la date de facture)
        period_end = self._extract_period_end_from_ref()

        if period_end:
            reference_month = period_end.replace(day=1)
        else:
            invoice_date = self.invoice_date or fields.Date.today()
            reference_month = invoice_date.replace(day=1)

        date_from = reference_month - relativedelta(months=12)
        date_to = reference_month - relativedelta(days=1)

        _logger.info(f"Période graphique : du {date_from} au {date_to}")

        # Recherche des données (peut être vide)
        consumptions = self.env['energy.community.consumption']
        productions = self.env['energy.community.production']

        if ean and community:
            consumptions = self.env['energy.community.consumption'].search([
                ('community_id', '=', community.id),
                ('ean', '=', ean),
                ('timestamp', '>=', date_from),
                ('timestamp', '<=', date_to),
            ], order='timestamp')

            productions = self.env['energy.community.production'].search([
                ('community_id', '=', community.id),
                ('ean', '=', ean),
                ('timestamp', '>=', date_from),
                ('timestamp', '<=', date_to),
            ], order='timestamp')

        _logger.info(f"Consommations trouvées: {len(consumptions)}")
        _logger.info(f"Productions trouvées: {len(productions)}")

        # ⭐ On génère TOUJOURS le graphique (même vide)
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7))

            # ---- Consommation ----
            if consumptions:
                conso_data = {}
                for c in consumptions:
                    month_key = c.timestamp.strftime('%Y-%m')
                    if month_key not in conso_data:
                        conso_data[month_key] = {'brut': 0.0, 'couvert': 0.0}
                    conso_data[month_key]['brut'] += c.prelevement_brut or 0.0
                    conso_data[month_key]['couvert'] += c.prelevement_couvert or 0.0

                months = sorted(conso_data.keys())
                if months:
                    month_labels = []
                    for m in months:
                        dt = datetime.strptime(m, '%Y-%m')
                        month_labels.append(dt.strftime('%b %Y'))

                    brut_values = [conso_data[m]['brut'] for m in months]
                    couvert_values = [conso_data[m]['couvert'] for m in months]

                    x = range(len(months))
                    width = 0.35
                    ax1.bar([i - width / 2 for i in x], brut_values, width,
                            label='Prélèvement brut', color='#0066ff')
                    ax1.bar([i + width / 2 for i in x], couvert_values, width,
                            label='Prélèvement couvert', color='#00cc66')
                    ax1.set_xticks(x)
                    ax1.set_xticklabels(month_labels, rotation=45, ha='right', fontsize=8)
                    ax1.set_ylabel('kWh', fontsize=10)
                    ax1.set_title(f'Consommation - {ean or "N/A"}',
                                  fontsize=12, fontweight='bold')
                    ax1.legend(fontsize=9)
                    ax1.grid(True, alpha=0.3)
                else:
                    self._draw_empty_axes(ax1, 'Consommation', ean)
            else:
                self._draw_empty_axes(ax1, 'Consommation', ean)

            # ---- Production ----
            if productions:
                prod_data = {}
                for p in productions:
                    month_key = p.timestamp.strftime('%Y-%m')
                    if month_key not in prod_data:
                        prod_data[month_key] = {'brut': 0.0, 'autoconsommee': 0.0}
                    prod_data[month_key]['brut'] += p.production_brute or 0.0
                    prod_data[month_key]['autoconsommee'] += p.production_autoconsommee or 0.0

                months = sorted(prod_data.keys())
                if months:
                    month_labels = []
                    for m in months:
                        dt = datetime.strptime(m, '%Y-%m')
                        month_labels.append(dt.strftime('%b %Y'))

                    brut_values = [prod_data[m]['brut'] for m in months]
                    autoconsommee_values = [prod_data[m]['autoconsommee'] for m in months]

                    x = range(len(months))
                    width = 0.35
                    ax2.bar([i - width / 2 for i in x], brut_values, width,
                            label='Production brute', color='#ff6600')
                    ax2.bar([i + width / 2 for i in x], autoconsommee_values, width,
                            label='Production autoconsommée', color='#9900cc')
                    ax2.set_xticks(x)
                    ax2.set_xticklabels(month_labels, rotation=45, ha='right', fontsize=8)
                    ax2.set_ylabel('kWh', fontsize=10)
                    ax2.set_title(f'Production - {ean or "N/A"}',
                                  fontsize=12, fontweight='bold')
                    ax2.legend(fontsize=9)
                    ax2.grid(True, alpha=0.3)
                else:
                    self._draw_empty_axes(ax2, 'Production', ean)
            else:
                self._draw_empty_axes(ax2, 'Production', ean)

            plt.tight_layout()

            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=120, bbox_inches='tight')
            img_buffer.seek(0)
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            plt.close(fig)

            _logger.info(f"✅ Graphique généré - Taille: {len(img_base64)} caractères")
            return img_base64

        except Exception as e:
            _logger.error(f"❌ Erreur génération graphique: {e}")
            import traceback
            _logger.error(traceback.format_exc())
            # Même en cas d'erreur matplotlib, on renvoie None (le template gère)
            return None

    def _draw_empty_axes(self, ax, title, ean):
        """Dessine un graphique vide avec un message 'Aucune donnée'."""
        ax.text(0.5, 0.5, 'Aucune donnée disponible',
                ha='center', va='center', transform=ax.transAxes,
                fontsize=12, color='#999', style='italic')
        ax.set_title(f'{title} - {ean or "N/A"}', fontsize=12, fontweight='bold')
        ax.set_ylabel('kWh', fontsize=10)
        ax.set_xticks([])
        ax.grid(True, alpha=0.3)

    def _extract_ean_from_ref(self):
        """Extrait l'EAN depuis la référence de la facture"""
        if not self.ref:
            return None
        parts = self.ref.split(' - ')
        if len(parts) >= 3:
            ean_part = parts[-1].strip()
            if ean_part.startswith('EAN'):
                return ean_part
            elif len(re.sub(r'[^0-9]', '', ean_part)) >= 10:
                return ean_part
        return None

    def _extract_period_end_from_ref(self):
        """
        Extrait la date de fin de période depuis la référence de la facture.
        Supporte :
          - "Opération de partage XXX - 2023-01 - EAN"
          - "Opération de partage XXX - Période 2023-01-01 au 2023-01-31 - EAN"
        """
        if not self.ref:
            return None

        # Cas 1 : période explicite "Période YYYY-MM-DD au YYYY-MM-DD"
        match = re.search(
            r'Période\s+(\d{4}-\d{2}-\d{2})\s+au\s+(\d{4}-\d{2}-\d{2})',
            self.ref)
        if match:
            try:
                return datetime.strptime(match.group(2), '%Y-%m-%d').date()
            except ValueError:
                pass

        # Cas 2 : mois "YYYY-MM" entre deux tirets
        match = re.search(r'-\s*(\d{4}-\d{2})\s*-', self.ref)
        if match:
            try:
                return datetime.strptime(match.group(1) + '-01', '%Y-%m-%d').date()
            except ValueError:
                pass

        return None

    def _get_community_from_invoice(self):
        """Récupère la communauté depuis la facture"""
        if self.ref:
            parts = self.ref.split(' - ')
            if len(parts) >= 1:
                community_name = parts[0].strip()
                # Nettoyer le préfixe "Opération de partage "
                if community_name.lower().startswith('opération de partage '):
                    community_name = community_name[len('Opération de partage '):].strip()
                community = self.env['energy.community'].search([
                    ('name', 'ilike', community_name)
                ], limit=1)
                if community:
                    return community

        for line in self.invoice_line_ids:
            if line.product_id and line.product_id.name:
                if ('énergie' in line.product_id.name.lower()
                        or 'consommation' in line.product_id.name.lower()):
                    community = self.env['energy.community'].search([
                        ('name', 'ilike', line.product_id.name)
                    ], limit=1)
                    if community:
                        return community

        community = self.env['energy.community'].search([], limit=1)
        if community:
            return community

        return None