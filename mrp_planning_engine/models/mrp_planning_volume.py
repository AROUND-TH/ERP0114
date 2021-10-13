# -*- coding: utf-8 -*-


from odoo import api, fields, models, _


class MrpPlanningVolume(models.Model):
    _name = "mrp.planning.volume"
    _description = "MRP Planning Volume"
    _order = "sequence"

    sequence = fields.Integer('Planning Sequence', default=10, required=True)
    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse')


    _sql_constraints = [("sequence_uniq", "unique(sequence)", "The planning sequence must be unique.",)]

