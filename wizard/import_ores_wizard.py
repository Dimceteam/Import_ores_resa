import base64
import csv
import io
import logging
import re
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

BATCH_SIZE = 2000

# === NOUVEAUX TARIFS (€/kWh HTVA) ===
CV_RESTITUTION_PRICE = 0.026
ACCISES_2026_PRICE = 0.046


class ImportOresWizard(models.TransientModel):
    _name = 'import.ores.wizard'
    _description = 'Assistant Import ORES'

    file_name = fields.Char(string='Nom du fichier')
    file_content = fields.Binary(string='Fichier CSV', required=True)
    file_type = fields.Selection([
        ('production', 'Fichier de production'),
        ('consumption', 'Fichier de consommation'),
        ('auto', 'Détection automatique')
    ], string='Type de fichier', required=True, default='auto')

    detected_file_type = fields.Char(string='Type détecté', readonly=True)

    community_id = fields.Many2one('energy.community',
                                   string='Opération de partage', required=True)
    month = fields.Char(string='Mois (YYYY-MM)')

    new_participants = fields.Text(string='Nouveaux participants à créer', readonly=True)
    existing_participants = fields.Text(string='Participants déjà existants', readonly=True)
    has_new_participants = fields.Boolean(string='A des nouveaux participants', default=False)
    confirm_import = fields.Boolean(
        string='Je confirme l\'ajout de ces nouveaux participants', default=False)
    import_enabled = fields.Boolean(string='Import activé', default=False)

    generate_invoices = fields.Boolean(
        string='Générer les factures automatiquement', default=False)
    invoice_date = fields.Date(string='Date de facture', default=fields.Date.today)
    payment_term_id = fields.Many2one('account.payment.term', string='Condition de paiement')

    @api.constrains('month')
    def _check_month(self):
        for record in self:
            if record.month:
                try:
                    datetime.strptime(record.month, '%Y-%m')
                except ValueError:
                    raise ValidationError(_("Le mois doit être au format YYYY-MM"))

    def _detect_file_type_from_headers(self, headers):
        production_keywords = [
            'production brute', 'production allouée', 'production allouee',
            'coefficient', 'allo production', 'production autoconsommée',
            'production autoconsommee', 'production non allouée', 'production non allouee']
        consumption_keywords = [
            'prélèvement brut', 'prelevement brut', 'prélèvement', 'prelevement',
            'itération', 'iteration', 'surplus de production', 'surplus production',
            'allo consommation', 'prelevement couvert', 'prélèvement couvert',
            'production mise à disposition', 'production mise a disposition']
        headers_lower = [h.lower().strip() for h in headers if h]
        p_count = c_count = 0
        for header in headers_lower:
            for kw in production_keywords:
                if kw in header:
                    p_count += 1
                    break
            for kw in consumption_keywords:
                if kw in header:
                    c_count += 1
                    break
        if p_count > c_count:
            return 'production'
        elif c_count > p_count:
            return 'consumption'
        else:
            if any('production brute' in h for h in headers_lower):
                return 'production'
            if any('prélèvement brut' in h or 'prelevement brut' in h for h in headers_lower):
                return 'consumption'
            return None

    @api.onchange('file_content')
    def _onchange_file_content(self):
        self.new_participants = False
        self.existing_participants = False
        self.has_new_participants = False
        self.confirm_import = False
        self.import_enabled = False
        self.detected_file_type = False

        if not self.file_content:
            return

        try:
            self._detect_month()
            csv_data = base64.b64decode(self.file_content)
            data_file = io.StringIO(csv_data.decode("utf-8-sig"))
            csv_reader = csv.DictReader(data_file, delimiter=';')
            headers = csv_reader.fieldnames or []
            detected_type = self._detect_file_type_from_headers(headers)

            if detected_type:
                self.detected_file_type = dict(self._fields['file_type'].selection).get(
                    detected_type, detected_type)
                if self.file_type == 'auto':
                    self.file_type = detected_type
            else:
                self.detected_file_type = "❌ Non détecté - Veuillez sélectionner manuellement"

            data_file.seek(0)
            csv_reader = csv.DictReader(data_file, delimiter=';')
            rows = list(csv_reader)

            if not rows:
                self.new_participants = "⚠️ Le fichier est vide"
                return

            all_ean = set()
            for row in rows:
                ean = row.get('EAN', '').strip()
                if ean:
                    all_ean.add(ean)

            if not all_ean:
                self.new_participants = "⚠️ Aucun EAN trouvé dans le fichier"
                return

            existing_ean_list = []
            if self.community_id.partner_ids:
                existing_ean_list = self.community_id.partner_ids.mapped('ref')

            new_list = []
            existing_list = []
            for ean in all_ean:
                if ean in existing_ean_list:
                    partner = self.env['res.partner'].search([('ref', '=', ean)], limit=1)
                    existing_list.append(f"✅ {ean} - {partner.name if partner else ean}")
                else:
                    new_list.append(f"🆕 {ean}")

            self.new_participants = "\n".join(new_list) if new_list else "Aucun nouveau participant"
            self.existing_participants = ("\n".join(existing_list) if existing_list
                                          else "Aucun participant existant")
            self.has_new_participants = bool(new_list)

            if (not self.has_new_participants
                    and self.new_participants != "⚠️ Le fichier est vide"
                    and self.new_participants != "⚠️ Aucun EAN trouvé dans le fichier"):
                self.import_enabled = True
                self.confirm_import = False
            else:
                self.confirm_import = False
                self.import_enabled = False

        except Exception as e:
            self.new_participants = f"⚠️ Erreur de lecture du fichier: {str(e)}"
            self.import_enabled = False
            _logger.error(f"Erreur analyse fichier ORES: {e}")

    def _detect_month(self):
        if not self.file_name:
            return
        patterns = [
            r'(\d{4})[-_ ](\d{1,2})',
            r'(\d{1,2})[-_](\d{4})',
            r'(\d{4})(\d{2})']
        for pattern in patterns:
            match = re.search(pattern, self.file_name)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    if len(groups[0]) == 4:
                        year, month = groups[0], groups[1]
                    else:
                        month, year = groups[0], groups[1]
                    self.month = f"{year}-{int(month):02d}"
                    return

        if self.file_content:
            try:
                csv_data = base64.b64decode(self.file_content)
                data_file = io.StringIO(csv_data.decode("utf-8-sig"))
                first_lines = data_file.readlines()[:10]
                for line in first_lines:
                    match = re.search(r'(\d{4})[-/](\d{1,2})', line)
                    if match:
                        year, month = match.groups()
                        self.month = f"{year}-{int(month):02d}"
                        return
            except Exception:
                pass

        if not self.month:
            self.month = datetime.now().strftime('%Y-%m')

    @api.onchange('confirm_import')
    def _onchange_confirm_import(self):
        self.import_enabled = self.confirm_import

    def action_import(self):
        if not self.file_content:
            raise UserError(_("Veuillez sélectionner un fichier."))
        if not self.month:
            self._detect_month()
        if not self.month:
            raise UserError(_("Impossible de détecter le mois."))

        if self.file_type == 'auto':
            csv_data = base64.b64decode(self.file_content)
            data_file = io.StringIO(csv_data.decode("utf-8-sig"))
            csv_reader = csv.DictReader(data_file, delimiter=';')
            headers = csv_reader.fieldnames or []
            detected_type = self._detect_file_type_from_headers(headers)
            if detected_type:
                self.file_type = detected_type
            else:
                raise UserError(_("Impossible de détecter automatiquement le type de fichier."))

        if self.has_new_participants and not self.confirm_import:
            raise UserError(_("Veuillez confirmer l'ajout des nouveaux participants."))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'import.ores.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('import_ores_resa.view_import_ores_progress_form').id,
            'target': 'new',
            'name': _('Importation en cours...'),
        }

    def action_do_import(self):
        """
        Import synchrone AVEC CACHE (corrigé).
        Cache stocké dans un dict Python local (pas d'attribut d'enregistrement).
        """
        self.ensure_one()

        csv_data = base64.b64decode(self.file_content)
        data_file = io.StringIO(csv_data.decode("utf-8-sig"))
        csv_reader = csv.DictReader(data_file, delimiter=';')
        rows = list(csv_reader)

        if not rows:
            raise UserError(_("Le fichier CSV est vide."))

        # 🎯 Cache LOCAL
        cache = {'partners': {}, 'recs': {}}

        all_partners = self.env['res.partner'].search([('ref', '!=', False)])
        cache['partners'] = {p.ref: p for p in all_partners}
        _logger.info(f"[ORES] Cache partners: {len(cache['partners'])} entrées")

        if self.file_type == 'production':
            existing = self.env['energy.community.production'].search([
                ('community_id', '=', self.community_id.id),
                ('month', '=', self.month)])
            cache['recs'] = {(r.timestamp, r.ean): r for r in existing}
            _logger.info(f"[ORES] Cache productions: {len(cache['recs'])} entrées")
            self._import_production(rows, cache)
            model_name = 'energy.community.production'
            view_name = "Productions"
        else:
            existing = self.env['energy.community.consumption'].search([
                ('community_id', '=', self.community_id.id),
                ('month', '=', self.month)])
            cache['recs'] = {(r.timestamp, r.ean, r.iteration): r for r in existing}
            _logger.info(f"[ORES] Cache consommations: {len(cache['recs'])} entrées")
            self._import_consumption(rows, cache)
            model_name = 'energy.community.consumption'
            view_name = "Consommations"

        self.env.cr.commit()

        if self.generate_invoices:
            try:
                self._generate_invoices()
                self.env.cr.commit()
            except Exception as e:
                _logger.warning(f"Erreur génération factures: {e}")

        return {
            'type': 'ir.actions.act_window',
            'res_model': model_name,
            'view_mode': 'list,form',
            'target': 'main',
            'domain': [('community_id', '=', self.community_id.id),
                       ('month', '=', self.month)],
            'name': f"{view_name} - {self.community_id.name} - {self.month}",
            'context': {
                'default_community_id': self.community_id.id,
                'default_month': self.month,
            },
        }

    def _get_or_create_partner(self, ean, cache):
        partner = cache['partners'].get(ean)
        if partner:
            if partner.id not in self.community_id.partner_ids.ids:
                self.community_id.write({'partner_ids': [(4, partner.id)]})
            return partner
        partner = self.env['res.partner'].create({
            'name': f'Participant {ean}',
            'ref': ean,
        })
        cache['partners'][ean] = partner
        self.community_id.write({'partner_ids': [(4, partner.id)]})
        return partner

    def _clean_number(self, val):
        if not val or val == '':
            return 0.0
        if not isinstance(val, str):
            try:
                return float(val)
            except Exception:
                return 0.0
        val_str = str(val).strip()
        if re.match(r'^-?\d+\.\d+$', val_str):
            try:
                return float(val_str)
            except Exception:
                pass
        if ' ' in val_str or '\xa0' in val_str:
            val_str = val_str.replace('\xa0', ' ').replace(' ', '').replace(',', '.')
            try:
                return float(val_str)
            except Exception:
                pass
        if ',' in val_str:
            val_str = val_str.replace(',', '.')
            try:
                return float(val_str)
            except Exception:
                pass
        val_str = re.sub(r'[^\d.]', '', val_str)
        try:
            return float(val_str) if val_str else 0.0
        except Exception:
            return 0.0

    def _to_float(self, val):
        try:
            return self._clean_number(val)
        except Exception as e:
            _logger.warning(f"Erreur conversion {val}: {e}")
            return 0.0

    def _import_production(self, rows, cache):
        count = 0
        for row in rows:
            try:
                ean = row.get('EAN', '').strip()
                if not ean:
                    continue
                partner = self._get_or_create_partner(ean, cache)
                timestamp_str = row.get('Timestamp', '').strip()
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M')

                vals = {
                    'timestamp': timestamp, 'ean': ean, 'partner_id': partner.id,
                    'community_id': self.community_id.id, 'month': self.month,
                    'production_brute': self._to_float(row.get('Production brute')),
                    'coefficient': self._to_float(row.get('Coefficient')) * 100,
                    'production_allouee': self._to_float(row.get('Production allouée au partage')),
                    'production_autoconsommee': self._to_float(
                        row.get('Production allouée autoconsommée par le partage')),
                    'production_non_allouee': self._to_float(
                        row.get('Production non allouée au partage')),
                    'allo_production': self._to_float(row.get('Allo Production')),
                }

                key = (timestamp, ean)
                existing = cache['recs'].get(key)
                if existing:
                    existing.write(vals)
                else:
                    rec = self.env['energy.community.production'].create(vals)
                    cache['recs'][key] = rec

                count += 1
                if count % BATCH_SIZE == 0:
                    self.env.cr.commit()
                    _logger.info(f"[ORES-prod] Commit après {count} lignes")

            except Exception as e:
                _logger.warning(f"Erreur import production ligne {row}: {e}")

        self.env.cr.commit()

    def _import_consumption(self, rows, cache):
        count = 0
        for row in rows:
            try:
                ean = row.get('EAN', '').strip()
                if not ean:
                    continue
                partner = self._get_or_create_partner(ean, cache)
                timestamp_str = row.get('Timestamp', '').strip()
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M')

                iteration = int(row.get('Itération', 0)) if row.get('Itération') else 0

                vals = {
                    'timestamp': timestamp, 'ean': ean, 'iteration': iteration,
                    'partner_id': partner.id,
                    'community_id': self.community_id.id, 'month': self.month,
                    'coefficient': self._to_float(row.get('Coefficient')) * 100,
                    'prelevement_brut': self._to_float(row.get('Prélèvement brut')),
                    'production_mise_disposition': self._to_float(
                        row.get('Production mise à disposition par le partage')),
                    'prelevement_couvert': self._to_float(
                        row.get('Prélèvement couvert par le partage')),
                    'surplus_production': self._to_float(row.get('Surplus de production')),
                    'allo_consommation': self._to_float(row.get('Allo Consommation')),
                }

                key = (timestamp, ean, iteration)
                existing = cache['recs'].get(key)
                if existing:
                    existing.write(vals)
                else:
                    rec = self.env['energy.community.consumption'].create(vals)
                    cache['recs'][key] = rec

                count += 1
                if count % BATCH_SIZE == 0:
                    self.env.cr.commit()
                    _logger.info(f"[ORES-conso] Commit après {count} lignes")

            except Exception as e:
                _logger.warning(f"Erreur import consommation ligne {row}: {e}")

        self.env.cr.commit()

    # ==========================================
    # FACTURATION
    # ==========================================

    def _get_tax_6_percent(self):
     tax_group = self.env['account.tax.group'].search([('name', 'ilike', '6%')], limit=1)
     tax = self.env['account.tax'].search([
        ('name', '=', 'TVA 6%'),
        ('company_id', '=', self.env.company.id)], limit=1)
     if not tax:
        tax = self.env['account.tax'].create({
            'name': 'TVA 6%', 'amount': 6.0, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'tax_exigibility': 'on_invoice',
            'description': 'TVA 6% (énergie)', 'company_id': self.env.company.id,
            'tax_group_id': tax_group.id if tax_group else False,
        })
     return tax

    def _get_invoice_journal(self, file_type):
        journal_type = 'purchase' if file_type == 'production' else 'sale'
        return self.env['account.journal'].search([('type', '=', journal_type)], limit=1)

    def _get_payment_term_30_days(self):
        payment_term = self.env['account.payment.term'].search(
            [('name', 'ilike', '30%')], limit=1)
        if not payment_term:
            payment_term = self.env['account.payment.term'].create({
                'name': '30 jours fin de mois',
                'note': 'Paiement à 30 jours fin de mois',
                'line_ids': [(0, 0, {
                    'value': 'balance', 'days': 30,
                    'days_type': 'end_of_month', 'sequence': 1,
                })]
            })
        return payment_term

    def _generate_invoices(self):
        self.ensure_one()
        tax_6 = self._get_tax_6_percent()
        payment_term = self.payment_term_id or self._get_payment_term_30_days()
        self._generate_ores_consumption_invoices(tax_6, payment_term)
        self._generate_ores_production_invoices(tax_6, payment_term)

    def _generate_ores_consumption_invoices(self, tax_6, payment_term):
        journal = self._get_invoice_journal('consumption')
        if not journal:
            return
        consumptions = self.env['energy.community.consumption'].search([
            ('community_id', '=', self.community_id.id),
            ('month', '=', self.month)])
        consumption_by_ean = {}
        for cons in consumptions:
            ean = cons.ean
            if ean not in consumption_by_ean:
                consumption_by_ean[ean] = {
                    'prelevement_couvert': 0.0,
                    'partner_id': cons.partner_id.id}
            consumption_by_ean[ean]['prelevement_couvert'] += cons.prelevement_couvert
        product_price = self.community_id.product_price or 0.0
        for ean, data in consumption_by_ean.items():
            if data['prelevement_couvert'] > 0 and product_price > 0:
                partner = self.env['res.partner'].browse(data['partner_id'])
                if self._invoice_exists(partner.id, 'out_invoice',
                                        self.month, self.community_id, ean):
                    continue
                quantity = data['prelevement_couvert']
                unit_price = product_price
                total = quantity * unit_price
                description = (
                    f"Consommation énergie partagée - {self.month}\n"
                    f"Prélèvement couvert : {quantity:.3f} kWh\n"
                    f"Prix de vente : {unit_price:.3f} €/kWh\n"
                    f"Sous-total : {total:.2f} €")
                invoice_lines = [{
                    'name': description, 'quantity': quantity,
                    'price_unit': unit_price, 'tax_ids': [(6, 0, [tax_6.id])]}]

                # === NOUVELLES LIGNES : CV + ACCISES (facture CLIENT uniquement) ===
                cv_total = quantity * CV_RESTITUTION_PRICE
                invoice_lines.append({
                    'name': (
                        f"Coût de la restitution des CV - {self.month}\n"
                        f"Prélèvement couvert : {quantity:.3f} kWh\n"
                        f"Tarif : {CV_RESTITUTION_PRICE:.3f} €/kWh HTVA\n"
                        f"Sous-total : {cv_total:.2f} €"),
                    'quantity': quantity,
                    'price_unit': CV_RESTITUTION_PRICE,
                    'tax_ids': [(6, 0, [tax_6.id])],
                })
                accises_total = quantity * ACCISES_2026_PRICE
                invoice_lines.append({
                    'name': (
                        f"Droit d'accises spécial 2026 (tarif unique) - {self.month}\n"
                        f"Prélèvement couvert : {quantity:.3f} kWh\n"
                        f"Tarif : {ACCISES_2026_PRICE:.3f} €/kWh HTVA\n"
                        f"Sous-total : {accises_total:.2f} €"),
                    'quantity': quantity,
                    'price_unit': ACCISES_2026_PRICE,
                    'tax_ids': [(6, 0, [tax_6.id])],
                })

                self._create_draft_invoice(partner, invoice_lines, ean,
                                           journal, payment_term, 'out_invoice')

    def _generate_ores_production_invoices(self, tax_6, payment_term):
        journal = self._get_invoice_journal('production')
        if not journal:
            return
        productions = self.env['energy.community.production'].search([
            ('community_id', '=', self.community_id.id),
            ('month', '=', self.month)])
        production_by_ean = {}
        for prod in productions:
            ean = prod.ean
            if ean not in production_by_ean:
                production_by_ean[ean] = {
                    'production_autoconsommee': 0.0,
                    'partner_id': prod.partner_id.id}
            production_by_ean[ean]['production_autoconsommee'] += prod.production_autoconsommee
        producer_price = self.community_id.producer_price or 0.0
        for ean, data in production_by_ean.items():
            if data['production_autoconsommee'] > 0 and producer_price > 0:
                partner = self.env['res.partner'].browse(data['partner_id'])
                if self._invoice_exists(partner.id, 'in_invoice',
                                        self.month, self.community_id, ean):
                    continue
                quantity = data['production_autoconsommee']
                unit_price = producer_price
                total = quantity * unit_price
                description = (
                    f"Rémunération énergie partagée - {self.month}\n"
                    f"Production autoconsommée : {quantity:.3f} kWh\n"
                    f"Prix d'achat : {unit_price:.3f} €/kWh\n"
                    f"Sous-total : {total:.2f} €")
                invoice_lines = [{
                    'name': description, 'quantity': quantity,
                    'price_unit': unit_price, 'tax_ids': [(6, 0, [tax_6.id])]}]
                self._create_draft_invoice(partner, invoice_lines, ean,
                                           journal, payment_term, 'in_invoice')

    def _invoice_exists(self, partner_id, move_type, month, community_id, ean):
        ref_prefix = f'Opération de partage {community_id.name} - {month} - {ean}'
        existing = self.env['account.move'].search([
            ('partner_id', '=', partner_id),
            ('move_type', '=', move_type),
            ('state', 'in', ['draft', 'posted']),
            ('ref', 'ilike', ref_prefix),
        ], limit=1)
        return bool(existing)

    def _create_draft_invoice(self, partner, invoice_lines, ean, journal,
                              payment_term, move_type):
        try:
            line_vals_list = []
            for line in invoice_lines:
                line_vals = {
                    'name': line['name'], 'quantity': line['quantity'],
                    'price_unit': line['price_unit'],
                    'tax_ids': line.get('tax_ids', [(6, 0, [])])}
                line_vals_list.append((0, 0, line_vals))
            invoice_vals = {
                'partner_id': partner.id, 'move_type': move_type,
                'invoice_date': self.invoice_date or fields.Date.today(),
                'journal_id': journal.id,
                'ref': f'Opération de partage {self.community_id.name} - {self.month} - {ean}',
                'invoice_line_ids': line_vals_list,
                'invoice_payment_term_id': payment_term.id,
                'state': 'draft'}
            self.env['account.move'].create(invoice_vals)
        except Exception as e:
            _logger.warning(f"Erreur création facture ORES pour {ean}: {e}")