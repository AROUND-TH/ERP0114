# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpDemandCreateWizard(models.TransientModel):
    _name = "mrp.demand.create.wizard"
    _description = "MRP Demand Massive Creation Wizard"

    qty_factor = fields.Float('Quantity Factor', required=True, default=1.0)
    old_mrp_parameter_id = fields.Many2one("mrp.parameter", "OLD MRP Planning Parameters", required=True)
    new_mrp_parameter_id = fields.Many2one("mrp.parameter", "NEW MRP Planning Parameters", required=True)
    demand_item_ids = fields.Many2many('mrp.demand', string='MRP Demand Items')
    demand_count = fields.Integer('Selected Demand Items #', compute='do_count_demand_items', store=True)


    def do_massive_create(self):
        self.ensure_one()
        if self.demand_count == 0:
            raise UserError(_('No Demand Item has been selected'))
        for item in self.demand_item_ids:
            for record in item:
                id_created= self.env['mrp.demand'].create({
                    'mrp_parameter_id': self.new_mrp_parameter_id.id,
                    'planned_qty': record.planned_qty * self.qty_factor,
                    'date_planned': record.date_planned,
                })
        return True

    @api.depends('demand_item_ids')
    def do_count_demand_items(self):
        self.demand_count = len(self.demand_item_ids)
        return True

    def _reopen_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'new'}

    def do_populate_demand_item(self):
        self.ensure_one()
        selected_demand_items = self.env['mrp.demand'].search([('mrp_parameter_id', '=', self.old_mrp_parameter_id.id), ('state', '!=', 'cancel')])
        self.demand_item_ids = selected_demand_items
        return self._reopen_form()

