# -*- coding: utf-8 -*-

from . import models
from . import wizards
from odoo import api, SUPERUSER_ID


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['mrp.floating.times'].create_floating_times()




