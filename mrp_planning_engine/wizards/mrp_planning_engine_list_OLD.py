# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from datetime import datetime, date, time, timedelta
from odoo.addons.mrp_planning_engine.models.mrp_element import MRP_ORIGIN_SELECTION
#from odoo.addons.mrp_planning_engine.models.mrp_element import MRP_TYPE_SELECTION


MRP_TYPE_SELECTION = [
    ("s", "Supply"),
    ("d", "Demand"),
    ("f", "Frozen Period"),
    ("b", "Begin"),
    ("e", "End"),
]

class MRPPlanningEngineList(models.TransientModel):
    _name = 'mrp.planning.engine.list'
    _description = 'MRP Planning Engine List'

    mrp_parameter_id = fields.Many2one("mrp.parameter", "MRP Planning Parameters", required=True)
    item_ids = fields.One2many('mrp.planning.engine.list.item', 'wizard_id')
    user_id = fields.Many2one(related='mrp_parameter_id.user_id')
    trigger = fields.Selection(related='mrp_parameter_id.trigger')
    supply_method = fields.Selection(related='mrp_parameter_id.supply_method')
    mrp_minimum_stock = fields.Float(related='mrp_parameter_id.mrp_minimum_stock')
    mrp_safety_time = fields.Integer(related='mrp_parameter_id.mrp_safety_time')
    product_uom = fields.Many2one(related='mrp_parameter_id.product_uom')
    days_uom = fields.Many2one(related='mrp_parameter_id.days_uom')
    mrp_type = fields.Selection(related='mrp_parameter_id.mrp_type')
    lot_qty_method = fields.Selection(related='mrp_parameter_id.lot_qty_method')
    demand_indicator = fields.Selection(related='mrp_parameter_id.demand_indicator')
    mrp_demand_backward_day = fields.Integer(related='mrp_parameter_id.mrp_demand_backward_day')


    def action_planning_engine_list(self):
        for list in self:
            stock_mrp = self.mrp_parameter_id._compute_qty_available()
            id_created_begin = self.env['mrp.planning.engine.list.item'].create({
                'wizard_id' : self.id,
                'mrp_parameter_id' : self.mrp_parameter_id.id,
                'product_id' : self.mrp_parameter_id.product_id.id,
                'mrp_qty' : stock_mrp,
                'mrp_date' : datetime.strptime('1900-01-01','%Y-%m-%d'),
                "fixed": False,
                "mrp_type": "b",
                "fixed": False,
            })
            id_created_end = self.env['mrp.planning.engine.list.item'].create({
                'wizard_id' : self.id,
                'mrp_parameter_id' : self.mrp_parameter_id.id,
                'product_id' : self.mrp_parameter_id.product_id.id,
                'mrp_qty' : 0.0,
                'mrp_date' : datetime.strptime('2999-12-31','%Y-%m-%d'),
                "mrp_type": "e",
                "fixed": False,
            })
            if self.mrp_parameter_id.mrp_frozen_days > 0 and not self.mrp_parameter_id.demand_indicator == "20":
                frozen_date = self.mrp_parameter_id.warehouse_id.calendar_id.plan_days(self.mrp_parameter_id.mrp_frozen_days + 1, fields.Datetime.now(), True)
                id_created_frozen_period = self.env['mrp.planning.engine.list.item'].create({
                    'wizard_id' : self.id,
                    'mrp_parameter_id' : self.mrp_parameter_id.id,
                    'product_id' : self.mrp_parameter_id.product_id.id,
                    'mrp_qty' : 0.0,
                    'mrp_date' : frozen_date,
                    "mrp_type": "f",
                    "fixed": False,
                })
        # MRP Elements
        mrp_elements = self.env["mrp.element"].search([("mrp_parameter_id", "=", self.mrp_parameter_id.id)])
        for mrp_element in mrp_elements:
            if mrp_element.mrp_qty != 0:
                element_item = self.env['mrp.planning.engine.list.item'].create({
                    'wizard_id' : self.id,
                    "mrp_parameter_id": self.mrp_parameter_id.id,
                    "product_id": mrp_element.product_id.id,
                    "mrp_qty": mrp_element.mrp_qty,
                    "mrp_date": mrp_element.mrp_date,
                    "mrp_type": mrp_element.mrp_type,
                    "mrp_origin": mrp_element.mrp_origin,
                    "mrp_order_number": mrp_element.mrp_order_number,
                    "parent_product_id": mrp_element.parent_product_id.id,
                    "name": mrp_element.name,
                    "fixed": mrp_element.fixed,
                })
        # Planned Orders
        planned_orders = self.env["mrp.planned.order"].search([("mrp_parameter_id", "=", self.mrp_parameter_id.id), ("fixed", "=", False)])
        for planned_order in planned_orders:
            if planned_order.mrp_qty > 0:
                element_item = self.env['mrp.planning.engine.list.item'].create({
                    'wizard_id' : self.id,
                    "mrp_parameter_id": self.mrp_parameter_id.id,
                    "product_id": planned_order.product_id.id,
                    "mrp_qty": planned_order.mrp_qty,
                    "mrp_date": planned_order.due_date,
                    "mrp_type": "s",
                    "mrp_origin": "op",
                    "mrp_order_number": planned_order.name,
                    "parent_product_id": False,
                    "name": planned_order.name,
                    "fixed": planned_order.fixed,
                })
        # Projected Qty
        list._get_cum_qty()
        return {
            'type': 'ir.actions.act_window',
            'name': _('MRP Planning Engine List'),
            'res_model': 'mrp.planning.engine.list',
            'target': 'new',
            'views': [(self.env.ref('mrp_planning_engine.view_mrp_planning_engine_list_form').id, "form")],
            'res_id': self.id,
        }

    def _get_cum_qty(self):
        for item in self.item_ids:
            item.mrp_qty_cum = 0.0
            items = self.env['mrp.planning.engine.list.item'].search([('wizard_id', '=', self.id),('mrp_date', '<=', item.mrp_date)])
            item.mrp_qty_cum = sum(items.mapped('mrp_qty'))
        return True


class MRPPlanningEngineListItem(models.TransientModel):
    _name = 'mrp.planning.engine.list.item'
    _description = 'MRP Planning Engine List Item'
    _order = "mrp_date, id"

    wizard_id = fields.Many2one('mrp.planning.engine.list', readonly=True)
    name = fields.Char("Name", readonly=True)
    mrp_parameter_id = fields.Many2one("mrp.parameter", "MRP Planning Parameters",  readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    product_uom = fields.Many2one("uom.uom", readonly=True, related="product_id.product_tmpl_id.uom_id")
    mrp_date = fields.Datetime("MRP Date", readonly=True)
    mrp_order_number = fields.Char("Order Number", readonly=True)
    mrp_origin = fields.Selection(MRP_ORIGIN_SELECTION, string="Origin", readonly=True)
    mrp_qty = fields.Float("MRP Quantity", readonly=True)
    mrp_type = fields.Selection(MRP_TYPE_SELECTION, string="Type", readonly=True)
    parent_product_id = fields.Many2one("product.product", string="Parent Product", readonly=True)
    fixed = fields.Boolean("Fixed", readonly=True, default=True)
    mrp_qty_cum = fields.Float('Projected Stock Qty', readonly=True)
