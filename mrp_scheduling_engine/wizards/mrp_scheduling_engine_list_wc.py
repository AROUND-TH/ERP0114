# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from datetime import datetime, date, time, timedelta


class MRPSchedulingEngineListWC(models.TransientModel):
    _name = 'mrp.scheduling.engine.list.wc'
    _description = 'MRP Scheduling Engine List WC'

    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', required=True, domain=[('manufacture_to_resupply', '=', True)])
    workcenter_id = fields.Many2one('mrp.workcenter', 'Workcenter', required=True)
    item_ids = fields.One2many('mrp.scheduling.engine.list.item.wc', 'wizard_id')


    def action_scheduling_engine_list_wc(self):
        for list in self:
            production_ids = self.env["mrp.production"].search([
                ("picking_type_id.warehouse_id", "=", list.warehouse_id.id),
                ("state", "in", ('confirmed', 'progress', 'to_close')),
            ])
            workorder_ids = self.env["mrp.workorder"].search([
                ("production_id", "in", production_ids.ids),
                ("scheduling_sequence", ">", 0),
                ("state", "in", ('pending', 'ready')),
                ("workcenter_id", "=", list.workcenter_id.id),
            ])
            for workorder in workorder_ids:
                element_item = self.env['mrp.scheduling.engine.list.item.wc'].create({
                    'wizard_id': list.id,
                    'workorder_id': workorder.id,
                    #'workcenter_id': workorder.workcenter_id.id,
                })
        return {
            'type': 'ir.actions.act_window',
            'name': _('MRP Scheduling Engine List'),
            'res_model': 'mrp.scheduling.engine.list.wc',
            'target': 'new',
            'views': [(self.env.ref('mrp_scheduling_engine.view_mrp_scheduling_engine_list_wc_form').id, "form")],
            'res_id': self.id,
        }


class MRPSchedulingEngineListItemWC(models.TransientModel):
    _name = 'mrp.scheduling.engine.list.item.wc'
    _description = 'MRP Scheduling Engine List Item WC'
    _order = "scheduling_sequence"


    wizard_id = fields.Many2one('mrp.scheduling.engine.list.wc', readonly=True)
    workorder_id = fields.Many2one('mrp.workorder', 'Workorder', readonly=True)
    #workcenter_id = fields.Many2one('mrp.workcenter', 'Workcenter', readonly=True)
    sequence = fields.Integer('Sequence', related='workorder_id.sequence', readonly=True)
    wo_state = fields.Selection(string="WO State", related='workorder_id.state', readonly=True)
    production_id = fields.Many2one('mrp.production', 'Production Order', related='workorder_id.production_id', readonly=True)
    mo_state = fields.Selection(string="MO State", related='workorder_id.production_id.state', readonly=True)
    product_id = fields.Many2one('product.product', 'Product', related='workorder_id.production_id.product_id', readonly=True)
    product_qty = fields.Float('Quantity', related='workorder_id.production_id.product_qty', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', 'UoM', related='workorder_id.production_id.product_uom_id', readonly=True)
    #date_planned_start_pivot = fields.Datetime(related='workorder_id.production_id.date_planned_start_pivot', readonly=True)
    #date_planned_finished_pivot = fields.Datetime(related='workorder_id.production_id.date_planned_finished_pivot', readonly=True)
    duration_expected = fields.Float(related='workorder_id.duration_expected', readonly=True)
    scheduling_date = fields.Datetime(related='workorder_id.scheduling_date')
    scheduling_sequence = fields.Integer('Scheduling Sequence', related='workorder_id.scheduling_sequence', store=True)
    date_scheduled_start = fields.Datetime(related='workorder_id.date_scheduled_start')
    date_scheduled_finished = fields.Datetime(related='workorder_id.date_scheduled_finished')
    #date_planned_start_wo = fields.Datetime(related='workorder_id.date_planned_start_wo')
    #date_planned_finished_wo = fields.Datetime(related='workorder_id.date_planned_finished_wo')
    #expected_delay = fields.Float(related='workorder_id.expected_delay', readonly=True)
