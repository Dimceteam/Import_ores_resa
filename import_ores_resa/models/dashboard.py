from odoo import models, fields, api, _
import base64
import logging
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
from xml.sax.saxutils import escape as xml_escape

_logger = logging.getLogger(__name__)

# Couleurs utilisées pour les graphiques (identiques à la version précédente)
COLOR_CONSO_BRUT = '#0066ff'
COLOR_CONSO_COUVERT = '#00cc66'
COLOR_PROD_BRUT = '#ff6600'
COLOR_PROD_AUTOCONSO = '#9900cc'


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

        # ⭐ On génère TOUJOURS le graphique (même vide), en SVG natif (pas de dépendance externe)
        try:
            # ---- Agrégation Consommation ----
            conso_months, conso_brut, conso_couvert = self._aggregate_monthly(
                consumptions, 'prelevement_brut', 'prelevement_couvert')

            # ---- Agrégation Production ----
            prod_months, prod_brut, prod_autoconso = self._aggregate_monthly(
                productions, 'production_brute', 'production_autoconsommee')

            panel_conso = self._build_bar_chart_panel(
                title=f'Consommation - {ean or "N/A"}',
                month_keys=conso_months,
                series=[
                    ('Prélèvement brut', COLOR_CONSO_BRUT, conso_brut),
                    ('Prélèvement couvert', COLOR_CONSO_COUVERT, conso_couvert),
                ],
            )

            panel_prod = self._build_bar_chart_panel(
                title=f'Production - {ean or "N/A"}',
                month_keys=prod_months,
                series=[
                    ('Production brute', COLOR_PROD_BRUT, prod_brut),
                    ('Production autoconsommée', COLOR_PROD_AUTOCONSO, prod_autoconso),
                ],
            )

            svg = self._assemble_svg([panel_conso, panel_prod])
            img_base64 = base64.b64encode(svg.encode('utf-8')).decode('ascii')

            _logger.info(f"✅ Graphique SVG généré - Taille: {len(img_base64)} caractères")
            return img_base64

        except Exception as e:
            _logger.error(f"❌ Erreur génération graphique: {e}")
            import traceback
            _logger.error(traceback.format_exc())
            return None

    # ------------------------------------------------------------------
    # Génération de graphiques SVG natifs (sans dépendance externe)
    # ------------------------------------------------------------------

    @api.model
    def _aggregate_monthly(self, records, field_brut, field_secondaire):
        """Agrège des enregistrements (consumption/production) par mois.
        Retourne (mois_triés, valeurs_brut, valeurs_secondaire) alignés sur mois_triés."""
        data = {}
        for rec in records:
            month_key = rec.timestamp.strftime('%Y-%m')
            if month_key not in data:
                data[month_key] = [0.0, 0.0]
            data[month_key][0] += getattr(rec, field_brut, 0.0) or 0.0
            data[month_key][1] += getattr(rec, field_secondaire, 0.0) or 0.0

        months = sorted(data.keys())
        brut_values = [data[m][0] for m in months]
        secondaire_values = [data[m][1] for m in months]
        return months, brut_values, secondaire_values

    @api.model
    def _month_label(self, month_key):
        dt = datetime.strptime(month_key, '%Y-%m')
        return dt.strftime('%b %Y')

    @api.model
    def _format_value(self, value):
        if abs(value) >= 1000:
            return f'{value:,.0f}'.replace(',', ' ')
        if abs(value) >= 10:
            return f'{value:.0f}'
        return f'{value:.1f}'

    @api.model
    def _build_bar_chart_panel(self, title, month_keys, series, unit='kWh',
                                panel_width=1000, panel_height=340):
        """Construit le contenu SVG (balise <g>) d'un panneau de graphique en
        barres groupées, ou un panneau 'aucune donnée' si month_keys est vide.
        `series` est une liste de tuples (label, couleur, valeurs)."""

        left_margin = 75
        right_margin = 25
        top_margin = 65      # place pour le titre + la légende
        bottom_margin = 85   # place pour les labels de mois pivotés

        chart_x = left_margin
        chart_y = top_margin
        chart_w = panel_width - left_margin - right_margin
        chart_h = panel_height - top_margin - bottom_margin

        parts = []
        parts.append(f'<rect x="0" y="0" width="{panel_width}" height="{panel_height}" '
                      f'fill="#ffffff"/>')
        parts.append(
            f'<text x="{panel_width / 2}" y="24" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="15" font-weight="bold" '
            f'fill="#333333">{xml_escape(title)}</text>'
        )

        has_data = bool(month_keys) and any(any(v) for _, _, v in series)

        if not has_data:
            # ---- Panneau vide ----
            parts.append(
                f'<text x="{panel_width / 2}" y="{top_margin + chart_h / 2}" '
                f'text-anchor="middle" font-family="Helvetica,Arial,sans-serif" '
                f'font-size="13" font-style="italic" fill="#999999">'
                f'Aucune donnée disponible</text>'
            )
            parts.append(
                f'<rect x="{chart_x}" y="{chart_y}" width="{chart_w}" height="{chart_h}" '
                f'fill="none" stroke="#dddddd" stroke-width="1"/>'
            )
            return f'<g>{"".join(parts)}</g>'

        # ---- Légende ----
        legend_items = [(label, color) for label, color, _ in series]
        legend_gap = 22
        approx_item_w = 190
        legend_total_w = len(legend_items) * approx_item_w
        legend_x = (panel_width - legend_total_w) / 2
        legend_y = 42
        for label, color in legend_items:
            parts.append(f'<rect x="{legend_x}" y="{legend_y - 10}" width="12" height="12" '
                          f'fill="{color}" rx="2"/>')
            parts.append(
                f'<text x="{legend_x + 18}" y="{legend_y}" '
                f'font-family="Helvetica,Arial,sans-serif" font-size="10.5" '
                f'fill="#333333">{xml_escape(label)}</text>'
            )
            legend_x += approx_item_w

        # ---- Échelle Y ----
        max_value = 0.0
        for _, _, values in series:
            if values:
                max_value = max(max_value, max(values))
        if max_value <= 0:
            max_value = 1.0
        max_value *= 1.15

        nb_gridlines = 4
        for i in range(nb_gridlines + 1):
            frac = i / nb_gridlines
            y = chart_y + chart_h - frac * chart_h
            value = frac * max_value
            parts.append(
                f'<line x1="{chart_x}" y1="{y:.1f}" x2="{chart_x + chart_w}" y2="{y:.1f}" '
                f'stroke="#e0e0e0" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{chart_x - 8}" y="{y + 3:.1f}" text-anchor="end" '
                f'font-family="Helvetica,Arial,sans-serif" font-size="9.5" fill="#666666">'
                f'{self._format_value(value)}</text>'
            )
        # Axe Y (unité)
        parts.append(
            f'<text x="16" y="{chart_y + chart_h / 2:.1f}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#666666" '
            f'transform="rotate(-90 16 {chart_y + chart_h / 2:.1f})">{xml_escape(unit)}</text>'
        )

        # ---- Barres groupées ----
        nb_categories = len(month_keys)
        nb_series = len(series)
        group_w = chart_w / nb_categories
        bar_w = (group_w * 0.6) / nb_series
        inner_gap = 2

        for idx, month_key in enumerate(month_keys):
            group_center_x = chart_x + group_w * idx + group_w / 2
            first_bar_x = group_center_x - (nb_series * bar_w) / 2

            for s_idx, (label, color, values) in enumerate(series):
                value = values[idx] if idx < len(values) else 0.0
                bar_h = (value / max_value) * chart_h if max_value else 0
                bar_x = first_bar_x + s_idx * (bar_w + inner_gap)
                bar_y = chart_y + chart_h - bar_h
                parts.append(
                    f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{max(bar_w - inner_gap, 0):.1f}" '
                    f'height="{bar_h:.1f}" fill="{color}"/>'
                )

            # Label du mois, pivoté à 45°
            label_x = group_center_x
            label_y = chart_y + chart_h + 14
            month_label = xml_escape(self._month_label(month_key))
            parts.append(
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="end" '
                f'font-family="Helvetica,Arial,sans-serif" font-size="9" fill="#333333" '
                f'transform="rotate(-45 {label_x:.1f} {label_y:.1f})">{month_label}</text>'
            )

        # Cadre du graphique
        parts.append(
            f'<rect x="{chart_x}" y="{chart_y}" width="{chart_w}" height="{chart_h}" '
            f'fill="none" stroke="#cccccc" stroke-width="1"/>'
        )

        return f'<g>{"".join(parts)}</g>'

    @api.model
    def _assemble_svg(self, panels, panel_width=1000, panel_height=340, gap=30):
        """Empile verticalement une liste de panneaux (contenu <g>...</g>) dans
        un unique document SVG et retourne le SVG complet sous forme de string."""
        total_height = len(panels) * panel_height + (len(panels) - 1) * gap
        body = []
        for idx, panel in enumerate(panels):
            y_offset = idx * (panel_height + gap)
            body.append(f'<g transform="translate(0,{y_offset})">{panel}</g>')

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {panel_width} {total_height}" '
            f'width="{panel_width}" height="{total_height}">'
            f'<rect x="0" y="0" width="{panel_width}" height="{total_height}" fill="#ffffff"/>'
            f'{"".join(body)}'
            f'</svg>'
        )

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