# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'


    hours_uom = fields.Many2one('uom.uom', 'Hours', compute="_get_uom_hours")
    partial_confirmation = fields.Boolean('Partial Confirmation allowed', default=True)
    start_without_stock = fields.Boolean('WO Start w/out Components Availability', default=False)
    doc_count = fields.Integer("Number of attached documents", compute='_compute_attached_docs_count')


    def _get_first_available_slot(self, start_datetime, duration):
        from_date = start_datetime
        to_date = start_datetime + timedelta(minutes=duration)
        return from_date, to_date

    @api.constrains('name', 'code')
    def check_unique(self):
        wc_name = self.env['mrp.workcenter'].search([('name', '=', self.name)])
        if len(wc_name) > 1:
            raise UserError(_("Workcenter Name already exists"))
        if self.code:
            wc_code = self.env['mrp.workcenter'].search([('code', '=', self.code)])
            if len(wc_code) > 1:
                raise UserError(_("Workcenter Code already exists"))
        return True

    def _get_uom_hours(self):
        uom = self.env.ref('uom.product_uom_hour', raise_if_not_found=False)
        for record in self:
            if uom:
                record.hours_uom = uom.id
        return True

    def _compute_attached_docs_count(self):
        attachment = self.env['ir.attachment']
        for workcenter in self:
            workcenter.doc_count = attachment.search_count(['&',('res_model', '=', 'mrp.workcenter'), ('res_id', '=', workcenter.id)])

    def attachment_tree_view(self):
        self.ensure_one()
        domain = ['&', ('res_model', '=', 'mrp.workcenter'), ('res_id', 'in', self.ids)]
        return {
            'name': _('Attachments'),
            'domain': domain,
            'res_model': 'ir.attachment',
            'view_id': False,
            'view_mode': 'kanban,tree,form',
            'type': 'ir.actions.act_window',
            'limit': 80,
            'context': "{'default_res_model': '%s','default_res_id': %d}" % (self._name, self.id)
        }

