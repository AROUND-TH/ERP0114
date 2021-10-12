# -*- coding: utf-8 -*-


from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'


    prev_date_planned_start_wo = fields.Datetime(string='Previous Scheduled Start Date ', readonly=True)


    def write(self, values):
        if values.get('date_planned_start_wo', False):
            self.prev_date_planned_start_wo = self.date_planned_start_wo
        return super().write(values)

    def mid_point_scheduling_engine(self):
        for workorder in self:
            sequence_wo = workorder.operation_id.sequence
            max_date_finished = False
            min_date_start = False
            max_date_finished_in_progress = False

            parall_workorders = self.search([
                ('production_id', '=', workorder.production_id.id),
                ('state', 'in', ('ready','pending','progress'))]).filtered(lambda r: r.sequence == sequence_wo)
            if parall_workorders:
                wos_in_progress = parall_workorders.filtered(lambda r: r.state == 'progress').sorted(key=lambda r: r.date_planned_finished_wo)
                if wos_in_progress:
                    last_wo_in_progress = wos_in_progress[-1]
                    max_date_finished_in_progress = last_wo_in_progress.date_planned_finished_wo
                current_workorder = workorder
                for parall_workorder in parall_workorders:
                    if not parall_workorder.state == 'progress':
                        parall_workorder.date_planned_start_wo = current_workorder.date_planned_start_wo
                        parall_workorder.forwards_scheduling()
                        if max_date_finished_in_progress and parall_workorder.date_planned_finished_wo < max_date_finished_in_progress:
                            raise UserError(_('backward scheduling is not possible'))
                    max_date_finished = max(parall_workorder.date_planned_finished_wo, current_workorder.date_planned_finished_wo)
                    min_date_start = min(parall_workorder.date_planned_start_wo, current_workorder.date_planned_start_wo)

            prev_workorders = self.search([
                ('production_id', '=', workorder.production_id.id),
                ('state', 'in', ('ready','pending','progress'))]).filtered(lambda r: r.sequence < sequence_wo).sorted(key=lambda r: r.sequence, reverse=True)
            if prev_workorders:
                current_workorder = workorder
                for prev_workorder in prev_workorders:
                    if prev_workorder.state == 'progress':
                        if prev_workorder.date_planned_finished_wo > current_workorder.date_planned_start_wo:
                            raise UserError(_('backward scheduling is not possible'))
                        else:
                            break
                    else:
                        if not current_workorder.sequence == prev_workorder.sequence:
                            prev_workorder.date_planned_finished_wo = min_date_start or current_workorder.date_planned_start_wo
                        else:
                            prev_workorder.date_planned_finished_wo = current_workorder.date_planned_finished_wo
                        prev_workorder.backwards_scheduling()
                        min_date_start = min(prev_workorder.date_planned_start_wo, current_workorder.date_planned_start_wo)
                        current_workorder = prev_workorder

            succ_workorders = self.search([
                ('production_id', '=', workorder.production_id.id),
                ('state', 'in', ('ready','pending','progress'))]).filtered(lambda r: r.sequence > sequence_wo).sorted(key=lambda r: r.sequence)
            if succ_workorders:
                current_workorder = workorder
                for succ_workorder in succ_workorders:
                    if succ_workorder.state == 'progress':
                        if succ_workorder.date_planned_start_wo < current_workorder.date_planned_finished_wo:
                            raise UserError(_('forward scheduling is not possible'))
                        else:
                            break
                    else:
                        if not current_workorder.sequence == succ_workorder.sequence:
                            succ_workorder.date_planned_start_wo = max_date_finished or current_workorder.date_planned_finished_wo
                        else:
                            succ_workorder.date_planned_start_wo = current_workorder.date_planned_start_wo
                        succ_workorder.forwards_scheduling()
                        max_date_finished = max(succ_workorder.date_planned_finished_wo, current_workorder.date_planned_finished_wo)
                        current_workorder = succ_workorder
            workorder.production_id.date_planned_start_wo = min_date_start
            workorder.production_id.date_planned_finished_wo = max_date_finished
        return True


class set_date_wizard(models.TransientModel):
    _name = 'set.date.wizard'
    _description = "Mid Point Scheduling Wizard"

    new_date_planned_start_wo = fields.Datetime(string=_('New Scheduled Start Date'), required=True)
    workorder_id = fields.Many2one('mrp.workorder', string="Workorder", readonly=True)

    @api.model
    def default_get(self, fields):
        default = super().default_get(fields)
        active_id = self.env.context.get('active_id', False)
        if active_id:
            default['workorder_id'] = active_id
        return default

    def set_date(self):
        new_date_planned = False
        workorder_id = self.env.context.get('active_id', False)
        if workorder_id:
            workorder = self.env['mrp.workorder'].browse(workorder_id)
            if workorder.state == 'progress':
                raise UserError(_('midpoint scheduling cannot be performed for workorder in progress'))
            if not workorder.date_planned_start_wo:
                raise UserError(_('Manufacturing Order not scheduled yet'))
            calendar = workorder.workcenter_id.resource_calendar_id
            new_date_planned = calendar.plan_hours(0.0, self.new_date_planned_start_wo, True)
            workorder.write({'date_planned_start_wo': new_date_planned})
            workorder.mid_point_scheduling_engine()
        return True
