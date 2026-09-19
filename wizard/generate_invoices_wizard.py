import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# === NOUVEAUX TARIFS (€/kWh HTVA) ===
CV_RESTITUTION_PRICE = 0.026
ACCISES_2026_PRICE = 0.046


class EnergyInvoiceGeneratorWizard(models.TransientModel):
    _name = 'energy.invoice.generator.wizard'
    _description = 'Générer les factures pour une période'

    community_id = fields.Many2one('energy.community',
                                   string='Opération de partage', required=True)
    partner_ids = fields.Many2many(
        'res.partner',
        string='Participants (laisser vide = tous)',
        help="Sélectionnez un ou plusieurs participants pour ne générer "
             "que leurs factures. Laissez vide pour générer pour tous.")
    allowed_partner_ids = fields.Many2many(
        'res.partner',
        'energy_inv_gen_allowed_rel',
        'wizard_id', 'partner_id',
        string='Participants autorisés',
        compute='_compute_allowed_partner_ids')
    data_type = fields.Selection([
        ('both', 'Consommation + Production'),
        ('consumption', 'Consommation (factures client)'),
        ('production', 'Production (factures fournisseur)'),
    ], string='Type de données', required=True, default='both')

    date_from = fields.Date(string='Du', required=True)
    date_to = fields.Date(string='Au', required=True)

    invoice_date = fields.Date(string='Date de facture', default=fields.Date.today)
    payment_term_id = fields.Many2one('account.payment.term', string='Condition de paiement')

    # ---- Prévisualisation ----
    stat_records = fields.Integer(string='Lignes de données', compute='_compute_stats')
    stat_partners = fields.Integer(string='Participants concernés', compute='_compute_stats')
    stat_kwh = fields.Float(string='Total kWh facturables', compute='_compute_stats')
    stat_amount = fields.Float(string='Montant estimé HT (€)', compute='_compute_stats')
    stat_existing = fields.Integer(string='Factures déjà existantes', compute='_compute_stats')

    result_summary = fields.Text(string='Résultat', readonly=True)

    @api.depends('community_id')
    def _compute_allowed_partner_ids(self):
        for record in self:
            if record.community_id:
                record.allowed_partner_ids = record.community_id.partner_ids
            else:
                record.allowed_partner_ids = self.env['res.partner'].browse()

    @api.onchange('community_id')
    def _onchange_community_id(self):
        """Filtre les participants proposés sur ceux de l'opération choisie."""
        if self.community_id:
            self.partner_ids = [(6, 0, [])]
            return {'domain': {'partner_ids': [('id', 'in', self.community_id.partner_ids.ids)]}}
        return {'domain': {'partner_ids': []}}

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise UserError(_("La date de début doit être antérieure à la date de fin."))

    def _period_ref(self):
        self.ensure_one()
        return f"{self.date_from} au {self.date_to}"

    def _get_domain(self):
        self.ensure_one()
        domain = [
            ('community_id', '=', self.community_id.id),
            ('timestamp', '>=', f'{self.date_from} 00:00:00'),
            ('timestamp', '<=', f'{self.date_to} 23:59:59'),
        ]
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        return domain

    def _group_consumption(self):
        """Retourne {ean: {'quantity': kWh, 'partner_id': id}} sur la période."""
        self.ensure_one()
        result = {}
        consumptions = self.env['energy.community.consumption'].search(
            self._get_domain())
        for cons in consumptions:
            ean = cons.ean
            if not ean or not cons.partner_id:
                continue
            if ean not in result:
                result[ean] = {'quantity': 0.0, 'partner_id': cons.partner_id.id}
            result[ean]['quantity'] += cons.prelevement_couvert or 0.0
        return result, len(consumptions)

    def _group_production(self):
        """Retourne {ean: {'quantity': kWh, 'partner_id': id}} sur la période."""
        self.ensure_one()
        result = {}
        productions = self.env['energy.community.production'].search(
            self._get_domain())
        for prod in productions:
            ean = prod.ean
            if not ean or not prod.partner_id:
                continue
            if ean not in result:
                result[ean] = {'quantity': 0.0, 'partner_id': prod.partner_id.id}
            result[ean]['quantity'] += prod.production_autoconsommee or 0.0
        return result, len(productions)

    def _count_existing_invoices(self, refs):
        """Compte les factures brouillon/validées dont la référence contient la période."""
        self.ensure_one()
        if not refs:
            return 0
        return self.env['account.move'].search_count([
            ('move_type', 'in', ['out_invoice', 'in_invoice']),
            ('state', 'in', ['draft', 'posted']),
            ('ref', 'in', refs),
        ])

    @api.depends('community_id', 'partner_ids', 'data_type', 'date_from', 'date_to')
    def _compute_stats(self):
        for record in self:
            record.stat_records = 0
            record.stat_partners = 0
            record.stat_kwh = 0.0
            record.stat_amount = 0.0
            record.stat_existing = 0
            if not (record.community_id and record.date_from and record.date_to):
                continue
            try:
                partners = set()
                total_kwh = 0.0
                total_amount = 0.0
                refs = []
                product_price = record.community_id.product_price or 0.0
                producer_price = record.community_id.producer_price or 0.0

                if record.data_type in ('both', 'consumption'):
                    grouped, nb = record._group_consumption()
                    record.stat_records += nb
                    for ean, data in grouped.items():
                        if data['quantity'] > 0 and product_price > 0:
                            partners.add(data['partner_id'])
                            total_kwh += data['quantity']
                            # Prix total incluant CV + accises (comme sur la facture réelle)
                            total_amount += data['quantity'] * (
                                product_price + CV_RESTITUTION_PRICE + ACCISES_2026_PRICE)
                            refs.append(record._build_ref(ean, 'out_invoice'))
                if record.data_type in ('both', 'production'):
                    grouped, nb = record._group_production()
                    record.stat_records += nb
                    for ean, data in grouped.items():
                        if data['quantity'] > 0 and producer_price > 0:
                            partners.add(data['partner_id'])
                            total_kwh += data['quantity']
                            total_amount += data['quantity'] * producer_price
                            refs.append(record._build_ref(ean, 'in_invoice'))

                record.stat_partners = len(partners)
                record.stat_kwh = total_kwh
                record.stat_amount = total_amount
                record.stat_existing = record._count_existing_invoices(refs)
            except Exception as e:
                _logger.warning(f"[GEN FACTURES] Erreur prévisualisation: {e}")

    # ---- Facturation (identique aux wizards d'import) ----

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

    def _get_invoice_journal(self, data_type):
        journal_type = 'purchase' if data_type == 'production' else 'sale'
        return self.env['account.journal'].search([('type', '=', journal_type)], limit=1)

    def _check_journals(self):
        """Valide la présence des journaux AVANT toute création de facture,
        afin d'éviter une génération partielle."""
        self.ensure_one()
        missing = []
        if self.data_type in ('both', 'consumption'):
            if not self._get_invoice_journal('consumption'):
                missing.append(_("journal de vente"))
        if self.data_type in ('both', 'production'):
            if not self._get_invoice_journal('production'):
                missing.append(_("journal d'achat"))
        if missing:
            raise UserError(_(
                "Impossible de générer les factures : aucun %s trouvé.\n"
                "Veuillez configurer le(s) journal(aux) comptable(s) avant de relancer."
            ) % _(" ni ").join(missing))

    def _get_payment_term(self):
        if self.payment_term_id:
            return self.payment_term_id
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

    def _build_ref(self, ean, move_type):
        self.ensure_one()
        return (f'Opération de partage {self.community_id.name} - '
                f'Période {self._period_ref()} - {ean}')

    def _invoice_exists(self, partner_id, move_type, ean):
        ref_prefix = self._build_ref(ean, move_type)
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
                'ref': self._build_ref(ean, move_type),
                'invoice_line_ids': line_vals_list,
                'invoice_payment_term_id': payment_term.id,
                'state': 'draft'}
            return self.env['account.move'].create(invoice_vals)
        except Exception as e:
            _logger.warning(
                f"[GEN FACTURES] Erreur création facture pour {ean}: {e}")
            return False

    def _generate_consumption_invoices(self, tax, payment_term):
        journal = self._get_invoice_journal('consumption')
        grouped, _nb = self._group_consumption()
        product_price = self.community_id.product_price or 0.0
        created, skipped, failed, unpriced = [], 0, 0, 0
        for ean, data in grouped.items():
            if data['quantity'] <= 0:
                continue
            if product_price <= 0:
                unpriced += 1
                continue
            partner = self.env['res.partner'].browse(data['partner_id'])
            if self._invoice_exists(partner.id, 'out_invoice', ean):
                skipped += 1
                continue
            quantity = data['quantity']
            unit_price = product_price
            total = quantity * unit_price
            description = (
                f"Consommation énergie partagée - Période {self._period_ref()}\n"
                f"Prélèvement couvert : {quantity:.3f} kWh\n"
                f"Prix de vente : {unit_price:.3f} €/kWh\n"
                f"Sous-total : {total:.2f} €")
            invoice_lines = [{
                'name': description, 'quantity': quantity,
                'price_unit': unit_price, 'tax_ids': [(6, 0, [tax.id])]}]

            # === NOUVELLES LIGNES : CV + ACCISES (facture CLIENT uniquement) ===
            cv_total = quantity * CV_RESTITUTION_PRICE
            invoice_lines.append({
                'name': (
                    f"Coût de la restitution des CV - Période {self._period_ref()}\n"
                    f"Prélèvement couvert : {quantity:.3f} kWh\n"
                    f"Tarif : {CV_RESTITUTION_PRICE:.3f} €/kWh HTVA\n"
                    f"Sous-total : {cv_total:.2f} €"),
                'quantity': quantity,
                'price_unit': CV_RESTITUTION_PRICE,
                'tax_ids': [(6, 0, [tax.id])],
            })
            accises_total = quantity * ACCISES_2026_PRICE
            invoice_lines.append({
                'name': (
                    f"Droit d'accises spécial 2026 (tarif unique) - Période {self._period_ref()}\n"
                    f"Prélèvement couvert : {quantity:.3f} kWh\n"
                    f"Tarif : {ACCISES_2026_PRICE:.3f} €/kWh HTVA\n"
                    f"Sous-total : {accises_total:.2f} €"),
                'quantity': quantity,
                'price_unit': ACCISES_2026_PRICE,
                'tax_ids': [(6, 0, [tax.id])],
            })

            invoice = self._create_draft_invoice(
                partner, invoice_lines, ean, journal, payment_term, 'out_invoice')
            if invoice:
                created.append(invoice)
            else:
                failed += 1
        return created, skipped, failed, unpriced

    def _generate_production_invoices(self, tax, payment_term):
        journal = self._get_invoice_journal('production')
        grouped, _nb = self._group_production()
        producer_price = self.community_id.producer_price or 0.0
        created, skipped, failed, unpriced = [], 0, 0, 0
        for ean, data in grouped.items():
            if data['quantity'] <= 0:
                continue
            if producer_price <= 0:
                unpriced += 1
                continue
            partner = self.env['res.partner'].browse(data['partner_id'])
            if self._invoice_exists(partner.id, 'in_invoice', ean):
                skipped += 1
                continue
            quantity = data['quantity']
            unit_price = producer_price
            total = quantity * unit_price
            description = (
                f"Rémunération énergie partagée - Période {self._period_ref()}\n"
                f"Production autoconsommée : {quantity:.3f} kWh\n"
                f"Prix d'achat : {unit_price:.3f} €/kWh\n"
                f"Sous-total : {total:.2f} €")
            invoice_lines = [{
                'name': description, 'quantity': quantity,
                'price_unit': unit_price, 'tax_ids': [(6, 0, [tax.id])]}]
            invoice = self._create_draft_invoice(
                partner, invoice_lines, ean, journal, payment_term, 'in_invoice')
            if invoice:
                created.append(invoice)
            else:
                failed += 1
        return created, skipped, failed, unpriced

    def action_generate(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_("Veuillez sélectionner une période."))
        if self.date_from > self.date_to:
            raise UserError(_("La date de début doit être antérieure à la date de fin."))
        if self.stat_records == 0:
            raise UserError(_("Aucune donnée de consommation/production sur cette "
                              "période pour cette opération de partage."))

        # Validation des journaux AVANT toute création (pas de génération partielle)
        self._check_journals()

        tax = self._get_tax_6_percent()
        payment_term = self._get_payment_term()

        created = []
        skipped = failed = unpriced = 0
        messages = []
        if self.data_type in ('both', 'consumption'):
            c_created, c_skipped, c_failed, c_unpriced = self._generate_consumption_invoices(
                tax, payment_term)
            created += c_created
            skipped += c_skipped
            failed += c_failed
            unpriced += c_unpriced
            messages.append(
                f"• Consommation : {len(c_created)} facture(s) client créée(s), "
                f"{c_skipped} déjà existante(s)")
            if c_unpriced:
                messages.append(
                    f"  ⚠️ {c_unpriced} participant(s) non facturé(s) : prix de vente "
                    f"(product_price) à 0 sur l'opération")
            if c_failed:
                messages.append(
                    f"  ❌ {c_failed} facture(s) en échec de création (voir le log serveur)")
        if self.data_type in ('both', 'production'):
            p_created, p_skipped, p_failed, p_unpriced = self._generate_production_invoices(
                tax, payment_term)
            created += p_created
            skipped += p_skipped
            failed += p_failed
            unpriced += p_unpriced
            messages.append(
                f"• Production : {len(p_created)} facture(s) fournisseur créée(s), "
                f"{p_skipped} déjà existante(s)")
            if p_unpriced:
                messages.append(
                    f"  ⚠️ {p_unpriced} participant(s) non facturé(s) : prix d'achat "
                    f"producteur (producer_price) à 0 sur l'opération")
            if p_failed:
                messages.append(
                    f"  ❌ {p_failed} facture(s) en échec de création (voir le log serveur)")

        self.result_summary = (
            f"Facturation de la période du {self.date_from} au {self.date_to}\n"
            f"Opération de partage : {self.community_id.name}\n\n"
            + "\n".join(messages)
            + f"\n\nTotal : {len(created)} facture(s) brouillon créée(s), "
              f"{skipped} ignorée(s) (déjà existante(s)).")

        if not created:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'energy.invoice.generator.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'name': _('Génération terminée'),
            }

        invoice_ids = [inv.id for inv in created]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Factures générées'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoice_ids)],
            'target': 'current',
        }