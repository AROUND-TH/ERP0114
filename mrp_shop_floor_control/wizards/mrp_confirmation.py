# -*- coding: utf-8 -*-


from odoo import models, fields, api, _
from odoo.exceptions import UserError
import datetime
from odoo.tools import float_round


class MrpConfirmation(models.TransientModel):
    _name = 'mrp.confirmation'
    _description = "MRP Confirmation"

    date_start = fields.Datetime('Start Date', required=True)
    date_end = fields.Datetime('End Date', compute='_compute_date_end')
    setup_duration = fields.Float('Setup Duration')
    teardown_duration = fields.Float('Teardown Duration')
    working_duration = fields.Float('Working Duration', required=True)
    overall_duration = fields.Float('Overall Duration', compute='_compute_duration')
    production_id = fields.Many2one('mrp.production', 'Production Order', domain=[('workorder_ids', '!=', []),('wo_confirmation','=', True)])
    product_id = fields.Many2one('product.product', 'Product', related='production_id.product_id', readonly=True)
    tracking = fields.Selection(related='product_id.tracking')
    final_lot_id = fields.Many2one('stock.production.lot', "Lot/Serial Number")
    workorder_id = fields.Many2one('mrp.workorder', "Workorder", domain="[('state', 'not in', ['done', 'cancel']), ('production_id','=',production_id)]")
    qty_production = fields.Float('Manufacturing Order Qty', readonly=True, related ='workorder_id.qty_production')
    qty_output_wo = fields.Float('WO Quantity', digits='Product Unit of Measure')
    product_uom_id = fields.Many2one('uom.uom', 'Unit of Measure', related='production_id.product_uom_id', readonly=True)
    user_id = fields.Many2one('res.users', string='User', required=True, default=lambda self: self.env.user, check_company=True)
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    milestone = fields.Boolean('Milestone', related='workorder_id.milestone')

    @api.depends('setup_duration', 'teardown_duration', 'working_duration')
    def _compute_duration(self):
        overall_duration = 0.0
        for record in self:
            overall_duration = record.setup_duration + record.teardown_duration + record.working_duration
            record.overall_duration = overall_duration
        return True

    @api.depends('overall_duration', 'date_start')
    def _compute_date_end(self):
        conf_duration = 0.0
        for record in self:
            record.date_end = False
            if record.overall_duration:
                conf_duration = datetime.timedelta(minutes=record.overall_duration)
                record.date_end = record.date_start + conf_duration
                if record.workorder_id.workcenter_id.resource_calendar_id:
                    calendar = record.workorder_id.workcenter_id.resource_calendar_id
                    record.date_start = calendar.plan_hours(0.0, record.date_start, True)
                    conf_duration = record.overall_duration / 60
                    record.date_end = calendar.plan_hours(conf_duration, record.date_start, True)
        return True

    @api.onchange('production_id')
    def onchange_production_id(self):
        workorder_domain = [('state', 'not in', ['done', 'cancel'])]
        if self.production_id:
            workorder_domain += [('production_id', '=', self.production_id.id)]
            workorder_ids = self.env['mrp.workorder'].search(workorder_domain)
            if workorder_ids:
                if self.workorder_id and self.workorder_id.id not in workorder_ids.ids:
                    self.workorder_id = False
                return {'domain': {'workorder_id': [('id', 'in', workorder_ids.ids)]}}

    @api.constrains('qty_output_wo')
    def check_qty_output_wo(self):
        for record in self:
            if not record.qty_output_wo > 0.0:
                raise UserError(_('Quantity has to be positive'))
        return True

    @api.onchange('workorder_id')
    def onchange_workorder_id(self):
        for record in self:
            record.qty_output_wo = record.workorder_id.qty_output_prev_wo
            if record.milestone and not record.workorder_id.prev_work_order_id.state == 'done':
                sequence_milestone = record.workorder_id.sequence
                prev_workorders_closed = record.production_id.workorder_ids.filtered(lambda x: (x.sequence < sequence_milestone and x.state == 'done'))
                if prev_workorders_closed:
                    record.qty_output_wo = min(prev_workorders_closed.mapped('qty_output_wo'))
                else:
                    record.qty_output_wo = record.workorder_id.qty_production
            if record.workorder_id.prev_work_order_id.date_actual_finished_wo:
                record.date_start = record.workorder_id.prev_work_order_id.date_actual_finished_wo
            else:
                record.date_start = record.workorder_id.date_planned_start_wo or record.production_id.date_planned_start_pivot or fields.Datetime.now()

    @api.onchange('workorder_id', 'qty_output_wo')
    def onchange_workorder_id_qty_output_wo(self):
        quantity = 0.0
        prod_quantity = 0.0
        cycle_number = 0.0
        prod_cycle_number = 0.0
        duration_expected_working = 0.0
        for record in self:
            if record.workorder_id:
                prod_quantity = record.production_id.product_uom_qty
                prod_cycle_number = float_round(prod_quantity / record.workorder_id.workcenter_id.capacity, precision_digits=0, rounding_method='UP')
                duration_expected_working = (record.workorder_id.duration_expected - record.workorder_id.workcenter_id.time_start - record.workorder_id.workcenter_id.time_stop) * record.workorder_id.workcenter_id.time_efficiency / (100.0 * prod_cycle_number)
                if duration_expected_working < 0.0:
                    duration_expected_working = 0.0
                quantity = record.product_uom_id._compute_quantity(record.qty_output_wo, record.product_id.product_tmpl_id.uom_id)
                cycle_number = float_round(quantity / record.workorder_id.workcenter_id.capacity, precision_digits=0, rounding_method='UP')
                record.working_duration = duration_expected_working * cycle_number * 100.0 / record.workorder_id.workcenter_id.time_efficiency or 0.0
                record.setup_duration = record.workorder_id.workcenter_id.time_start or 0.0
                record.teardown_duration = record.workorder_id.workcenter_id.time_stop or 0.0

    def do_confirm(self):
        #self.workorder_id.workorder_checks()
        self.workorder_id.finished_lot_id = self.final_lot_id
        self.workorder_id.qty_output_wo = self.qty_output_wo
        if self.workorder_id.state in ['ready', 'pending', 'progress']:
            self.workorder_id.button_start()
        time_id = self.env['mrp.workcenter.productivity'].search([('workorder_id','=',self.workorder_id.id),('date_end','=',False)], limit=1)
        if time_id:
            time_values = {'overall_duration': self.overall_duration,
                        'setup_duration': self.setup_duration,
                        'teardown_duration': self.teardown_duration,
                        'working_duration': self.working_duration,
                        'date_start': self.date_start,
                        'date_end': self.date_end,
                        'user_id': self.user_id.id,
                        }
            time_id.write(time_values)
        self.workorder_id.button_finish()
        return True

    @api.model
    def default_get(self, fields):
        default = super().default_get(fields)
        active_id = self.env.context.get('active_id', False)
        if active_id:
            default['production_id'] = active_id
        return default

    def _reopen_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new'
        }

    def action_generate_serial(self):
        self.ensure_one()
        product_produce_wiz = self.env.ref('mrp.view_mrp_product_produce_wizard', False)
        self.final_lot_id = self.env['stock.production.lot'].create({
            'product_id': self.product_id.id,
            'company_id': self.production_id.company_id.id
        })
        return self._reopen_form()
