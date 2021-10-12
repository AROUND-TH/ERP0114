# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from datetime import datetime, date, time, timedelta


class MRPSchedulingEngineList(models.TransientModel):
    _name = 'mrp.scheduling.engine.list'
    _description = 'MRP Scheduling Engine List'

    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', required=True, domain=[('manufacture_to_resupply', '=', True)])
    item_ids = fields.One2many('mrp.scheduling.engine.list.item', 'wizard_id')


    def action_scheduling_engine_list(self):
        for list in self:
            production_ids = self.env["mrp.production"].search([
                ("picking_type_id.warehouse_id", "=", list.warehouse_id.id),
                ("state", "in", ('confirmed', 'progress', 'to_close')),
            ])
            workorder_ids = self.env["mrp.workorder"].search([
                ("production_id", "in", production_ids.ids),
                ("scheduling_sequence", ">", 0),
                ("state", "in", ('pending', 'ready')),
            ])
            for workorder in workorder_ids:
                element_item = self.env['mrp.scheduling.engine.list.item'].create({
                    'wizard_id': list.id,
                    'workorder_id': workorder.id,
                })
        return {
            'type': 'ir.actions.act_window',
            'name': _('MRP Scheduling Engine List'),
            'res_model': 'mrp.scheduling.engine.list',
            'target': 'new',
            'views': [(self.env.ref('mrp_scheduling_engine.view_mrp_scheduling_engine_list_form').id, "form")],
            'res_id': self.id,
        }

    def action_align_dates(self):
        max_date_finished = min_date_start = False
        for item in self.item_ids:
            if not item.production_id.date_planned_start_wo:
                item.production_id.button_plan()
            if item.date_scheduled_start and item.date_scheduled_start != item.date_planned_start_wo:
                item.workorder_id.write({'date_planned_start_wo': item.date_scheduled_start})
            if item.date_scheduled_finished and item.date_scheduled_finished != item.date_planned_finished_wo:
                item.workorder_id.write({'date_planned_finished_wo': item.date_scheduled_finished})
        productions = self.item_ids.mapped('production_id')
        for production in productions:
            min_date_start = min((production.workorder_ids.mapped('date_planned_start_wo')))
            max_date_finished = max(production.workorder_ids.mapped('date_planned_finished_wo'))
            production.date_planned_start_wo = min_date_start
            production.date_planned_finished_wo = max_date_finished
        return {
            'type': 'ir.actions.act_window',
            'name': _('MRP Scheduling Engine List'),
            'res_model': 'mrp.scheduling.engine.list',
            'target': 'new',
            'views': [(self.env.ref('mrp_scheduling_engine.view_mrp_scheduling_engine_list_form').id, "form")],
            'res_id': self.id,
        }


class MRPSchedulingEngineListItem(models.TransientModel):
    _name = 'mrp.scheduling.engine.list.item'
    _description = 'MRP Scheduling Engine List Item'
    _order = "workcenter_id, scheduling_sequence"


    wizard_id = fields.Many2one('mrp.scheduling.engine.list', readonly=True)
    workorder_id = fields.Many2one('mrp.workorder', 'Workorder', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Workcenter', related='workorder_id.workcenter_id', readonly=True, store=True)
    sequence = fields.Integer('Sequence', related='workorder_id.sequence', readonly=True)
    wo_state = fields.Selection(string="WO State", related='workorder_id.state', readonly=True)
    production_id = fields.Many2one('mrp.production', 'Production Order', related='workorder_id.production_id', readonly=True)
    mo_state = fields.Selection(string="MO State", related='workorder_id.production_id.state', readonly=True)
    product_id = fields.Many2one('product.product', 'Product', related='workorder_id.production_id.product_id', readonly=True)
    product_qty = fields.Float('Quantity', related='workorder_id.production_id.product_qty', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', 'UoM', related='workorder_id.production_id.product_uom_id', readonly=True)
    date_planned_start_pivot = fields.Datetime(related='workorder_id.production_id.date_planned_start_pivot', readonly=True)
    date_planned_finished_pivot = fields.Datetime(related='workorder_id.production_id.date_planned_finished_pivot', readonly=True)
    duration_expected = fields.Float(related='workorder_id.duration_expected', readonly=True)
    scheduling_date = fields.Datetime(related='workorder_id.scheduling_date')
    scheduling_sequence = fields.Integer('Scheduling Sequence', related='workorder_id.scheduling_sequence', store=True)
    date_scheduled_start = fields.Datetime(related='workorder_id.date_scheduled_start')
    date_scheduled_finished = fields.Datetime(related='workorder_id.date_scheduled_finished')
    date_planned_start_wo = fields.Datetime(related='workorder_id.date_planned_start_wo')
    date_planned_finished_wo = fields.Datetime(related='workorder_id.date_planned_finished_wo')
    expected_delay = fields.Float(related='workorder_id.expected_delay', readonly=True)
    scheduled_dates_aligned = fields.Boolean("Scheduled Dates Aligned", compute='_get_aligned_indicator')


    @api.depends('date_scheduled_start', 'date_scheduled_finished')
    def _get_aligned_indicator(self):
        for record in self:
            record.scheduled_dates_aligned = False
            if record.date_scheduled_start == record.date_planned_start_wo and record.date_scheduled_finished == record.date_planned_finished_wo:
                record.scheduled_dates_aligned = True
        return True
