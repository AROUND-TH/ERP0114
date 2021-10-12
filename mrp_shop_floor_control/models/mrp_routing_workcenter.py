# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import UserError


class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'

    milestone = fields.Boolean(_('Milestone'), default=False)


    @api.constrains('milestone','sequence')
    def ckeck_milestone(self):
        for operation in self:
            other_operations = self.env['mrp.routing.workcenter'].search([('bom_id', '=', operation.bom_id.id),('id', '!=', operation.id)])
            if operation.milestone:
                milestone_sequence = operation.sequence
                if any(other_operation.sequence == milestone_sequence for other_operation in other_operations):
                    raise UserError(_('no parallel operation is allowed for milestone'))
            else:
                operation_sequence = operation.sequence
                if any(other_operation.sequence == operation_sequence and other_operation.milestone for other_operation in other_operations):
                    raise UserError(_('no parallel operation is allowed for milestone'))
