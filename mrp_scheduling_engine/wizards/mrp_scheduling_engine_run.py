# -*- coding: utf-8 -*-
# Copyright (c) OpenValue All Rights Reserved

from odoo import api, fields, models, _
from datetime import datetime, date
from pytz import timezone
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError
from docplex.cp.model import *


class MRPSchedulingEngineRun(models.TransientModel):
    _name = 'mrp.scheduling.engine.run'
    _description = 'MRP Planning Engine Run'

    @api.model
    def _get_default_scheduling_start_date(self):
        date = fields.Datetime.now() + relativedelta(days=1)
        date_utc = timezone('utc').localize(date)
        utc_time = date_utc.astimezone(timezone('UTC')).replace(tzinfo=None)
        current_user = self.env["res.users"].browse(self.env.uid)
        local_timezone = current_user.tz
        local_time = date_utc.astimezone(timezone(local_timezone)).replace(tzinfo=None)
        delta_hours = ((utc_time - local_time).total_seconds())/3600
        return date.replace(hour=0, minute=0, second=0, microsecond=0) + relativedelta(hours=delta_hours)

    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', required=True, domain=[('manufacture_to_resupply', '=', True)])
    scheduling_start_date = fields.Datetime('Scheduling Start Date', required=True, default=_get_default_scheduling_start_date)
    scheduling_horizon = fields.Integer('Scheduling Horizon (days)', required=True, default=14)


    @api.constrains('scheduling_horizon')
    def _check_scheduling_horizon(self):
        if self.scheduling_horizon <= 0:
            raise UserError(_('Scheduling Horizon has to be positive'))
        return True

    @api.constrains('scheduling_start_date')
    def _check_scheduling_start_date(self):
        if self.scheduling_start_date < fields.Datetime.now():
            raise UserError(_('Start Scheduling Date is in the past'))
        return True

    def action_scheduling_engine_run(self):
        message = self.scheduling_engine_run(self.warehouse_id, self.scheduling_start_date, self.scheduling_horizon)
        t_mess_id = False
        if message:
            t_mess_id = self.env["mrp.scheduling.message"].create({'message': message}).id
        else:
            t_mess_id = self.env["mrp.scheduling.message"].create({'message': 'no scheduling result'}).id
        return {
            'name': _('Scheduling Run Results'),
            "view_mode": 'form',
            'res_model': "mrp.scheduling.message",
            'res_id': t_mess_id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def scheduling_engine_run(self, warehouse_id, scheduling_start_date, scheduling_horizon):
        message = False
        counter = 0
        workorder_itvs = {} # dictionary delle decision variables dei WO
        production_itvs = {} # dictionary delle decision variables dei MO
        workcenter_assignment = {} # dictionary delle assegnazione dei WC ai WO
        workcenter_sequence = {} # dictionary delle sequence variables dei WC
        fail_limit = warehouse_id.company_id.fail_limit
        time_limit = warehouse_id.company_id.time_limit
        mdl = CpoModel()
        scheduling_finish_date = scheduling_start_date + relativedelta(days=scheduling_horizon)
        production_ids = self.env["mrp.production"].search([
            ("picking_type_id.warehouse_id", "=", warehouse_id.id),
            ("state", "in", ('confirmed', 'progress', 'to_close')),
            ("date_planned_finished_pivot", "<=", scheduling_finish_date),
            ("workorder_ids", "!=", False),
        ])
        workorder_ids = self.env["mrp.workorder"].search([
            ("production_id", "in", production_ids.ids),
            ("state", "in", ('pending', 'ready')),
        ])
        workcenter_ids = self.env["mrp.workcenter"].search([])
        # assegnazione dei workcenter ai workorder
        for workorder in workorder_ids:
            workcenter_assignment[workorder.id] = workorder.workcenter_id.id
        # Declarations of decision variables
        for production in production_ids:
            for workorder in production.workorder_ids.filtered(lambda r: r.state in ('pending', 'ready')):
                name = production.name+"_"+workorder.name
                size = int(workorder.duration_expected)
                workorder_itvs[(production.id, workorder.id)] = mdl.interval_var(size=size, name=name)
        for production in production_ids:
            name = production.name
            production_itvs[production.id] = mdl.interval_var(name=name)
        # span variables: tutte i workorders legati a un production orders
        for production in production_ids:
            wo_itvs_list = []
            for workorder in production.workorder_ids.filtered(lambda r: r.state in ('pending', 'ready')):
                wo_itvs_list.append(workorder_itvs[(production.id, workorder.id)])
            if wo_itvs_list:
                mdl.add(mdl.span(production_itvs[production.id], wo_itvs_list))
        # Create the objective function
        mdl.add(mdl.minimize(mdl.sum(mdl.length_of(production_itvs[production.id]) for production in production_ids)))
        # Workorders precedence constraints (each tuple (X, Y) means X ends before start of Y)
        for production in production_ids:
            for workorder in production.workorder_ids.filtered(lambda r: r.state in ('pending', 'ready')):
                sequence_wo = workorder.sequence
                prev_workorders = self.env["mrp.workorder"].search([
                    ('production_id', '=', workorder.production_id.id),
                    ('state', 'in', ('ready','pending'))]).filtered(lambda r: r.sequence < sequence_wo).sorted(key=lambda r: r.sequence, reverse=True)
                for prev_workorder in prev_workorders:
                    mdl.add(mdl.end_before_start(workorder_itvs[production.id, prev_workorder.id], workorder_itvs[production.id, workorder.id]))
        # sequence variable
        for workcenter_id in workcenter_ids:
            list_workorder_itvs = []
            for production in production_ids:
                for workorder in production.workorder_ids.filtered(lambda r: r.state in ('pending', 'ready')):
                    if workcenter_assignment[workorder.id] == workcenter_id.id:
                        list_workorder_itvs.append(workorder_itvs[production.id, workorder.id])
            workcenter_sequence[workcenter_id.id] = mdl.sequence_var(list_workorder_itvs, name=workcenter_id.name)
        # no overlap constraints
        for workcenter_id in workcenter_ids:
            mdl.add( mdl.no_overlap(workcenter_sequence[workcenter_id.id]))
        # solver
        msol = mdl.solve(FailLimit=fail_limit, TimeLimit=time_limit)
        counter = len(workorder_ids)
        message = _('scheduled workorders: %r' % counter)
        for production in production_ids:
            for workorder in production.workorder_ids.filtered(lambda r: r.state in ('pending', 'ready')):
                var_sol = msol.get_var_solution(workorder_itvs[(production.id, workorder.id)])
                workorder.ss_start = float(var_sol.get_start())
                workorder.ss_end = float(var_sol.get_end())
                workorder.scheduling_sequence = 0
                workorder.scheduling_date = scheduling_start_date
        for workcenter_id in workcenter_ids:
            counter = 1
            wc_workorder_ids = self.env["mrp.workorder"].search([
                ("production_id", "in", production_ids.ids),
                ("state", "in", ('pending', 'ready')),
                ("workcenter_id", "=", workcenter_id.id)
            ])
            for workorder in wc_workorder_ids.sorted(key=lambda r: r.ss_start, reverse=False):
                workorder.scheduling_sequence = counter
                counter += 1
        return message

    def scheduling_engine_run_background(self):
        warehouses = self.env["stock.warehouse"].search([('manufacture_to_resupply', '=', True)])
        for warehouse in warehouses:
            scheduling_start_date = self._get_default_scheduling_start_date()
            scheduling_horizon = warehouse.company_id.scheduling_horizon
            message = self.scheduling_engine_run(warehouse, scheduling_start_date, scheduling_horizon)
            if warehouse.partner_id.email:
                mail_obj = self.env['mail.mail']
                subject = "Scheduling Plan for: " + warehouse.name
                mail_data = {
                            'subject': subject,
                            'body_html': message,
                            'email_to': warehouse.partner_id.email,
                            }
                mail_id = mail_obj.create(mail_data)
                mail_id.send()
        return True


class MRPSchedulingMessage(models.TransientModel):
    _name = "mrp.scheduling.message"
    _description = "MRP Scheduling Engine Messages"

    message = fields.Text('Result', readonly=True)
