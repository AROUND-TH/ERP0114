# -*- coding: utf-8 -*-
# Copyright (c) OpenValue All Rights Reserved


from odoo import api, fields, models, _


MRP_ORIGIN_SELECTION = [
    ("so", "Sales Order"),
    ("di", "Demand Item"),
    ("mo", "Manufacturing Order"),
    ("po", "Purchase Order"),
    ("mv", "Move"),
    ("mrp", "Requirements"),
    ("op", "Planned Order"),
]

MRP_TYPE_SELECTION = [
    ("s", "Supply"),
    ("d", "Demand"),
    ("b", "Begin"),
    ("e", "End"),
]

STATE_SELECTION = [
    ("draft", "Draft"),
    ("waiting", "Waiting Another Move"),
    ("confirmed", "Waiting Availability"),
    ("partially_available", "Partially Available"),
    ("assigned", "Available"),
    ("sent", "Sent"),
    ("to approve", "To Approve"),
]


class MrpElement(models.Model):
    _name = "mrp.element"
    _description = "MRP Element"
    _order = "mrp_parameter_id, mrp_date, mrp_type desc, id"


    name = fields.Char("Name")
    mrp_parameter_id = fields.Many2one("mrp.parameter", "MRP Planning Parameters", index=True, required=True)
    warehouse_id = fields.Many2one('stock.warehouse', "Warehouse", related="mrp_parameter_id.warehouse_id", store=True, readonly=True)
    company_id = fields.Many2one("res.company", "Company", related="mrp_parameter_id.warehouse_id.company_id", readonly=True)
    product_id = fields.Many2one("product.product", related="mrp_parameter_id.product_id", store=True, readonly=True)
    mrp_date = fields.Date("MRP Date")
    mrp_order_number = fields.Char("Order Number")
    mrp_origin = fields.Selection(MRP_ORIGIN_SELECTION, string="Origin")
    mrp_qty = fields.Float("MRP Quantity")
    mrp_type = fields.Selection(MRP_TYPE_SELECTION, string="Type")
    parent_product_id = fields.Many2one("product.product", string="Parent Product")
    production_id = fields.Many2one("mrp.production", "Manufacturing Order")
    purchase_line_id = fields.Many2one("purchase.order.line", "Purchase Order Line")
    purchase_order_id = fields.Many2one("purchase.order", "Purchase Order")
    fixed = fields.Boolean("Fixed", readonly=True, default=True)
    state = fields.Selection(STATE_SELECTION, string="State")
    stock_move_id = fields.Many2one("stock.move", string="Stock Move")
    planned_order_up_ids = fields.Many2many("mrp.planned.order", string="Planned Orders UP")
