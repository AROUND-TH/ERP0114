# -*- coding: utf-8 -*-
# Copyright (c) Open Value All Rights Reserved

{
    'name': 'MRP Shop Floor Control',
    'summary': 'MRP Shop Floor Control',
    'version': '14.0.6.2',
    'category': 'Manufacturing',
    'website': 'www.openvalue.cloud',
    'author': "OpenValue",
    'support': 'info@openvalue.cloud',
    'license': "Other proprietary",
    'price': 1000.00,
    'currency': 'EUR',
    'depends': [
            'mrp',
            'openvalue_warehouse_calendar',
    ],
    'demo': [],
    'data': [
        'security/mrp_workorder_confirmation_security.xml',
        'security/ir.model.access.csv',
        'views/mrp_floating_times_views.xml',
        'views/mrp_workcenter_views.xml',
        'views/mrp_routing_workcenter_views.xml',
        'views/mrp_workorder_views.xml',
        'views/mrp_workcenter_capacity_views.xml',
        'wizards/mrp_confirmation_views.xml',
        'wizards/mrp_capacity_check_views.xml',
        'views/mrp_production_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'application': False,
    'installable': True,
    'auto_install': False,
    'images': ['static/description/banner.png'],
}
