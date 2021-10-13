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

    def update_planning_engine_list(self):
        self.env['mrp.planning.engine.list.item'].search([]).unlink()
        #self.env['mrp.planning.engine.list'].search([]).unlink()
        self.action_planning_engine_list()
        return {
            'type': 'ir.actions.act_window',
            'name': _('MRP Planning Engine List'),
            'res_model': 'mrp.planning.engine.list',
            'target': 'new',
            'views': [(self.env.ref('mrp_planning_engine.view_mrp_planning_engine_list_form').id, "form")],
            'res_id': self.id,
        }

    def action_planning_engine_list(self):
        for list in self:
            stock_mrp = list.mrp_parameter_id._compute_qty_available()
            id_created_begin = self.env['mrp.planning.engine.list.item'].create({
                'wizard_id' : list.id,
                'mrp_parameter_id' : list.mrp_parameter_id.id,
                'product_id' : list.mrp_parameter_id.product_id.id,
                'mrp_qty' : stock_mrp,
                'mrp_date' : datetime.strptime('1900-01-01','%Y-%m-%d').date(),
                "fixed": False,
                "mrp_type": "b",
                "fixed": False,
            })
            id_created_end = self.env['mrp.planning.engine.list.item'].create({
                'wizard_id' : list.id,
                'mrp_parameter_id' : list.mrp_parameter_id.id,
                'product_id' : list.mrp_parameter_id.product_id.id,
                'mrp_qty' : 0.0,
                'mrp_date' : datetime.strptime('2999-12-31','%Y-%m-%d').date(),
                "mrp_type": "e",
                "fixed": False,
            })
            if list.mrp_parameter_id.mrp_frozen_days > 0 and not list.mrp_parameter_id.demand_indicator == "20":
                frozen_date = list.mrp_parameter_id.warehouse_id.calendar_id.plan_days(list.mrp_parameter_id.mrp_frozen_days + 1, fields.Datetime.now(), True)
                id_created_frozen_period = self.env['mrp.planning.engine.list.item'].create({
                    'wizard_id' : list.id,
                    'mrp_parameter_id' : list.mrp_parameter_id.id,
                    'product_id' : list.mrp_parameter_id.product_id.id,
                    'mrp_qty' : 0.0,
                    'mrp_date' : frozen_date.date(),
                    "mrp_type": "f",
                    "fixed": False,
                })
        # Demand
        demand_items = self.env["mrp.demand"].search([("mrp_parameter_id", "=", list.mrp_parameter_id.id), ("state", "=", "done")])
        for demand_item in demand_items:
            element_item = self.env['mrp.planning.engine.list.item'].create({
                'wizard_id' : list.id,
                "mrp_parameter_id": list.mrp_parameter_id.id,
                "product_id": demand_item.product_id.id,
                "mrp_qty": - demand_item.mrp_qty,
                "mrp_date": fields.Datetime.from_string(demand_item.date_planned).date(),
                "mrp_type": "d",
                "mrp_origin": "di",
                "mrp_order_number": "Demand Item",
                "parent_product_id": False,
                "name": "Demand Item",
                "fixed": False,
            })
        # RfQs
        location_ids = list.mrp_parameter_id.location_ids
        picking_type_ids = self.env["stock.picking.type"].search([("default_location_dest_id", "in", location_ids.ids), ("code", "=", "incoming")]).ids
        pos = self.env["purchase.order"].search([("picking_type_id", "in", picking_type_ids),("state", "in", ["draft", "sent", "to approve"])])
        po_lines = self.env["purchase.order.line"].search([("order_id", "in", pos.ids), ("product_qty", ">", 0.0),("product_id", "=", list.mrp_parameter_id.product_id.id)])
        for po_line in po_lines:
            element_item = self.env['mrp.planning.engine.list.item'].create({
                'wizard_id' : list.id,
                "mrp_parameter_id": list.mrp_parameter_id.id,
                "product_id": po_line.product_id.id,
                "mrp_qty": po_line.product_uom_qty,
                "mrp_date": fields.Datetime.from_string(po_line.date_planned).date(),
                "mrp_type": "s",
                "mrp_origin": "po",
                "mrp_order_number": po_line.order_id.name,
                "parent_product_id": False,
                "name": po_line.order_id.name,
                "fixed": False,
            })
        # Subcontracting RfQ Requirements
        other_po_lines = self.env["purchase.order.line"].search([("order_id", "in", pos.ids), ("product_qty", ">", 0.0),("product_id", "!=", list.mrp_parameter_id.product_id.id)])
        for other_po_line in other_po_lines:
            other_po_line_mrp_parameter = self.env["mrp.parameter"].search([("product_id", "=", other_po_line.product_id.id),("warehouse_id", "=", list.mrp_parameter_id.warehouse_id.id)], limit=1)
            if other_po_line_mrp_parameter and other_po_line_mrp_parameter.supply_method == 'subcontracting' and other_po_line_mrp_parameter.bom_id and other_po_line.order_id.partner_id in other_po_line_mrp_parameter.bom_id.subcontractor_ids:
                mrp_date = False
                order_date = other_po_line.order_id.date_order
                days_to_purchase = list.mrp_parameter_id.company_id.days_to_purchase
                mrp_date = order_date - timedelta(days=days_to_purchase)
                if list.mrp_parameter_id.warehouse_id.calendar_id and not days_to_purchase == 0:
                    calendar = list.mrp_parameter_id.warehouse_id.calendar_id
                    mrp_date = calendar.plan_days(-days_to_purchase - 1, order_date, True)
                for bomline in other_po_line_mrp_parameter.bom_id.bom_line_ids:
                    if bomline.product_id == list.mrp_parameter_id.product_id:
                        parent_product = other_po_line_mrp_parameter.product_id
                        factor = (parent_product.product_tmpl_id.uom_id._compute_quantity(other_po_line.product_uom_qty, bomline.bom_id.product_uom_id) / bomline.bom_id.product_qty)
                        line_quantity = factor * bomline.product_qty
                        element_item = self.env['mrp.planning.engine.list.item'].create({
                            'wizard_id' : list.id,
                            "mrp_parameter_id": list.mrp_parameter_id.id,
                            "product_id": bomline.product_id.id,
                            "mrp_qty": -line_quantity,
                            "mrp_date": fields.Datetime.from_string(mrp_date).date(),
                            "mrp_type": "d",
                            "mrp_origin": "po",
                            "mrp_order_number": other_po_line.order_id.name,
                            "parent_product_id": parent_product.id,
                            "name": "Demand PO Subcontracting Explosion: %s %s" % (parent_product.name, bomline.product_id.name),
                            "fixed": False,
                        })
        # stock moves
        in_domain = list.mrp_parameter_id._in_stock_moves_domain()
        in_moves = self.env["stock.move"].search(in_domain)
        out_domain = list.mrp_parameter_id._out_stock_moves_domain()
        out_moves = self.env["stock.move"].search(out_domain)
        if in_moves:
            for move in in_moves:
                in_move_data = list._prepare_mrp_element_data_from_stock_move(move, direction="in")
                self.env['mrp.planning.engine.list.item'].create(in_move_data)
        if out_moves:
            for move in out_moves:
                out_move_data = list._prepare_mrp_element_data_from_stock_move(move, direction="out")
                self.env['mrp.planning.engine.list.item'].create(out_move_data)
        # Planned Orders
        for planned_order in list.mrp_parameter_id.planned_order_ids:
            element_item = self.env['mrp.planning.engine.list.item'].create({
                'wizard_id' : list.id,
                "mrp_parameter_id": list.mrp_parameter_id.id,
                "product_id": planned_order.product_id.id,
                "mrp_qty": planned_order.mrp_qty,
                "mrp_date": planned_order.due_date.date(),
                "mrp_type": "s",
                "mrp_origin": "op",
                "mrp_order_number": planned_order.name,
                "parent_product_id": False,
                "name": planned_order.name,
                "fixed": planned_order.fixed,
            })
        # Requirements
        for mrp_element in list.mrp_parameter_id.mrp_element_ids.filtered(lambda r: r.mrp_origin == "mrp"):
            if not mrp_element.mrp_qty == 0.0:
                element_item = self.env['mrp.planning.engine.list.item'].create({
                    'wizard_id' : list.id,
                    "mrp_parameter_id": list.mrp_parameter_id.id,
                    "product_id": mrp_element.product_id.id,
                    "mrp_qty": mrp_element.mrp_qty,
                    "mrp_date": mrp_element.mrp_date,
                    "mrp_type": mrp_element.mrp_type,
                    "mrp_origin": "mrp",
                    "mrp_order_number": mrp_element.mrp_order_number,
                    "parent_product_id": mrp_element.parent_product_id.id,
                    "name": mrp_element.name,
                    "fixed": mrp_element.fixed,
                })
        list._get_cum_qty()
        return {
            'type': 'ir.actions.act_window',
            'name': _('MRP Planning Engine List'),
            'res_model': 'mrp.planning.engine.list',
            'target': 'new',
            'views': [(self.env.ref('mrp_planning_engine.view_mrp_planning_engine_list_form').id, "form")],
            'res_id': self.id,
        }

    def _prepare_mrp_element_data_from_stock_move(self, move, direction):
        if direction == "out":
            mrp_type = "d"
            product_qty = -move.product_qty
        elif direction == "in":
            mrp_type = "s"
            product_qty = move.product_qty
        mrp_date = move.date_deadline or move.date
        if move.purchase_line_id:
            order_number = move.purchase_line_id.order_id.name
            origin = "po"
            parent_product_id = False
            name = move.name
        elif move.production_id:
            if move.production_id.location_dest_id.id == move.production_id.company_id.subcontracting_location_id.id:
                origin_move = self.env["stock.move"].search([('reference', '=', move.group_id.name)], limit=1)
                order_number = origin_move.origin
                parent_product_id = False
                origin = "po"
                name = move.production_id.name
            else:
                order_number = move.production_id.name
                origin = "mo"
                parent_product_id = False
                name = move.production_id.name
        elif move.raw_material_production_id:
            if move.raw_material_production_id.location_src_id.id == move.raw_material_production_id.company_id.subcontracting_location_id.id:
                origin_move = self.env["stock.move"].search([('reference', '=', move.group_id.name)], limit=1)
                order_number = origin_move.origin
                parent_product_id = origin_move.product_id.id
                origin = "po"
                name = move.raw_material_production_id.name
                if origin_move.purchase_line_id:
                    date_order = origin_move.purchase_line_id.order_id.date_order
                    days_to_purchase = origin_move.company_id.days_to_purchase
                    mrp_date = date_order - timedelta(days=days_to_purchase)
                    if origin_move.warehouse_id.calendar_id and not days_to_purchase == 0:
                        calendar = origin_move.warehouse_id.calendar_id
                        mrp_date = calendar.plan_days(-days_to_purchase - 1, date_order, True)
            else:
                order_number = move.raw_material_production_id.name
                parent_product_id = move.raw_material_production_id.product_id.id
                origin = "mo"
                name = move.raw_material_production_id.name
        elif move.sale_line_id:
            order_number = move.sale_line_id.order_id.name
            parent_product_id = False
            origin = "so"
            name = move.picking_id.name or move.name
            if self.mrp_parameter_id.demand_indicator == "10":
                product_qty = 0.0
        else:
            order_number = move.picking_id.name or move.name
            parent_product_id = False
            origin = "mv"
            name = move.picking_id.name or move.name
        return {
            "wizard_id" : self.id,
            "mrp_parameter_id": self.mrp_parameter_id.id,
            "product_id": move.product_id.id,
            "mrp_qty": product_qty,
            "mrp_date": mrp_date.date(),
            "mrp_type": mrp_type,
            "mrp_origin": origin,
            "mrp_order_number": order_number,
            "parent_product_id": parent_product_id,
            "name": name,
            "fixed": False,
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
    _order = "mrp_date, mrp_type desc, id"


    wizard_id = fields.Many2one('mrp.planning.engine.list', readonly=True)
    name = fields.Char("Name", readonly=True)
    mrp_parameter_id = fields.Many2one("mrp.parameter", "MRP Planning Parameters",  readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    product_uom = fields.Many2one("uom.uom", readonly=True, related="product_id.product_tmpl_id.uom_id")
    mrp_date = fields.Date("MRP Date", readonly=True)
    mrp_order_number = fields.Char("Order Number", readonly=True)
    mrp_origin = fields.Selection(MRP_ORIGIN_SELECTION, string="Origin", readonly=True)
    mrp_qty = fields.Float("MRP Quantity", readonly=True)
    mrp_type = fields.Selection(MRP_TYPE_SELECTION, string="Type", readonly=True)
    parent_product_id = fields.Many2one("product.product", string="Parent Product", readonly=True)
    fixed = fields.Boolean("Fixed", readonly=True, default=True)
    mrp_qty_cum = fields.Float('Projected Stock Qty', readonly=True)
