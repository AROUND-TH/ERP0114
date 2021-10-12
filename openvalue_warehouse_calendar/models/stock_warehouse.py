# -*- coding: utf-8 -*-

from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    calendar_id = fields.Many2one('resource.calendar', 'Working Calendar')
