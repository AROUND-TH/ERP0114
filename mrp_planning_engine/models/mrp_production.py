# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.osv.expression import AND


class MrpProduction(models.Model):
    _inherit = 'mrp.production'


    def action_confirm(self):
        if not self.move_raw_ids:
            moves_raw_values = self._get_moves_raw_values()
            list_move_raw = []
            for move_raw_values in moves_raw_values:
                list_move_raw += [(0,_,move_raw_values)]
            self.move_raw_ids = list_move_raw
            self.move_raw_ids.write({
                'group_id': self.procurement_group_id.id,
                'reference': self.name,
            })
        if not self.move_finished_ids:
            move_finished_values = self._get_moves_finished_values()
            list_move_finished = []
            for move_finished_value in move_finished_values:
                list_move_finished += [(0,_,move_finished_value)]
            self.move_finished_ids = list_move_finished
            self.move_finished_ids.write({
                'group_id': self.procurement_group_id.id,
                'reference': self.name,
            })
        if not self.workorder_ids:
            self._create_workorder()
        return super().action_confirm()


class MrpBom(models.Model):
    _inherit = 'mrp.bom'


    def _bom_subcontract_find(self, product_tmpl=None, product=None, picking_type=None, company_id=False, bom_type='subcontract', subcontractor=False):
        domain = self._bom_find_domain(product_tmpl=product_tmpl, product=product, picking_type=None, company_id=company_id, bom_type=bom_type)
        if subcontractor:
            domain = AND([domain, [('subcontractor_ids', 'parent_of', subcontractor.ids)]])
            return self.search(domain, order='sequence, product_id', limit=1)
        else:
            return self.env['mrp.bom']
