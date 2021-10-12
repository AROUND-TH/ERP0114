# -*- coding: utf-8 -*-


from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'


    fail_limit = fields.Integer('Solver Failures Limit', default=1000, required=True)
    time_limit = fields.Float('Solver Elapsed Time Limit', default=10, required=True)
    scheduling_horizon = fields.Integer('Scheduling Horizon (days)', required=True, default=14)

    @api.constrains('fail_limit', 'time_limit', 'scheduling_horizon')
    def _check_values(self):
        if self.fail_limit <= 0:
            raise UserError(_('Negative values for Solver Failures Limit are not allowed'))
        if self.time_limit <= 0:
            raise UserError(_('Negative values for Solver Failures Limit are not allowed'))
        if self.scheduling_horizon <= 0:
            raise UserError(_('Negative values for Scheduling Horizon are not allowed'))
        return True


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"


    fail_limit = fields.Integer('Solver Failures Limit', related="company_id.fail_limit", readonly=False, required=True)
    time_limit = fields.Float('Solver Elapsed Time Limit', related="company_id.time_limit", readonly=False, required=True)
    scheduling_horizon = fields.Integer('Scheduling Horizon (days)', related="company_id.scheduling_horizon", readonly=False, required=True)
