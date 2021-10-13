# -*- coding: utf-8 -*-


from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'


    forward_planning = fields.Boolean('Forward Planning')


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"


    forward_planning = fields.Boolean('Forward Planning', related="company_id.forward_planning", readonly=False)

