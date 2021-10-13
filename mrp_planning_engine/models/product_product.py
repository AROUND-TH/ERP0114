# -*- coding: utf-8 -*-
# Copyright (c) OpenValue All Rights Reserved


from odoo import api, fields, models, _


class ProductProduct(models.Model):
    _inherit = "product.product"


    mrp_parameter_ids = fields.One2many("mrp.parameter", "product_id", "MRP Planning parameters")
    mrp_parameter_count = fields.Integer("MRP Planning Parameter Count", readonly=True, compute="_compute_mrp_parameter_count")


    @api.depends("mrp_parameter_ids", "mrp_parameter_ids.active")
    def _compute_mrp_parameter_count(self):
        for product in self:
            if product.company_id:
                product.mrp_parameter_count = self.env['mrp.parameter'].search_count([
                    ('active', '=', True),
                    ('product_id', '=', product.id),
                    ('company_id', '=', product.company_id.id)])
            else:
                product.mrp_parameter_count = self.env['mrp.parameter'].search_count([
                    ('active', '=', True),
                    ('product_id', '=', product.id)])


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def _find_candidate(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values):
        return False

