from odoo import models, fields, api


class EnergyCommunityProduction(models.Model):
    _name = 'energy.community.production'
    _description = 'Production partage énergie'
    _order = 'timestamp desc'

    timestamp = fields.Datetime(string='Période', required=True, index=True)
    ean = fields.Char(string='EAN', required=True, index=True)
    production_brute = fields.Float(string='Production brute (kWh)')
    coefficient = fields.Float(string='Coefficient (%)')
    production_allouee = fields.Float(string='Production allouée au partage (kWh)')
    production_autoconsommee = fields.Float(string='Production autoconsommée (kWh)')
    production_non_allouee = fields.Float(string='Production non allouée (kWh)')
    allo_production = fields.Float(string='Allo Production (kWh)')

    community_id = fields.Many2one('energy.community', string='Opération de partage')
    partner_id = fields.Many2one('res.partner', string='Participant')
    month = fields.Char(string='Mois', compute='_compute_month', store=True)

    @api.depends('timestamp')
    def _compute_month(self):
        for record in self:
            if record.timestamp:
                record.month = record.timestamp.strftime('%Y-%m')


class EnergyCommunityConsumption(models.Model):
    _name = 'energy.community.consumption'
    _description = 'Consommation partage énergie'
    _order = 'timestamp desc, iteration'

    timestamp = fields.Datetime(string='Période', required=True, index=True)
    ean = fields.Char(string='EAN', required=True, index=True)
    iteration = fields.Integer(string='Itération')
    coefficient = fields.Float(string='Coefficient (%)')
    prelevement_brut = fields.Float(string='Prélèvement brut (kWh)')
    production_mise_disposition = fields.Float(string='Production mise à disposition (kWh)')
    prelevement_couvert = fields.Float(string='Prélèvement couvert (kWh)')
    surplus_production = fields.Float(string='Surplus de production (kWh)')
    allo_consommation = fields.Float(string='Allo Consommation (kWh)')

    community_id = fields.Many2one('energy.community', string='Opération de partage')
    partner_id = fields.Many2one('res.partner', string='Participant')
    month = fields.Char(string='Mois', compute='_compute_month', store=True)

    @api.depends('timestamp')
    def _compute_month(self):
        for record in self:
            if record.timestamp:
                record.month = record.timestamp.strftime('%Y-%m')


class EnergyCommunity(models.Model):
    _name = 'energy.community'
    _description = 'Opération de partage'

    name = fields.Char(string='Nom', required=True)
    active = fields.Boolean(string='Actif', default=True)
    partner_ids = fields.Many2many('res.partner', string='Participants')
    product_price = fields.Float(string='Prix de vente énergie (€/kWh)')
    producer_price = fields.Float(string='Prix d\'achat producteur (€/kWh)')
    month = fields.Char(string='Mois en cours')

    def write(self, vals):
        """
        Intercepte la modification de partner_ids pour synchroniser
        les enregistrements production/consommation associés.
        """
        old_partner_map = {}
        if 'partner_ids' in vals:
            for community in self:
                for partner in community.partner_ids:
                    if partner.ref:
                        old_partner_map[partner.id] = partner.ref

        result = super().write(vals)

        if 'partner_ids' in vals:
            for community in self:
                new_partner_ids = set(community.partner_ids.ids)
                old_partner_ids = set(old_partner_map.keys())

                removed_partner_ids = old_partner_ids - new_partner_ids
                added_partner_ids = new_partner_ids - old_partner_ids

                if removed_partner_ids or added_partner_ids:
                    self._sync_data_for_partners(
                        community,
                        removed_ids=list(removed_partner_ids),
                        added_ids=list(added_partner_ids),
                    )

        return result

    def _sync_data_for_partners(self, community, removed_ids, added_ids):
        """
        Synchronise les enregistrements production/consommation
        quand des partenaires sont retirés ou ajoutés à une communauté.
        """
        removed_partners = self.env['res.partner'].browse(removed_ids)
        removed_eans = [p.ref for p in removed_partners if p.ref]

        added_partners = self.env['res.partner'].browse(added_ids)
        added_eans = [p.ref for p in added_partners if p.ref]

        # 1. Partenaires RETIRÉS
        if removed_eans:
            consumptions = self.env['energy.community.consumption'].search([
                ('community_id', '=', community.id),
                ('ean', 'in', removed_eans),
            ])
            productions = self.env['energy.community.production'].search([
                ('community_id', '=', community.id),
                ('ean', 'in', removed_eans),
            ])

            for ean in removed_eans:
                other_communities = self.env['energy.community'].search([
                    ('id', '!=', community.id),
                    ('partner_ids.ref', '=', ean),
                ])
                if other_communities:
                    # Déplacé vers une autre communauté → réassigner
                    new_id = other_communities[0].id
                    consumptions.filtered(lambda c: c.ean == ean).write(
                        {'community_id': new_id})
                    productions.filtered(lambda p: p.ean == ean).write(
                        {'community_id': new_id})
                else:
                    # N'est plus nulle part → détacher
                    consumptions.filtered(lambda c: c.ean == ean).write(
                        {'community_id': False})
                    productions.filtered(lambda p: p.ean == ean).write(
                        {'community_id': False})

        # 2. Partenaires AJOUTÉS
        if added_eans:
            for ean in added_eans:
                # Si l'EAN est encore dans une autre communauté, on ne touche pas
                still_elsewhere = self.env['energy.community'].search([
                    ('id', '!=', community.id),
                    ('partner_ids.ref', '=', ean),
                ])
                if still_elsewhere:
                    continue

                # Récupérer les données orphelines et les réassigner
                self.env['energy.community.consumption'].search([
                    ('ean', '=', ean),
                    ('community_id', '!=', community.id),
                ]).write({'community_id': community.id})

                self.env['energy.community.production'].search([
                    ('ean', '=', ean),
                    ('community_id', '!=', community.id),
                ]).write({'community_id': community.id})


class EnergyCommunityParticipant(models.Model):
    _name = 'energy.community.participant'
    _description = 'Participant à une opération de partage'
    _rec_name = 'ean'

    community_id = fields.Many2one('energy.community', string='Opération de partage', required=True)
    partner_id = fields.Many2one('res.partner', string='Contact', required=True)
    ean = fields.Char(string='EAN', required=True, index=True)
    meter_id = fields.Char(string='Numéro de compteur')
    participant_type = fields.Selection([
        ('consumption', 'Prélèvement'),
        ('injection', 'Injection'),
    ], string='Type de participant', default='consumption')
    active = fields.Boolean(string='Actif', default=True)