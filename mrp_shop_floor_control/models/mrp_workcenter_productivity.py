# -*- coding: utf-8 -*-


from odoo import models, fields, api, _



class MrpWorkCenterProductivity(models.Model):
    _inherit = 'mrp.workcenter.productivity'


    duration = fields.Float(_('Elapsed'))

    setup_duration = fields.Float('Setup Duration')
    teardown_duration = fields.Float('Teardown Duration')
    working_duration = fields.Float('Working Duration')
    overall_duration = fields.Float('Overall Duration')







