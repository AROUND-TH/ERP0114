# -*- coding: utf-8 -*-
# Copyright (c) OpenValue All Rights Reserved

{
  'name': 'MRP Scheduling Engine',
  'summary': 'MRP Scheduling Engine',
  'version': '14.0.2.2',
  'category': 'Manufacturing',
  "website": 'www.openvalue.cloud',
  'author': "OpenValue",
  'support': 'info@openvalue.cloud',
  'license': 'Other proprietary',
  'price': 1200.00,
  'currency': 'EUR',
  'depends': [
        "mrp_shop_floor_control",
    ],
    'external_dependencies': {
        "python": ["docplex"],
        "python": ["cplex"],
    },
    'data': [
        "security/mrp_scheduling_engine_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/res_config_settings_views.xml",
        "wizards/mrp_scheduling_engine_run_views.xml",
        "reports/report_scheduling.xml",
        "wizards/mrp_scheduling_engine_list_views.xml",
        "reports/report_scheduling_wc.xml",
        "wizards/mrp_scheduling_engine_list_wc_views.xml",
    ],
  'application': False,
  'installable': True,
  'auto_install': False,
  'images': ['static/description/banner.png'],
}
