# -*- coding: utf-8 -*-
# Copyright (c) OpenValue All Rights Reserved


from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime, date, timedelta
from math import ceil


class MRPParameter(models.Model):
    _name = "mrp.parameter"
    _description = "MRP Planning Parameters"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "sequence"

    LOT_QTY_METHOD = [
        ('E', 'lot for lot'),
        ('F', 'fixed order quantity'),
        ('S', 'supply coverage days'),
        ('R', 'replenishment maximum quantity'),
    ]

    MRP_TYPE = [
        ('M', 'MRP'),
        ('R', 'Reorder Point'),
    ]

    SUPPLY_METHOD_SELECTION = [
        ("buy", "Buy"),
        ("none", "Undefined"),
        ("manufacture", "Produce"),
        ("transfer", "Stock Transfer"),
        ("subcontracting", "Subcontracting"),
    ]

    REQUIREMENTS_METHOD = [
        ('N', 'no requirements'),
        ('C', 'confirmed requirements in LT'),
        ('A', 'all requirements in LT'),
    ]

    DEMAND_SELECTION = [
        ("00", "No Demand Management"),
        ("10", "MTS Anonymous"),
        ("20", "MTO"),
        ("30", "Planning production by lots"),
        ("40", "Planning with final assembly"),
        #("41", "MTS production lot planning"),
        ("50", "Planning without final assembly"),
    ]

    def _group_planner_domain(self):
        group = self.env.ref('mrp_planning_engine.group_planning_user', raise_if_not_found=False)
        return [('groups_id', 'in', group.ids)] if group else []


    name = fields.Char("Name")
    sequence = fields.Integer('Sequence', default=1)
    active = fields.Boolean(default=True)
    user_id = fields.Many2one('res.users', string='MRP Planner', domain=_group_planner_domain, required=True)
    warehouse_id = fields.Many2one('stock.warehouse', "Warehouse", required=True)
    company_id = fields.Many2one("res.company", "Company", related="warehouse_id.company_id", store=True, readonly=True)
    product_id = fields.Many2one("product.product",  string="Product", required=True, domain=[('type', '=', 'product')])
    product_uom = fields.Many2one("uom.uom", readonly=True, related="product_id.product_tmpl_id.uom_id")
    location_ids = fields.One2many('stock.location', string="Internal Locations", compute='_get_locations')
    trigger = fields.Selection([('auto', 'Auto'), ('manual', 'Manual')], string='Trigger', default='auto', required=True)
    supply_method = fields.Selection(SUPPLY_METHOD_SELECTION, string="Supply Method", compute="_get_bom_supply_method", store=True)

    mrp_minimum_stock = fields.Float("Safety Stock", default=0.0, digits='Product Unit of Measure')
    mrp_safety_time = fields.Integer("Safety Time")
    mrp_maximum_order_qty = fields.Float("Maximum Order Qty", default=0.0, digits='Product Unit of Measure')
    mrp_minimum_order_qty = fields.Float("Minimum Order Qty", default=0.0, digits='Product Unit of Measure')
    mrp_qty_multiple = fields.Float("Qty Multiple", default=1.0, digits='Product Unit of Measure')

    mrp_type = fields.Selection(MRP_TYPE, 'MRP Type', default="M", required=True)
    requirements_method = fields.Selection(REQUIREMENTS_METHOD, 'Requirements Method', default="N", required=True)
    lot_qty_method = fields.Selection(LOT_QTY_METHOD, 'Lot Quantity Method', default="E", required=True)
    mrp_fixed_qty = fields.Float('Fixed Quantity', default=0.0, digits='Product Unit of Measure')
    mrp_coverage_days = fields.Integer("Days of Coverage")
    mrp_threshold_stock = fields.Float("Reorder Point Threshold Stock", default=0.0, digits='Product Unit of Measure')
    mrp_maximum_stock = fields.Float("Reorder Point Maximum Stock", default=0.0, digits='Product Unit of Measure')
    days_uom = fields.Many2one('uom.uom', 'Days', compute="_get_uom_days")

    bom_id = fields.Many2one("mrp.bom", "Bill of Materials", compute="_get_bom_supply_method")
    main_supplier_id = fields.Many2one("res.partner", "Main Supplier", compute="_get_main_supplier")
    main_supplierinfo_id = fields.Many2one("product.supplierinfo", "Supplier Info", compute="_get_main_supplier")
    source_warehouse_id = fields.Many2one('stock.warehouse', "Source Warehouse", compute="_get_bom_supply_method")
    mrp_transfer_delay = fields.Integer("Transfer Delay", default=1.0)
    mrp_transfer_lt = fields.Integer("Transfer Lead Time", default=0.0)
    mrp_element_ids = fields.One2many("mrp.element", "mrp_parameter_id", readonly=True)
    demand_item_ids = fields.One2many("mrp.demand", "mrp_parameter_id", readonly=True)
    demand_items_count = fields.Integer('Demand Items Count', compute='_demand_items_count')
    planned_order_ids = fields.One2many("mrp.planned.order", "mrp_parameter_id", readonly=True)
    planned_orders_count = fields.Integer('Planned Orders Count', compute='_planned_orders_count')
    llc = fields.Integer(string="Low Level Code", default=0, index=True)

    demand_indicator = fields.Selection(DEMAND_SELECTION, 'Demand Management', default="00", required=True)
    mrp_demand_backward_day = fields.Integer("Demand Backward Reduction Days", default=10)
    mrp_frozen_days = fields.Integer("Frozen Period", default=0)


    _sql_constraints = [("product_mrp_area_uniq", "unique(product_id, warehouse_id)", "The product/Warehouse combination must be unique.",)]

    @api.constrains("active")
    def _check_archive(self):
        for record in self:
            if record.active == False and record.planned_order_ids:
                    raise UserError(_("Planned Orders exist: please delete them before"))

    def unlink(self):
        for record in self:
            if record.planned_order_ids:
                raise UserError(_("Planned Orders exist, please delete them."))
            if record.demand_item_ids:
                raise UserError(_("Demand Items exist, please delete them."))
            polines = self.env["purchase.order.line"].search([
                ("state", "in", ("draft", "sent", "to approve")),
                ("product_id", "=", record.product_id.id),
                ("order_id.picking_type_id.warehouse_id", "=", record.warehouse_id.id),
                ])
            if polines:
                raise UserError(_("RfQ lines exist, please either convert or delete them."))
            mrp_production_ids = self.env["mrp.production"].search([
                    ("state", "in", ("draft", "confirmed", "progress", "to_close")),
                    ("product_id", "=", record.product_id.id),
                    ("picking_type_id.warehouse_id", "=", record.warehouse_id.id),
                ])
            if mrp_production_ids:
                raise UserError(_("MOs/Subcontracting POs exist, please either complete or delete them."))
        return super().unlink()

    def _planned_orders_count(self):
        order = self.env['mrp.planned.order']
        for record in self:
            self.planned_orders_count = order.search_count([('mrp_parameter_id', '=', record.id)])
        return True

    def action_view_planned_order(self):
        context = {'search_default_mrp_parameter_id': [self.id],'default_mrp_parameter_id': self.id,}
        return {
            'domain': "[('mrp_parameter_id','in',[" + ','.join(map(str, self.ids)) + "])]",
            'context': context,
            'name': _('Planned Orders'),
            'views': [(self.env.ref('mrp_planning_engine.mrp_planned_order_view_tree').id, "tree"), (self.env.ref('mrp_planning_engine.mrp_planned_order_view_form').id, "form")],
            'res_model': 'mrp.planned.order',
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def _demand_items_count(self):
        demand = self.env['mrp.demand']
        for record in self:
            self.demand_items_count = demand.search_count([('mrp_parameter_id', '=', record.id)])
        return True

    def action_view_demand_item(self):
        context = {'search_default_mrp_parameter_id': [self.id],'default_mrp_parameter_id': self.id,}
        return {
            'domain': "[('mrp_parameter_id','in',[" + ','.join(map(str, self.ids)) + "])]",
            'context': context,
            'name': _('Demand Items'),
            'views': [
                (self.env.ref('mrp_planning_engine.view_mrp_demand_tree').id, "tree"),
                (self.env.ref('mrp_planning_engine.view_mrp_demand_pivot').id, "pivot"),
                (self.env.ref('mrp_planning_engine.view_mrp_demand_graph').id, "graph"),
                ],
            'res_model': 'mrp.demand',
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def action_view_planning_engine_list(self):
        context = {'default_mrp_parameter_id': self.id,}
        return {
            'context': context,
            'name': _('MRP Planning Engine List'),
            'views': [(self.env.ref('mrp_planning_engine.view_mrp_planning_engine_list_wizard').id, "form")],
            'res_model': 'mrp.planning.engine.list',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.constrains('mrp_threshold_stock', 'mrp_type')
    def _check_mrp_threshold_stock(self):
        for parameter in self:
            if parameter.mrp_threshold_stock <= 0.0 and parameter.mrp_type == 'R':
                raise UserError(_('Reorder Point Threshold Quantity has to be positive'))
        return True

    #@api.constrains('demand_indicator', 'trigger')
    #def _check_production_lots(self):
    #    for parameter in self:
    #        if parameter.demand_indicator == "41" and parameter.trigger == "auto":
    #            raise UserError(_('Please set Trigger indicator as Manual with Demand Management as Producton Lot Planning'))
    #    return True

    @api.constrains('lot_qty_method', 'mrp_type')
    def _check_mrp_type_lot_qty_method(self):
        for parameter in self:
            if parameter.mrp_type == 'M' and parameter.lot_qty_method == 'R':
                raise UserError(_('lot quantity method not allowed with mrp type'))
            if parameter.mrp_type == 'R' and parameter.lot_qty_method == 'S':
                raise UserError(_('lot quantity method not allowed with mrp type'))
        return True

    def _compute_qty_available(self):
        qty_available = 0.0
        for record in self:
            stock_quant_ids = self.env['stock.quant'].search([('product_id', '=', record.product_id.id),('location_id', 'in', record.location_ids.ids)])
            qty_available = sum(stock_quant_ids.mapped('quantity'))
        return qty_available

    def _get_uom_days(self):
        uom = self.env.ref('uom.product_uom_day', raise_if_not_found=False)
        for record in self:
            if uom:
                record.days_uom = uom.id
        return True

    @api.depends('warehouse_id')
    def _get_locations(self):
        #domain = [('usage', 'in', ('internal', 'transit'))]
        domain = [('usage', '=', 'internal')]
        for parameter in self:
            domain += [('id', 'child_of', parameter.warehouse_id.view_location_id.id)]
            domain += ['|', ('company_id', '=', False), ('company_id', '=', parameter.company_id.id)]
            parameter.location_ids = self.env['stock.location'].search(domain)
            parameter.location_ids |= parameter.company_id.subcontracting_location_id
            #parameter.location_ids |= parameter.company_id.internal_transit_location_id
        return True

    @api.constrains("mrp_minimum_order_qty",
        "mrp_maximum_order_qty",
        "mrp_qty_multiple",
        "mrp_minimum_stock",
        "mrp_safety_time",
        "mrp_demand_backward_day",
        )
    def _check_mrp_parameters(self):
        if self.mrp_minimum_order_qty < 0.0 or self.mrp_maximum_order_qty < 0.0 or self.mrp_qty_multiple < 0.0 or self.mrp_minimum_stock < 0.0 or self.mrp_safety_time < 0.0 or self.mrp_demand_backward_day < 0.0:
            raise UserError(_('planning parameters cannot be negative'))
        return True

    def name_get(self):
        result = []
        for record in self:
            rec_name = "%s-%s" %(record.product_id.name,record.warehouse_id.name)
            result.append((record.id,rec_name))
        return result

    @api.depends('warehouse_id', 'product_id', 'main_supplier_id')
    def _get_bom_supply_method(self):
        bom = False
        for record in self:
            record.bom_id = False
            record.source_warehouse_id = False
            location = record.warehouse_id.lot_stock_id
            values = {"warehouse_id": record.warehouse_id, "company_id": record.warehouse_id.company_id}
            rule = self.env["procurement.group"]._get_rule(record.product_id, location, values)
            picking_type = record.warehouse_id.manu_type_id
            if not rule:
                record.supply_method = "none"
            elif rule.action in ("pull", "push", "pull_push"):
                record.supply_method = "transfer"
                record.source_warehouse_id = rule.propagate_warehouse_id
            elif rule.action == "buy":
                record.supply_method = "buy"
                if record.main_supplier_id:
                    bom = self.env['mrp.bom']._bom_subcontract_find(
                        product=record.product_id,
                        picking_type=None,
                        company_id=record.company_id.id,
                        bom_type='subcontract',
                        subcontractor=record.main_supplier_id,
                    )
                    if bom:
                        record.supply_method = "subcontracting"
                        record.bom_id = bom.id
            elif rule.action == "manufacture":
                record.supply_method = "manufacture"
                if record.product_id and picking_type:
                    bom = self.env['mrp.bom']._bom_find(product=record.product_id, picking_type=picking_type, bom_type='normal')
                if bom:
                    record.bom_id = bom.id
        return True

    @api.depends("product_id")
    def _get_main_supplier(self):
        for record in self:
            record.main_supplierinfo_id = False
            record.main_supplier_id = False
            suppliers = record.product_id._prepare_sellers()
            if suppliers:
                record.main_supplierinfo_id = suppliers[0]
                record.main_supplier_id = suppliers[0].name
        return True

    @api.constrains('lot_qty_method','mrp_fixed_qty', 'mrp_coverage_days', 'mrp_maximum_stock')
    def _check_lot_method_parameters(self):
        if self.lot_qty_method == 'F' and not self.mrp_fixed_qty > 0.0:
            raise UserError(_('fixed lot quantity has to be positive'))
        if self.lot_qty_method == 'S' and not self.mrp_coverage_days > 0.0:
            raise UserError(_('supply coverage days parameter has to be positive'))
        if self.lot_qty_method == 'R' and not self.mrp_maximum_stock > 0.0:
            raise UserError(_('maximum stock has to be positive'))

    def _get_start_date(self, finish_date):
        start_date = False
        for parameter in self:
            if parameter.supply_method in ("buy", "subcontracting") and parameter.main_supplierinfo_id:
                supplier_delay = parameter.main_supplierinfo_id.delay
                days_to_purchase = parameter.company_id.days_to_purchase
                purchase_lead_time = supplier_delay + days_to_purchase
                start_date = finish_date - timedelta(days=purchase_lead_time)
                if parameter.warehouse_id.calendar_id and not days_to_purchase == 0:
                    calendar = parameter.warehouse_id.calendar_id
                    start_date = finish_date - timedelta(days=supplier_delay)
                    start_date = calendar.plan_days(-days_to_purchase - 1, start_date, True)
            elif parameter.supply_method == "manufacture":
                manufacture_delay = parameter.product_id.produce_delay
                security_delay = parameter.company_id.manufacturing_lead
                manufacture_lead_time = manufacture_delay + security_delay
                start_date = finish_date - timedelta(days=manufacture_lead_time)
                if parameter.warehouse_id.calendar_id:
                    calendar = parameter.warehouse_id.calendar_id
                    start_date = calendar.plan_days(-manufacture_delay - 1, finish_date, True)
                    if security_delay > 0.0:
                        start_date = calendar.plan_days(-security_delay - 1, start_date, True)
            elif parameter.supply_method == "transfer":
                transfer_delay = parameter.mrp_transfer_delay + parameter.mrp_transfer_lt
                start_date = finish_date - timedelta(days=transfer_delay)
                if parameter.warehouse_id.calendar_id:
                    calendar = parameter.warehouse_id.calendar_id
                    finish_date = calendar.plan_hours(0.0, finish_date, True)
                    start_date = calendar.plan_days(-transfer_delay - 1, finish_date, True)
            else:
                start_date = finish_date
        return start_date

    def _get_finish_date(self, start_date):
        finish_date = False
        for parameter in self:
            if parameter.supply_method in ("buy", "subcontracting") and parameter.main_supplierinfo_id:
                supplier_delay = parameter.main_supplierinfo_id.delay
                days_to_purchase = parameter.company_id.days_to_purchase
                purchase_lead_time = supplier_delay + days_to_purchase
                finish_date = start_date + timedelta(days=purchase_lead_time)
                if parameter.warehouse_id.calendar_id and not days_to_purchase == 0:
                    calendar = parameter.warehouse_id.calendar_id
                    start_date = calendar.plan_hours(0.0, start_date, True)
                    finish_date = calendar.plan_days(days_to_purchase + 1, start_date, True)
                    finish_date = finish_date + timedelta(days=supplier_delay)
            elif parameter.supply_method == 'manufacture':
                manufacture_delay = parameter.product_id.produce_delay
                security_delay = parameter.company_id.manufacturing_lead
                manufacture_lead_time = manufacture_delay + security_delay
                finish_date = start_date + timedelta(days=manufacture_lead_time)
                if parameter.warehouse_id.calendar_id:
                    calendar = parameter.warehouse_id.calendar_id
                    start_date = calendar.plan_hours(0.0, start_date, True)
                    finish_date = calendar.plan_days(manufacture_delay + 1, start_date, True)
                    if security_delay > 0.0:
                        finish_date = calendar.plan_days(security_delay + 1, finish_date, True)
            elif parameter.supply_method == "transfer":
                transfer_delay = parameter.mrp_transfer_delay + parameter.mrp_transfer_lt
                finish_date = start_date + timedelta(days=transfer_delay)
                if parameter.warehouse_id.calendar_id:
                    calendar = parameter.warehouse_id.calendar_id
                    start_date = calendar.plan_hours(0.0, start_date, True)
                    finish_date = calendar.plan_days(transfer_delay + 1, start_date, True)
            else:
                finish_date = start_date
        return finish_date

    def _in_stock_moves_domain(self):
        self.ensure_one()
        locations = self.location_ids
        return [
            ("product_id", "=", self.product_id.id),
            ("state", "not in", ["done", "cancel"]),
            ("product_qty", ">", 0.00),
            ("location_id", "not in", locations.ids),
            ("location_dest_id", "in", locations.ids),
        ]

    def _out_stock_moves_domain(self):
        self.ensure_one()
        locations = self.location_ids
        return [
            ("product_id", "=", self.product_id.id),
            ("state", "not in", ["done", "cancel"]),
            ("product_qty", ">", 0.00),
            ("location_id", "in", locations.ids),
            ("location_dest_id", "not in", locations.ids),
        ]

    def update_min_qty_from_main_supplier(self):
        for rec in self.filtered(lambda r: r.main_supplierinfo_id and r.supply_method == "buy"):
            rec.mrp_minimum_order_qty = rec.main_supplierinfo_id.min_qty

    def _to_be_exploded(self):
        self.ensure_one()
        if self.supply_method in ("manufacture", "subcontracting"):
            return True
        else:
            return False

    def _get_lot_qty(self, qty_to_order):
        self.ensure_one()
        lot_qty = 0.0
        for parameter in self:
            # maximum lot
            if parameter.lot_qty_method == 'R':
                if max(parameter.mrp_threshold_stock, parameter.mrp_maximum_stock) > qty_to_order:
                    lot_qty = max(parameter.mrp_threshold_stock, parameter.mrp_maximum_stock) - qty_to_order
            #fixed lot
            if parameter.lot_qty_method == 'F':
                number_lots = int(qty_to_order // parameter.mrp_fixed_qty) + 1
                lot_qty = parameter.mrp_fixed_qty * number_lots
            #lot for lot
            else:
                lot_qty = qty_to_order
            if (not self.mrp_maximum_order_qty and not self.mrp_minimum_order_qty and self.mrp_qty_multiple == 1.0):
                return lot_qty
            if lot_qty < parameter.mrp_minimum_order_qty:
                lot_qty = parameter.mrp_minimum_order_qty
            if parameter.mrp_qty_multiple:
                multiplier = ceil(lot_qty / parameter.mrp_qty_multiple)
                lot_qty = multiplier * parameter.mrp_qty_multiple
            if parameter.mrp_maximum_order_qty and lot_qty > parameter.mrp_maximum_order_qty:
                lot_qty = parameter.mrp_maximum_order_qty
            return lot_qty
