# -*- coding: utf-8 -*-


from odoo import models, fields, api, _


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'


    ss_start = fields.Float('Scheduled Start', copy=False)
    ss_end = fields.Float('Scheduled End', copy=False)
    scheduling_sequence = fields.Integer('Scheduling Sequence', copy=False)
    scheduling_date = fields.Datetime('Scheduling Date', copy=False)
    date_scheduled_start = fields.Datetime('Scheduled Start Date', compute='_compute_scheduled_dates', compute_sudo=True)
    date_scheduled_finished = fields.Datetime('Scheduled End Date', compute='_compute_scheduled_dates', compute_sudo=True)
    expected_delay = fields.Float('Expected Delay', compute='_get_expected_delay', compute_sudo=True, store=True)


    @api.depends('scheduling_date', 'ss_start', 'ss_end')
    def _compute_scheduled_dates(self):
        for workorder in self:
            workorder.date_scheduled_start = False
            workorder.date_scheduled_finished = False
            calendar = workorder.workcenter_id.resource_calendar_id
            if calendar and workorder.scheduling_date:
                workorder.date_scheduled_start = calendar.plan_hours(workorder.ss_start/60, workorder.scheduling_date, True)
                workorder.date_scheduled_finished = calendar.plan_hours(workorder.ss_end/60, workorder.scheduling_date, True)
        return True

    @api.depends('date_scheduled_finished', 'production_id.date_planned_finished_pivot')
    def _get_expected_delay(self):
        for workorder in self:
            workorder.expected_delay = 0
            if workorder.date_scheduled_finished and workorder.date_scheduled_finished > workorder.production_id.date_planned_finished_pivot:
                workorder.expected_delay = (workorder.date_scheduled_finished - workorder.production_id.date_planned_finished_pivot).total_seconds()/3600.0
        return True



