# -*- coding: utf-8 -*-


from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'
    _order = 'production_id, sequence, id'


    qty_production = fields.Float('Manufacturing Order Qty')
    duration = fields.Float('Elapsed')

    date_actual_start_wo = fields.Datetime('Actual Start Date', compute='_compute_dates_actual', store=True)
    date_actual_finished_wo = fields.Datetime('Actual End Date', compute='_compute_dates_actual', store=True)
    date_planned_start_wo = fields.Datetime('Scheduled Start Date', readonly=True, states={'ready': [('readonly', False)],'pending': [('readonly', False)]}, copy=False)
    date_planned_finished_wo = fields.Datetime('Scheduled End Date', readonly=True, states={'ready': [('readonly', False)],'pending': [('readonly', False)]}, copy=False)
    qty_output_wo = fields.Float('WO Quantity', digits='Product Unit of Measure', copy=False)
    qty_output_prev_wo = fields.Float('Previous WO Quantity', digits='Product Unit of Measure', compute="_compute_prev_work_order")
    prev_work_order_id = fields.Many2one('mrp.workorder', 'Previous Work Order', compute="_compute_prev_work_order")
    milestone = fields.Boolean('Milestone', compute='_get_milestone',  store=True, readonly=True, states={'ready': [('readonly', False)],'pending': [('readonly', False)]}, copy=True)
    sequence = fields.Integer('Sequence', compute='_get_sequence', store=True, readonly=True, states={'ready': [('readonly', False)],'pending': [('readonly', False)]}, copy=True)
    hours_uom = fields.Many2one('uom.uom', 'Hours', related='workcenter_id.hours_uom')
    wo_capacity_requirements = fields.Float('WO Capacity Requirements', compute='_wo_capacity_requirement', store=True)
    overall_duration = fields.Float('Overall Duration', compute='_compute_overall_duration', store=True)

    @api.depends('operation_id.milestone')
    def _get_milestone(self):
        for workorder in self:
            if workorder.operation_id and workorder.operation_id.milestone:
                workorder.milestone = True
        return True

    @api.depends('operation_id.sequence')
    def _get_sequence(self):
        for workorder in self:
            if workorder.operation_id and workorder.operation_id.sequence:
                workorder.sequence = workorder.operation_id.sequence
        return True

    @api.depends('time_ids.overall_duration')
    def _compute_overall_duration(self):
        for workorder in self:
            workorder.overall_duration = sum(workorder.time_ids.mapped('overall_duration'))
        return True

    @api.depends('duration_expected')
    def _wo_capacity_requirement(self):
        for workorder in self:
            workorder.wo_capacity_requirements = (workorder.duration_expected) / 60
        return True

    @api.depends('state')
    def _compute_prev_work_order(self):
        for workorder in self:
            prev_work_order = self.search([('next_work_order_id', '=', workorder.id)], limit=1)
            workorder.prev_work_order_id = prev_work_order
            product_qty = workorder.production_id.product_qty
            if prev_work_order:
                workorder.qty_output_prev_wo = prev_work_order.qty_output_wo
            else:
                workorder.qty_output_prev_wo = product_qty
        return True

    def button_start(self):
        for workorder in self:
            if workorder.qty_output_wo == 0.0:
                if not workorder.prev_work_order_id:
                    workorder.qty_output_wo = workorder.qty_production
                else:
                    workorder.qty_output_wo = workorder.qty_output_prev_wo
            if any(move.product_qty > move.forecast_availability for move in workorder.production_id.move_raw_ids) and not workorder.workcenter_id.start_without_stock:
                raise UserError(_('It is not possible to start workorder without components availability'))
            workorder.workorder_checks()
        return super().button_start()

    def workorder_checks(self):
        for workorder in self:
            if not workorder.date_planned_start_wo:
                raise UserError(_('Manufacturing Order not scheduled yet'))
            if workorder.qty_output_wo != workorder.qty_production and not workorder.workcenter_id.partial_confirmation:
                raise UserError(_('partial confirmation is not allowed'))
            if workorder.qty_output_wo > workorder.qty_production:
                raise UserError( _('It is not possible to produce more than production order quantity'))
            if workorder.qty_output_wo > workorder.qty_output_prev_wo and not workorder.milestone:
                raise UserError(_('It is not possible to produce more than %s') % workorder.qty_output_prev_wo)
            if workorder.milestone:
                sequence_milestone = workorder.sequence
                prev_workorders_closed = workorder.production_id.workorder_ids.filtered(lambda x: (x.sequence < sequence_milestone and x.state == 'done'))
                if prev_workorders_closed:
                    max_qty_output = min(prev_workorders_closed.mapped('qty_output_wo'))
                    if workorder.qty_output_wo > max_qty_output:
                        raise UserError(_('It is not possible to produce more than %s') % max_qty_output)
        return True

    @api.depends('time_ids','state')
    def _compute_dates_actual(self):
        date_start = False
        date_end = False
        for workorder in self:
            if workorder.state == 'done' and workorder.time_ids:
                date_start =  workorder.time_ids.sorted('date_start')[0].date_start
                date_end = workorder.time_ids.sorted('date_end')[-1].date_end
            workorder.date_actual_start_wo = date_start
            workorder.date_actual_finished_wo = date_end
        return True

    ## close workload
    def button_finish(self):
        super().button_finish()
        for workorder in self:
            wo_capacity_ids = self.env['mrp.workcenter.capacity'].search([('workorder_id', '=', workorder.id)])
            wo_capacity_ids.unlink()
            if workorder.milestone:
                workorders = workorder.production_id.workorder_ids
                sequence_milestone = workorder.sequence
                prev_workorders = [x for x in workorders if x.sequence < sequence_milestone]
                if any(prev_workorder.state == 'progress' for prev_workorder in prev_workorders):
                    raise UserError(_('previous workorders in progress'))
                for prev_workorder in prev_workorders:
                    if prev_workorder.state in ('ready','pending'):
                        prev_workorder.state = 'cancel'
                    wo_capacity_id = self.env['mrp.workcenter.capacity'].search([('workorder_id', '=', prev_workorder.id)],limit=1)
                    if wo_capacity_id:
                        wo_capacity_id.unlink()
            workorder.qty_producing = workorder.qty_output_wo
        return True

    def _get_capacity_load(self, start_date, end_date):
        sdate =  start_date.date()
        edate = end_date.date()
        delta = edate - sdate
        list_days = []
        nro_hours = 0.0
        list_days.append(start_date)
        for i in range(delta.days):
            day = sdate + timedelta(days=i+1)
            day = datetime.combine(day, datetime.min.time())
            list_days.append(day)
        list_days.append(end_date)
        for i in range(len(list_days) - 1):
            for workorder in self:
                nro_hours = workorder.workcenter_id.resource_calendar_id.get_work_duration_data(list_days[i], list_days[i+1])['hours']
                if  nro_hours > 0:
                    id_created= self.env['mrp.workcenter.capacity'].create({
                        'workcenter_id': workorder.workcenter_id.id,
                        'workorder_id': workorder.id,
                        'product_id': workorder.production_id.product_id.id,
                        'product_qty': workorder.production_id.product_qty,
                        'product_uom_id': workorder.production_id.product_uom_id.id,
                        'date_planned': list_days[i],
                        'wo_capacity_requirements': nro_hours,
                    })
        return True

    ## create/change workload
    @api.constrains('date_planned_start_wo', 'date_planned_finished_wo')
    def _change_scheduled_dates(self):
        for workorder in self:
            date_planned_start = workorder.date_planned_start_wo
            date_planned_finish = workorder.date_planned_finished_wo
            if date_planned_start and date_planned_finish:
                wo_capacity_ids = self.env['mrp.workcenter.capacity'].search([('workorder_id', '=', workorder.id)])
                wo_capacity_ids.unlink()
                workorder._get_capacity_load(date_planned_start, date_planned_finish)
        return True

    def backwards_scheduling(self):
        for workorder in self:
            time_delta = workorder.duration_expected
            workorder.date_planned_start_wo = workorder.date_planned_finished_wo - timedelta(minutes=time_delta)
            if workorder.workcenter_id.resource_calendar_id:
                calendar = workorder.workcenter_id.resource_calendar_id
                duration_expected = - workorder.duration_expected / 60
                workorder.date_planned_start_wo = calendar.plan_hours(duration_expected, workorder.date_planned_finished_wo, True)

    def forwards_scheduling(self):
        for workorder in self:
            time_delta = workorder.duration_expected
            workorder.date_planned_finished_wo = workorder.date_planned_start_wo + timedelta(minutes=time_delta)
            if workorder.workcenter_id.resource_calendar_id:
                calendar = workorder.workcenter_id.resource_calendar_id
                duration_expected = workorder.duration_expected / 60
                workorder.date_planned_finished_wo = calendar.plan_hours(duration_expected, workorder.date_planned_start_wo, True)