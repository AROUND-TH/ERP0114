# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MrpFloatingTimes(models.Model):
    _name = "mrp.floating.times"
    _description = "MRP Floating Times"


    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', required=True, domain="[('manufacture_to_resupply', '=', 'True')]")
    mrp_release_time = fields.Float("Release Time (Hours)", default=1.0)
    mrp_ftbp_time = fields.Float("Floating Time Before Production (Hours)", default=1.0)
    mrp_ftap_time = fields.Float("Floating Time After Production (Hours)", default=1.0)

    @api.constrains('warehouse_id')
    def _check_same_warehouse(self):
        for record in self:
            ft_ids = self.env['mrp.floating.times'].search([('warehouse_id', '=', record.warehouse_id.id)])
            if len(ft_ids) > 1:
                raise UserError(_('Another Floating Times record exists in the same warehouse: %s')% record.warehouse_id.name)
        return True

    def create_floating_times(self):
        warehouses = self.env['stock.warehouse'].with_context(active_test=False).search([('manufacture_to_resupply', '=', True)])
        for warehouse in warehouses:
            self.create({
                'warehouse_id': warehouse.id,
                'mrp_release_time': 1.0,
                'mrp_ftbp_time': 1.0,
                'mrp_ftap_time': 1.0,
            })
        return True


class MrpProduction(models.Model):
    _inherit = 'mrp.production'


    def action_confirm(self):
        res = super().action_confirm()
        for production in self:
            floating_times_id = self.env['mrp.floating.times'].search([('warehouse_id', '=', production.picking_type_id.warehouse_id.id)])
            if not floating_times_id:
                raise UserError(_('Floating Times record has not been created yet for the warehouse: %s')% production.picking_type_id.warehouse_id.name)
        return res