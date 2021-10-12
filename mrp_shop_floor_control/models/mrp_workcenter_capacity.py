# -*- coding: utf-8 -*-


from odoo import models, fields, api, _
from datetime import datetime, date, timedelta



class MrpWorkCenterCapacity(models.Model):
    _name = "mrp.workcenter.capacity"
    _description = "Work Center Capacity"
    _order = "date_planned DESC"


    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center')
    workorder_id = fields.Many2one('mrp.workorder', 'WorkOrder')
    production_id = fields.Many2one("mrp.production", 'Manufacturing Order', related='workorder_id.production_id')
    product_id = fields.Many2one("product.product", "Product")
    product_qty = fields.Float("Required Quantity")
    product_uom_id = fields.Many2one('uom.uom', 'Unit of Measure')
    date_planned = fields.Datetime('Planned Date')
    week_nro = fields.Char('Week Number', compute='_get_week_number', store=True)
    active = fields.Boolean(default=True)
    wo_capacity_requirements = fields.Float('WO Capacity Requirements')
    wc_available_capacity_cal = fields.Float('WC Weekly Available Capacity', compute='_calculate_wc_available_capacity_cal', store=True, group_operator="avg")
    #wc_available_capacity_day = fields.Float('WC AV', compute='_calculate_wc_available_capacity_cal')



    @api.depends('week_nro')
    def _calculate_wc_available_capacity_cal(self):
        for record in self:
            week = record.week_nro
            monday = datetime.strptime(week + '-1', "%Y-%W-%w")
            sunday = monday + timedelta(days = 7)
            nro_hours_week = record.workcenter_id.resource_calendar_id.get_work_hours_count(monday, sunday)
            record.wc_available_capacity_cal = nro_hours_week * record.workcenter_id.capacity * record.workcenter_id.time_efficiency / 100
        return True

    @api.depends('date_planned')
    def _get_week_number(self):
        for record in self:
            week = record.date_planned.date().strftime("%V")
            year = record.date_planned.date().strftime("%Y")
            record.week_nro = year + "-" + week
        return True




