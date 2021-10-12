# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta
from datetime import datetime, date, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'


    lot_producing_id = fields.Many2one(states={'done': [('readonly', True)]})
    user_id = fields.Many2one(states={'done': [('readonly', True)]})

    date_planned_start_pivot = fields.Datetime('Planned Start Pivot Date', default=lambda self: fields.datetime.now(), readonly=True, states={'draft': [('readonly', False)], 'confirmed': [('readonly', False)]})
    #date_planned_finished_pivot = fields.Datetime('Planned End Pivot Date', readonly=True, states={'draft': [('readonly', False)], 'confirmed': [('readonly', False)]}, compute='_compute_planned_pivot_finished_date', inverse='_set_planned_pivot_finished_date', store=True)
    date_planned_finished_pivot = fields.Datetime('Planned End Pivot Date', readonly=True, states={'draft': [('readonly', False)], 'confirmed': [('readonly', False)]}, compute='_compute_planned_pivot_finished_date', store=True)
    date_planned_start_wo = fields.Datetime("Scheduled Start Date", readonly=True, copy=False)
    date_planned_finished_wo = fields.Datetime("Scheduled End Date", readonly=True, copy=False)
    date_actual_start_wo = fields.Datetime('Start Date', copy=False, readonly=True, compute="get_actual_dates", store=True)
    date_actual_finished_wo = fields.Datetime('End Date', copy=False, readonly=True, compute="get_actual_dates", store=True)
    origin = fields.Char(readonly=True, states={'draft': [('readonly', False)]})
    wo_confirmation = fields.Boolean('WO Confirmation Indicator', compute='_get_wo_confirmation', store=True)
    is_scheduled = fields.Boolean('Its Operations are Scheduled', compute='_compute_is_scheduled', store=True)


    def _generate_backorder_productions(self, close_mo=True):
        backorders = super()._generate_backorder_productions(close_mo)
        for backorder in backorders:
            backorder.qty_producing = 0
            backorder.state = 'confirmed'
        for workorder in backorders.workorder_ids:
            workorder.qty_produced = 0
            workorder.qty_producing = 0
        return backorders

    def action_capacity_check(self):
        return {
            'name': _('Capacity Check'),
            'view_mode': 'form',
            'res_model': 'mrp.capacity.check',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.depends('date_planned_start_pivot', 'product_id', 'company_id', 'picking_type_id')
    def _compute_planned_pivot_finished_date(self):
        date_start = False
        date_finished = False
        for production in self:
            date_start = production.date_planned_start_pivot or fields.Datetime.now()
            date_finished = date_start + relativedelta(days=production.product_id.produce_delay + 1)
            if production.company_id.manufacturing_lead > 0:
                date_finished = date_finished + relativedelta(days=production.company_id.manufacturing_lead + 1)
            if production.picking_type_id.warehouse_id.calendar_id:
                calendar = production.picking_type_id.warehouse_id.calendar_id
                date_start = calendar.plan_hours(0.0, date_start, True)
                date_finished = calendar.plan_days(production.product_id.produce_delay + 1, date_start, True)
                if production.company_id.manufacturing_lead > 0:
                    date_finished = calendar.plan_days(production.company_id.manufacturing_lead  + 1, date_finished, True)
            if date_finished == date_start:
                date_finished = date_start + relativedelta(hours=1)
            production.date_planned_start_pivot = date_start
            production.date_planned_finished_pivot = date_finished
        return True

    #def _set_planned_pivot_finished_date(self):
    #    date_start = False
    #    date_finished = False
    #    for production in self:
    #        if production.date_planned_finished_pivot:
    #            date_finished = production.date_planned_finished_pivot
    #            date_start = date_finished - relativedelta(days=production.product_id.produce_delay + 1)
    #            if production.company_id.manufacturing_lead > 0:
    #                date_start = date_start - relativedelta(days=production.company_id.manufacturing_lead + 1)
    #            if production.picking_type_id.warehouse_id.calendar_id:
    #                calendar = production.picking_type_id.warehouse_id.calendar_id
    #                date_finished = calendar.plan_hours(0.0, date_finished, True)
    #                date_start = calendar.plan_days(- production.product_id.produce_delay - 1, date_finished, True)
    #                if production.company_id.manufacturing_lead > 0:
    #                    date_start = calendar.plan_days(- production.company_id.manufacturing_lead - 1, date_start, True)
    #            if date_finished == date_start:
    #                date_start = date_finished + relativedelta(hours= -1)
    #        production.date_planned_start_pivot = date_start
    #        production.date_planned_finished_pivot = date_finished
    #    return True

    @api.depends("workorder_ids.date_planned_start_wo")
    def _compute_is_scheduled(self):
        for production in self:
            if production.workorder_ids:
                production.is_scheduled = any(workorder.date_planned_start_wo for workorder in production.workorder_ids if workorder.state not in ('done', 'cancel'))
            else:
                production.is_scheduled = False
        return True

    @api.depends('workorder_ids.state', 'is_scheduled')
    def _get_wo_confirmation(self):
        for production in self:
            production.wo_confirmation = False
            if any(workorder.state in ('pending','ready','progress') for workorder in production.workorder_ids) and production.is_scheduled:
                production.wo_confirmation = True
        return True

    ## scheduling
    def schedule_workorders(self):
        max_date_finished = False
        start_date = False
        for production in self:
            production.date_planned_start_wo = False
            production.date_planned_finished_wo = False
            floating_times_id = self.env['mrp.floating.times'].search([('warehouse_id', '=', production.picking_type_id.warehouse_id.id)])
            if not floating_times_id:
                raise UserError(_('Floating Times record has not been created yet for the warehouse: %s')% production.picking_type_id.warehouse_id.name)
            warehouse_calendar = production.picking_type_id.warehouse_id.calendar_id
            start_date = production.date_planned_start_pivot or fields.Datetime.now()
            # Release production
            release_time = floating_times_id.mrp_release_time
            if release_time > 0.0 and warehouse_calendar:
                start_date = warehouse_calendar.plan_hours(release_time, start_date, True)
            # before production
            before_production_time = floating_times_id.mrp_ftbp_time
            if before_production_time > 0.0 and warehouse_calendar:
                start_date = warehouse_calendar.plan_hours(before_production_time, start_date, True)
            production.date_planned_start_wo = start_date
            # workorders scheduling
            for workorder in production.workorder_ids:
                if not workorder.prev_work_order_id:
                    workorder.date_planned_start_wo = start_date
                    calendar = workorder.workcenter_id.resource_calendar_id
                    if calendar:
                        workorder.date_planned_start_wo = calendar.plan_hours(0.0, workorder.date_planned_start_wo, True)
                else:
                    if not workorder.sequence == workorder.prev_work_order_id.sequence:
                        workorder.date_planned_start_wo = max_date_finished or workorder.prev_work_order_id.date_planned_finished_wo
                    else:
                        workorder.date_planned_start_wo = workorder.prev_work_order_id.date_planned_start_wo
                workorder.forwards_scheduling()
                if workorder.prev_work_order_id:
                    max_date_finished = max(workorder.date_planned_finished_wo, workorder.prev_work_order_id.date_planned_finished_wo)
                else:
                    max_date_finished = workorder.date_planned_finished_wo
            # after production
            after_production_time = floating_times_id.mrp_ftap_time
            if after_production_time > 0.0 and warehouse_calendar:
                max_date_finished = warehouse_calendar.plan_hours(after_production_time, max_date_finished, True)
            production.date_planned_finished_wo = max_date_finished
        return True

    def button_plan(self):
        res = super().button_plan()
        for production in self:
            production.schedule_workorders()
            production.move_finished_ids.write({'date': production.date_planned_finished_pivot, 'date_deadline': production.date_planned_finished_pivot})
            production.move_raw_ids.write({'date': production.date_planned_start_pivot, 'date_deadline': production.date_planned_start_pivot})
            production.picking_ids.write({'scheduled_date': production.date_planned_start_pivot, 'date_deadline': production.date_planned_start_pivot})
        return res

    ## delete workload
    def button_unplan(self):
        res = super().button_unplan()
        for production in self:
            for workorder in production.workorder_ids:
                workorder.date_planned_start_wo = False
                workorder.date_planned_finished_wo = False
            wo_capacity_ids = self.env['mrp.workcenter.capacity'].search([('workorder_id', 'in', production.workorder_ids.ids)])
            wo_capacity_ids.unlink()
            production.date_planned_start_wo = False
            production.date_planned_finished_wo = False
        return res

    @api.depends('state')
    def get_actual_dates(self):
        for production in self:
            if production.workorder_ids:
                if production.state == "done" and production.workorder_ids:
                    workorders = self.env['mrp.workorder'].search([('production_id', '=', production.id),('state', '=', 'done')])
                    time_records = self.env['mrp.workcenter.productivity'].search([('workorder_id', 'in', workorders.ids)])
                    if time_records:
                        production.date_actual_start_wo = time_records.sorted('date_start')[0].date_start
                        production.date_actual_finished_wo = time_records.sorted('date_end')[-1].date_end
            else:
                if production.state == "confirmed":
                    production.write({'date_actual_start_wo': fields.Datetime.now()})
                if production.state == "done":
                    production.write({'date_actual_finished_wo': fields.Datetime.now()})
        return True

    ## delete workload
    def action_cancel(self):
        for production in self:
            if production.workorder_ids:
                wo_capacity_ids = self.env['mrp.workcenter.capacity'].search([('workorder_id', 'in', production.workorder_ids.ids)])
                wo_capacity_ids.unlink()
                if any(workorder.state == 'progress' for workorder in production.workorder_ids):
                    raise UserError(_('workorder still running, please close it'))
        return super().action_cancel()

    def button_mark_done(self):
        for production in self:
            if production.workorder_ids:
                if any(workorder.state not in ('done', 'cancel') for workorder in production.workorder_ids):
                    raise UserError(_('workorders not yet processed, please close them before'))
            if production.picking_type_id.active:
                if any(picking_id.state not in ('done', 'cancel') for picking_id in production.picking_ids):
                    raise UserError(_('pickings not yet processed, please close or cancel them'))
        return super().button_mark_done()

    @api.constrains('date_planned_start_pivot', 'date_planned_finished_pivot')
    def _align_stock_moves_dates(self):
        for production in self:
            if production.date_planned_finished_pivot and production.date_planned_start_pivot:
                production.move_finished_ids.write({'date': production.date_planned_finished_pivot, 'date_deadline': production.date_planned_finished_pivot})
                production.move_raw_ids.write({'date': production.date_planned_start_pivot, 'date_deadline': production.date_planned_start_pivot})
                production.picking_ids.write({'scheduled_date': production.date_planned_start_pivot, 'date_deadline': production.date_planned_start_pivot})
        return True

    @api.depends(
        'move_raw_ids.state', 'move_raw_ids.quantity_done', 'move_finished_ids.state',
        'workorder_ids', 'workorder_ids.state', 'product_qty', 'qty_producing')
    def _compute_state(self):
        super()._compute_state()
        for production in self:
            if production.workorder_ids:
                if any(wo_state in ('progress', 'done') for wo_state in production.workorder_ids.mapped('state')):
                    production.state = 'progress'
                if all(wo_state in ('cancel', 'done') for wo_state in production.workorder_ids.mapped('state')):
                    production.state = 'to_close'
                if production.state == 'to_close' and all(move.state in ('cancel', 'done') for move in production.move_raw_ids):
                    production.state = 'done'
                if all(move.state == 'cancel' for move in production.move_raw_ids):
                    production.state = 'cancel'
        return True
