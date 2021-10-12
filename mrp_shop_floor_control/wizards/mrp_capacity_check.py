# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from datetime import datetime, date, timedelta


class MrpCapacityCheck(models.TransientModel):
    _name = "mrp.capacity.check"
    _description = 'MRP Capacity Check'


    def _default_production_id(self):
        return self.env['mrp.production'].browse(self.env.context.get('active_id'))

    production_id = fields.Many2one("mrp.production", 'Manufacturing Order', default=lambda self: self._default_production_id(), readonly=True)
    capacity_item_ids = fields.One2many('mrp.capacity.check.item', 'check_id', string="Capacity Items", readonly=True)
    capacity_item_all_ids = fields.One2many('mrp.capacity.check.allitem', 'check_id', string="Capacity Items", readonly=True)


    @api.onchange('production_id')
    def get_records(self):
        workcenters = self.env['mrp.workcenter'].search([('id', 'in', self.production_id.workorder_ids.workcenter_id.ids)])
        result = {wc: {} for wc in workcenters.ids}
        result_all = {wc: {} for wc in workcenters.ids}
        domain = [('production_id', '=', self.production_id.id)]
        domain_all = [('workcenter_id', 'in', workcenters.ids)]
        res = self.env["mrp.workcenter.capacity"].read_group(domain,
            ['workcenter_id', 'week_nro', 'wo_capacity_requirements'], ['workcenter_id', 'week_nro'],
            lazy=False)
        for res_group in res:
            result[res_group['workcenter_id'][0]][res_group['week_nro']] = res_group['wo_capacity_requirements']
        for workcenter in workcenters:
            for week, req in result[workcenter.id].items():
                id_created_item = self.env['mrp.capacity.check.item'].create({
                    'workcenter_id': workcenter.id,
                    'week_nro': week,
                    'wo_capacity_requirements': req,
                    'check_id': self.id,
                })
        res_all = self.env["mrp.workcenter.capacity"].read_group(domain_all,
            ['workcenter_id', 'week_nro', 'wo_capacity_requirements'], ['workcenter_id', 'week_nro'],
            lazy=False)
        for res_group_all in res_all:
            result_all[res_group_all['workcenter_id'][0]][res_group_all['week_nro']] = res_group_all['wo_capacity_requirements']
        for workcenter in workcenters:
            for week, req in result_all[workcenter.id].items():
                id_created_allitem = self.env['mrp.capacity.check.allitem'].create({
                    'workcenter_id': workcenter.id,
                    'week_nro': week,
                    'wo_capacity_requirements': req,
                    'check_id': self.id,
                })
                item = self.env['mrp.capacity.check.item'].search([('workcenter_id', '=', workcenter.id),('week_nro', '=', week)])
                if item:
                    id_created_allitem.indicator = True
        return self._reopen_form()

    def _reopen_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'new'}


class MrpCapacityCheckItem(models.TransientModel):
    _name = "mrp.capacity.check.item"
    _description = 'MRP Capacity Check Item'

    check_id = fields.Many2one('mrp.capacity.check', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center')
    week_nro = fields.Char('Original Week Number')
    week_nro_2 = fields.Char('Week Number', compute='_get_week_number_2')
    wo_capacity_requirements = fields.Float('WO Capacity Requirements (Hours)')
    wc_available_capacity_cal = fields.Float('WC Weekly Available Capacity', compute='_calculate_wc_available_capacity_cal', store=True)
    monday = fields.Datetime('Monday')
    sunday = fields.Datetime('Sunday')

    @api.depends('week_nro')
    def _calculate_wc_available_capacity_cal(self):
        for record in self:
            week = record.week_nro
            monday = datetime.strptime(week + '-1', "%Y-%W-%w")
            sunday = monday + timedelta(days = 7)
            nro_hours = record.workcenter_id.resource_calendar_id.get_work_hours_count(monday, sunday)
            record.wc_available_capacity_cal = nro_hours * record.workcenter_id.capacity * record.workcenter_id.time_efficiency / 100
            record.monday = monday
            record.sunday = sunday
        return True

    @api.depends('week_nro')
    def _get_week_number_2(self):
        for record in self:
            record.week_nro_2 = False
            monday = datetime.strptime(record.week_nro + '-1', "%Y-%W-%w") + timedelta(days=7)
            if monday:
                week = monday.date().strftime("%V")
                year = monday.date().strftime("%Y")
                record.week_nro_2 = year + "-" + week
        return True

class MrpCapacityCheckAllItem(models.TransientModel):
    _name = "mrp.capacity.check.allitem"
    _description = 'MRP Capacity Check Item'

    check_id = fields.Many2one('mrp.capacity.check', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center')
    week_nro = fields.Char('Original Week Number')
    week_nro_2 = fields.Char('Week Number', compute='_get_week_number_2')
    wo_capacity_requirements = fields.Float('WO Capacity Requirements (Hours)')
    wc_available_capacity_cal = fields.Float('WC Weekly Available Capacity', compute='_calculate_wc_available_capacity_cal', store=True)
    wc_capacity_load = fields.Float('WC Capacity Load %', compute='_get_wc_capacity')
    wc_remaining_capacity = fields.Float('WC Remaining Capacity', compute='_wc_capacity')
    indicator = fields.Boolean(default=False)


    @api.depends('week_nro')
    def _calculate_wc_available_capacity_cal(self):
        for record in self:
            week = record.week_nro
            monday = datetime.strptime(week + '-1', "%Y-%W-%w")
            sunday = monday + timedelta(days = 7)
            nro_hours = record.workcenter_id.resource_calendar_id.get_work_hours_count(monday, sunday)
            record.wc_available_capacity_cal = nro_hours * record.workcenter_id.capacity * record.workcenter_id.time_efficiency / 100
        return True

    @api.depends('wo_capacity_requirements','wc_available_capacity_cal')
    def _get_wc_capacity(self):
        for record in self:
            if record.wc_available_capacity_cal:
                record.wc_capacity_load = (record.wo_capacity_requirements / record.wc_available_capacity_cal) * 100
            else:
                record.wc_capacity_load = 0.0
            record.wc_remaining_capacity = record.wc_available_capacity_cal - record.wo_capacity_requirements
        return True

    def open_pivot_info(self):
        context={'default_workcenter_id': self.workcenter_id.id,}
        domain = [("workcenter_id", "=", self.workcenter_id.id)]
        return {
            "name": _("Workcenter Capacity Elaluations"),
            "view_mode": "pivot",
            "res_model": "mrp.workcenter.capacity",
            "type": "ir.actions.act_window",
            "context": context,
            "domain": domain,
            "target": "fullscreen",
        }

    @api.depends('week_nro')
    def _get_week_number_2(self):
        for record in self:
            record.week_nro_2 = False
            monday = datetime.strptime(record.week_nro + '-1', "%Y-%W-%w") + timedelta(days=7)
            if monday:
                week = monday.date().strftime("%V")
                year = monday.date().strftime("%Y")
                record.week_nro_2 = year + "-" + week
        return True

