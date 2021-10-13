# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from datetime import datetime, date, timedelta
from odoo.tools import float_compare, float_is_zero, float_round, date_utils
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

logger = logging.getLogger(__name__)


class MRPPlanningEngineRun(models.TransientModel):
    _name = 'mrp.planning.engine.run'
    _description = 'MRP Planning Engine Run'

    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', required=True)


    def massive_planning_engine_run(self):
        planning_volume = self.env["mrp.planning.volume"].search([])
        counter = 0
        for record in planning_volume:
            counter += 1
            message = self.planning_engine_run(record.warehouse_id)
            if message and record.warehouse_id.partner_id.email:
                mail_obj = self.env['mail.mail']
                subject = " ".join(["MRP Planning Run for:" , record.warehouse_id.name, "sequence:", str(counter)])
                mail_data = {
                            'subject': subject,
                            'body_html': message,
                            'email_to': record.warehouse_id.partner_id.email,
                            }
                mail_id = mail_obj.create(mail_data)
                mail_id.send()
        return True

    def action_planning_engine_run(self):
        message = self.planning_engine_run(self.warehouse_id)
        t_mess_id = False
        if message:
            t_mess_id = self.env["mrp.planning.message"].create({'name': message}).id
        else:
            t_mess_id = self.env["mrp.planning.message"].create({'name': 'no planning result'}).id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Planning Run Results'),
            'res_model': "mrp.planning.message",
            'res_id': t_mess_id,
            'views': [(self.env.ref('mrp_planning_engine.view_mrp_planning_message_form').id, "form")],
            'target': 'new',
        }

    def planning_engine_run(self, warehouse_id):
        message = False
        self._mrp_cleanup(warehouse_id)
        mrp_lowest_llc = self._low_level_code_calculation(warehouse_id)
        self._mrp_initialisation(warehouse_id)
        rop_counter, rop_planned_order_counter = self._rop_calculation(warehouse_id)
        mrp_counter, mrp_planned_order_counter = self._mrp_calculation(mrp_lowest_llc, warehouse_id)
        counter = mrp_counter + rop_counter
        planned_order_counter = mrp_planned_order_counter + rop_planned_order_counter
        message = _('planned products: %r ; planned orders: %r' %(counter, planned_order_counter))
        return message

    @api.model
    def _mrp_cleanup(self, warehouse_id):
        logger.info("Start MRP Cleanup")
        domain_element = [("warehouse_id", "=", warehouse_id.id)]
        self.env["mrp.element"].search(domain_element).unlink()
        domain_order = [("warehouse_id", "=", warehouse_id.id), ("fixed", "=", False)]
        self.env["mrp.planned.order"].search(domain_order).unlink()
        logger.info("End MRP Cleanup")
        return True

    @api.model
    def _low_level_code_calculation(self, warehouse_id):
        logger.info("Start low level code calculation")
        counter = 0
        # reorder point
        llc = -1
        self.env["mrp.parameter"].search([("warehouse_id", "=", warehouse_id.id),("mrp_type", "=", 'R')]).write({"llc": llc})
        parameters = self.env["mrp.parameter"].search([("llc", "=", llc)])
        if parameters:
            counter = len(parameters)
        log_msg = "Low level code -1 finished - Nbr. products: %s" % counter
        logger.info(log_msg)
        # MRP
        llc = 0
        self.env["mrp.parameter"].search([("warehouse_id", "=", warehouse_id.id),("mrp_type", "=", 'M')]).write({"llc": llc})
        parameters = self.env["mrp.parameter"].search([("llc", "=", llc)])
        if parameters:
            counter = len(parameters)
        log_msg = "Low level code 0 finished - Nbr. products: %s" % counter
        logger.info(log_msg)
        while counter:
            llc += 1
            parameters = self.env["mrp.parameter"].search([("llc", "=", llc - 1)])
            product_ids = parameters.product_id.ids
            product_template_ids = parameters.product_id.product_tmpl_id.ids
            bom_lines = self.env["mrp.bom.line"].search([("product_id", "in", product_ids),("bom_id.product_tmpl_id", "in", product_template_ids)])
            products = bom_lines.mapped("product_id")
            self.env["mrp.parameter"].search([("product_id", "in", products.ids),("warehouse_id", "=", warehouse_id.id),("mrp_type", "=", 'M')]).write({"llc": llc})
            counter = self.env["mrp.parameter"].search_count([("llc", "=", llc)])
            log_msg = "Low level code {} finished - Nbr. products: {}".format(llc, counter)
            logger.info(log_msg)
        mrp_lowest_llc = llc
        logger.info("End low level code calculation")
        return mrp_lowest_llc

    @api.model
    def _mrp_initialisation(self, warehouse_id):
        logger.info("Start MRP initialisation")
        mrp_parameters = self.env["mrp.parameter"].search([("warehouse_id", "=", warehouse_id.id), ("trigger", "=", "auto")])
        for mrp_parameter in mrp_parameters:
            self._init_mrp_element(mrp_parameter)
        logger.info("End MRP initialisation")

    @api.model
    def _init_mrp_element(self, mrp_parameter):
        self._init_mrp_element_from_demand(mrp_parameter)
        self._init_mrp_element_from_stock_move(mrp_parameter)
        self._init_mrp_element_from_purchase_order(mrp_parameter)
        self._init_mrp_element_from_fixed_planned_order(mrp_parameter)

    @api.model
    def _init_mrp_element_from_demand(self, mrp_parameter):
        demand_items = self.env["mrp.demand"].search([("mrp_parameter_id", "=", mrp_parameter.id), ("state", "=", "done")])
        for demand_item in demand_items:
            demand_item_data = self._prepare_mrp_element_data_from_demand(mrp_parameter, demand_item)
            self.env["mrp.element"].create(demand_item_data)
        return True

    @api.model
    def _prepare_mrp_element_data_from_demand(self,  mrp_parameter, demand_item):
        return {
            "product_id": demand_item.product_id.id,
            "mrp_parameter_id": mrp_parameter.id,
            "production_id": None,
            "purchase_order_id": None,
            "purchase_line_id": None,
            "stock_move_id": None,
            "mrp_qty": - demand_item.mrp_qty,
            "mrp_date": fields.Datetime.from_string(demand_item.date_planned).date(),
            "mrp_type": "d",
            "mrp_origin": "di",
            "mrp_order_number": "Demand Item",
            "parent_product_id": None,
            "name": "Demand Item",
            "state": False,
            "fixed": False,
        }

    @api.model
    def _init_mrp_element_from_stock_move(self, mrp_parameter):
        in_domain = mrp_parameter._in_stock_moves_domain()
        in_moves = self.env["stock.move"].search(in_domain)
        out_domain = mrp_parameter._out_stock_moves_domain()
        out_moves = self.env["stock.move"].search(out_domain)
        if in_moves:
            for move in in_moves:
                in_move_data = self._prepare_mrp_element_data_from_stock_move(mrp_parameter, move, direction="in")
                self.env["mrp.element"].create(in_move_data)
        if out_moves:
            for move in out_moves:
                out_move_data = self._prepare_mrp_element_data_from_stock_move(mrp_parameter, move, direction="out")
                self.env["mrp.element"].create(out_move_data)
        return True

    @api.model
    def _prepare_mrp_element_data_from_stock_move(self, mrp_parameter, move, direction):
        if direction == "out":
            mrp_type = "d"
            product_qty = -move.product_qty
        elif direction == "in":
            mrp_type = "s"
            product_qty = move.product_qty
        mo = po = po_line = None
        origin = order_number = parent_product_id = name = None
        mrp_date = move.date_deadline or move.date
        if move.purchase_line_id:
            order_number = move.purchase_line_id.order_id.name
            origin = "po"
            po = move.purchase_line_id.order_id.id
            po_line = move.purchase_line_id.id
            name = move.name
        elif move.production_id:
            if move.production_id.location_dest_id.id == move.production_id.company_id.subcontracting_location_id.id:
                production = move.production_id
                origin_move = self.env["stock.move"].search([('reference', '=', move.group_id.name)], limit=1)
                order_number = origin_move.origin
                origin = "po"
                name = production.name
            else:
                production = move.production_id
                order_number = production.name
                origin = "mo"
                mo = production.id
                name = production.name
        elif move.raw_material_production_id:
            if move.raw_material_production_id.location_src_id.id == move.raw_material_production_id.company_id.subcontracting_location_id.id:
                production = move.raw_material_production_id
                origin_move = self.env["stock.move"].search([('reference', '=', move.group_id.name)], limit=1)
                order_number = origin_move.origin
                parent_product_id = origin_move.product_id.id
                origin = "po"
                name = production.name
                if origin_move.purchase_line_id:
                    date_order = origin_move.purchase_line_id.order_id.date_order
                    days_to_purchase = origin_move.company_id.days_to_purchase
                    mrp_date = date_order - timedelta(days=days_to_purchase)
                    if origin_move.warehouse_id.calendar_id and not days_to_purchase == 0:
                        calendar = origin_move.warehouse_id.calendar_id
                        mrp_date = calendar.plan_days(-days_to_purchase - 1, date_order, True)
            else:
                production = move.raw_material_production_id
                order_number = production.name
                origin = "mo"
                parent_product_id = production.product_id.id
                mo = production.id
                name = production.name
        elif move.sale_line_id:
            order_number = move.sale_line_id.order_id.name
            origin = "so"
            name = move.picking_id.name or move.name
            if mrp_parameter.demand_indicator == "10":
                product_qty = 0.0
        else:
            order_number = move.picking_id.name or move.name
            origin = "mv"
            name = move.picking_id.name or move.name
        return {
            "product_id": move.product_id.id,
            "mrp_parameter_id": mrp_parameter.id,
            "production_id": mo,
            "purchase_order_id": po,
            "purchase_line_id": po_line,
            "stock_move_id": move.id,
            "mrp_qty": product_qty,
            "mrp_date": mrp_date.date(),
            "mrp_type": mrp_type,
            "mrp_origin": origin,
            "mrp_order_number": order_number,
            "parent_product_id": parent_product_id,
            "name": name,
            "state": move.state,
            "fixed": False,
        }

    @api.model
    def _init_mrp_element_from_purchase_order(self, mrp_parameter):
        location_ids = mrp_parameter.location_ids
        picking_type_ids = self.env["stock.picking.type"].search([("default_location_dest_id", "in", location_ids.ids), ("code", "=", "incoming")]).ids
        pos = self.env["purchase.order"].search([("picking_type_id", "in", picking_type_ids),("state", "in", ["draft", "sent", "to approve"])])
        po_lines = self.env["purchase.order.line"].search([("order_id", "in", pos.ids), ("product_qty", ">", 0.0),("product_id", "=", mrp_parameter.product_id.id)])
        for po_line in po_lines:
            mrp_element_data = self._prepare_mrp_element_data_from_purchase_order(po_line, mrp_parameter)
            self.env["mrp.element"].create(mrp_element_data)
            # generazione dei fabbisogni di subcontracting dei componenti per le RfQs di subcontracting
            if mrp_parameter.supply_method == 'subcontracting' and mrp_parameter.bom_id and po_line.order_id.partner_id in mrp_parameter.bom_id.subcontractor_ids:
                for bomline in mrp_parameter.bom_id.bom_line_ids:
                    if bomline.product_qty <= 0.00 or bomline.product_id.type != "product":
                        continue
                    mrp_element_data2 = self._prepare_mrp_element_data_from_subcontracting_order(po_line, mrp_parameter, bomline)
                    self.env["mrp.element"].create(mrp_element_data2)
        return True

    @api.model
    def _prepare_mrp_element_data_from_purchase_order(self, po_line, mrp_parameter):
        mrp_date = fields.Datetime.from_string(po_line.date_planned)
        return {
            "product_id": po_line.product_id.id,
            "mrp_parameter_id": mrp_parameter.id,
            "production_id": None,
            "purchase_order_id": po_line.order_id.id,
            "purchase_line_id": po_line.id,
            "stock_move_id": None,
            "mrp_qty": po_line.product_uom_qty,
            "mrp_date": mrp_date.date(),
            "mrp_type": "s",
            "mrp_origin": "po",
            "mrp_order_number": po_line.order_id.name,
            "parent_product_id": None,
            "name": po_line.order_id.name,
            "state": po_line.order_id.state,
            "fixed": False,
        }

    @api.model
    def _prepare_mrp_element_data_from_subcontracting_order(self, po_line, mrp_parameter_id, bomline):
        mrp_date = False
        order_date = po_line.order_id.date_order
        days_to_purchase = mrp_parameter_id.company_id.days_to_purchase
        mrp_date = order_date - timedelta(days=days_to_purchase)
        if mrp_parameter_id.warehouse_id.calendar_id and not days_to_purchase == 0:
            calendar = mrp_parameter_id.warehouse_id.calendar_id
            mrp_date = calendar.plan_days(-days_to_purchase - 1, order_date, True)
        parent_product = mrp_parameter_id.product_id
        factor = (parent_product.product_tmpl_id.uom_id._compute_quantity(po_line.product_uom_qty, bomline.bom_id.product_uom_id) / bomline.bom_id.product_qty)
        line_quantity = factor * bomline.product_qty
        bomline_mrp_parameter_id = self.env["mrp.parameter"].search([("product_id", "=", bomline.product_id.id),("warehouse_id", "=", mrp_parameter_id.warehouse_id.id)], limit=1)
        if bomline_mrp_parameter_id:
            return {
                "product_id": bomline.product_id.id,
                "mrp_parameter_id": bomline_mrp_parameter_id.id,
                "production_id": None,
                "purchase_order_id": po_line.order_id.id,
                "purchase_line_id": po_line.id,
                "stock_move_id": None,
                "mrp_qty": -line_quantity,
                "mrp_date": fields.Datetime.from_string(mrp_date).date(),
                "mrp_type": "d",
                "mrp_origin": "po",
                "mrp_order_number": po_line.order_id.name,
                "parent_product_id": parent_product.id,
                "name": "Demand PO Subcontracting Explosion: %s %s" % (parent_product.name, bomline.product_id.name),
                "state": po_line.order_id.state,
                "fixed": False,
            }
        else:
            return False

    @api.model
    def _init_mrp_element_from_fixed_planned_order(self, mrp_parameter):
        planned_orders = self.env["mrp.planned.order"].search([("mrp_parameter_id", "=", mrp_parameter.id),("fixed", "=", True)])
        for planned_order in planned_orders:
            mrp_element_data = self._prepare_mrp_element_data_from_fixed_planned_order(planned_order, mrp_parameter)
            self.env["mrp.element"].create(mrp_element_data)
        return True

    @api.model
    def _prepare_mrp_element_data_from_fixed_planned_order(self, planned_order, mrp_parameter):
        mrp_date = fields.Datetime.from_string(planned_order.due_date)
        return {
            "product_id": planned_order.product_id.id,
            "mrp_parameter_id": mrp_parameter.id,
            "production_id": None,
            "purchase_order_id": None,
            "purchase_line_id": None,
            "stock_move_id": None,
            "mrp_qty": planned_order.mrp_qty,
            "mrp_date": mrp_date.date(),
            "mrp_type": "s",
            "mrp_origin": "op",
            "mrp_order_number": planned_order.name,
            "parent_product_id": None,
            "name": planned_order.name,
            "state": False,
            "fixed": True,
        }

    @api.model
    def _mrp_calculation(self, mrp_lowest_llc, warehouse_id):
        logger.info("Start MRP calculation")
        counter = planned_order_counter = llc = 0
        stock_mrp = 0.0
        release_date = mrp_date = False
        while mrp_lowest_llc > llc:
            mrp_parameters = self.env["mrp.parameter"].search([("llc", "=", llc),("warehouse_id", "=", warehouse_id.id), ("trigger", "=", "auto")])
            llc += 1
            for mrp_parameter in mrp_parameters:
                stock_mrp = mrp_parameter._compute_qty_available()
                if stock_mrp < mrp_parameter.mrp_minimum_stock:
                    qty_to_order = mrp_parameter.mrp_minimum_stock - stock_mrp
                    lot_qty = mrp_parameter._get_lot_qty(qty_to_order)
                    mrp_date = mrp_parameter._get_finish_date(datetime.now())
                    # planned order creation
                    planned_order = self.create_planned_order(mrp_parameter, mrp_date, lot_qty)
                    planned_order_counter += 1
                    stock_mrp += lot_qty
                for mrp_element_id in mrp_parameter.mrp_element_ids:
                    qty_to_order = mrp_parameter.mrp_minimum_stock - stock_mrp - mrp_element_id.mrp_qty
                    if qty_to_order > 0.0:
                        if mrp_parameter.lot_qty_method == 'S':
                            mrp_date = datetime.strptime(str(mrp_element_id.mrp_date), DEFAULT_SERVER_DATE_FORMAT) #datetime
                            last_date = warehouse_id.calendar_id.plan_days(mrp_parameter. mrp_coverage_days, mrp_date, True) # datetime
                            domain_damand = [
                                ('mrp_date', '>=', mrp_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT)),
                                ('mrp_date', '<=', last_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT)),
                                ('mrp_type', '=', 'd'),
                                ]
                            demand_records = mrp_parameter.mrp_element_ids.filtered_domain(domain_damand)
                            demand_mrp_qty = sum(demand_records.mapped('mrp_qty'))
                            qty_to_order = mrp_parameter.mrp_minimum_stock - stock_mrp - demand_mrp_qty
                        lot_qty = mrp_parameter._get_lot_qty(qty_to_order)
                        mrp_date = mrp_element_id.mrp_date
                        if mrp_parameter.mrp_safety_time > 0 and warehouse_id.calendar_id:
                            mrp_date = warehouse_id.calendar_id.plan_days(-mrp_parameter.mrp_safety_time -1, mrp_date, True)
                        # forward scheduling
                        #release_date = mrp_parameter._get_start_date(mrp_date)
                        #if release_date < datetime.now() and warehouse_id.company_id.forward_planning:
                        #    mrp_date = mrp_parameter._get_finish_date(datetime.now())
                        # planned order creation
                        if lot_qty > 0:
                            planned_order = self.create_planned_order(mrp_parameter, mrp_date, lot_qty)
                            planned_order_counter += 1
                            # strategy 50
                            if mrp_parameter.demand_indicator == "50" and mrp_element_id.mrp_origin == "di":
                                planned_order.conversion_indicator = False
                        stock_mrp += mrp_element_id.mrp_qty + lot_qty
                    else:
                        stock_mrp += mrp_element_id.mrp_qty
                counter += 1
            log_msg = "MRP Calculation LLC {} Finished - Nbr. products: {}".format(llc - 1, counter)
            logger.info(log_msg)
        logger.info("End MRP calculation")
        return counter, planned_order_counter


    @api.model
    def _rop_calculation(self, warehouse_id):
        logger.info("Start ROP calculation")
        counter = planned_order_counter = 0
        stock_mrp = 0.0
        mrp_element_in_records = False
        mrp_element_out_ready_records = False
        mrp_element_out_all_records = False
        mrp_element_in_qty = 0.0
        mrp_element_out_ready_qty = 0.0
        mrp_element_out_all_qty = 0.0
        mrp_parameters = self.env["mrp.parameter"].search([("llc", "=", -1),("warehouse_id", "=", warehouse_id.id), ("trigger", "=", "auto")])
        for mrp_parameter in mrp_parameters:
            to_date = mrp_parameter._get_finish_date(datetime.now()) + timedelta(days=1)
            to_date = to_date.date()
            stock_mrp = mrp_parameter._compute_qty_available()
            domain_mrp_element_in = [
                        ('mrp_parameter_id', '=', mrp_parameter.id),
                        ('mrp_type', '=', 's'),
                        ('mrp_date', '<=', to_date),
                        ]
            mrp_element_in_records = self.env["mrp.element"].search(domain_mrp_element_in)
            if mrp_element_in_records:
                mrp_element_in_qty = sum(mrp_element_in_records.mapped('mrp_qty'))
            if mrp_parameter.requirements_method == 'N':
                stock_mrp += mrp_element_in_qty
            elif mrp_parameter.requirements_method == 'C':
                domain_mrp_element_out_ready = [
                    ('mrp_parameter_id', '=', mrp_parameter.id),
                    ('mrp_type', '=', 'd'),
                    ('mrp_date', '<=', to_date),
                    ('state','=', 'assigned'),
                    ]
                mrp_element_out_ready_records = self.env["mrp.element"].search(domain_mrp_element_out_ready)
                if mrp_element_out_ready_records:
                    mrp_element_out_ready_qty = sum(mrp_element_out_ready_records.mapped('mrp_qty'))
                stock_mrp += mrp_element_in_qty + mrp_element_out_ready_qty
            elif mrp_parameter.requirements_method == 'A':
                domain_mrp_element_out_all = [
                    ('mrp_parameter_id', '=', mrp_parameter.id),
                    ('mrp_type', '=', 'd'),
                    ('mrp_date', '<=', to_date),
                    ]
                mrp_element_out_all_records = self.env["mrp.element"].search(domain_mrp_element_out_all)
                if mrp_element_out_all_records:
                    mrp_element_out_all_qty = sum(mrp_element_out_all_records.mapped('mrp_qty'))
                stock_mrp += mrp_element_in_qty + mrp_element_out_all_qty
            if stock_mrp is None:
                continue
            if float_compare(stock_mrp, mrp_parameter.mrp_threshold_stock, precision_rounding=mrp_parameter.product_id.uom_id.rounding) < 0:
                lot_qty = mrp_parameter._get_lot_qty(mrp_parameter.mrp_threshold_stock - stock_mrp) or 0.0
                if lot_qty > 0:
                    planned_order = self.create_planned_order(mrp_parameter, to_date, lot_qty)
                    planned_order_counter += 1
            counter += 1
            log_msg = "ROP Calculation Finished - Nbr. products: %s" % counter
            logger.info(log_msg)
        logger.info("End ROP calculation")
        return counter, planned_order_counter

    @api.model
    def create_planned_order(self, mrp_parameter_id, mrp_date, lot_qty):
        order_data = self._prepare_planned_order_data(mrp_parameter_id, lot_qty, mrp_date)
        planned_order = self.env["mrp.planned.order"].create(order_data)
        return planned_order

    @api.model
    def _prepare_planned_order_data(self, mrp_parameter_id, lot_qty, mrp_date):
        return {
            "mrp_parameter_id": mrp_parameter_id.id,
            "mrp_qty": lot_qty,
            "due_date": mrp_date,
            "fixed": False,
        }


class MRPPlanningMessage(models.TransientModel):
    _name = "mrp.planning.message"
    _description = "MRP Planning Engine Messages"

    name = fields.Text('Result', readonly=True)
