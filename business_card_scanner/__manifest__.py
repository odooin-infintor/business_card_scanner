# -*- coding: utf-8 -*-
{
    'name': 'Odoo AI Business Card Scanner',
    'version': '19.0.1.1.0',
    'category': 'Contacts',
    'summary': 'Scan business cards and save contacts to Odoo',
    'description': """
    Business Card Scanner
    =====================
    Scan business cards using your camera or upload images.
    Automatically extracts contact information and saves to Odoo Contacts.

    Features:
        - Camera capture / image upload
        - AI-powered text extraction (OCR) via OpenAI GPT-4o or Google Gemini
        - Auto-fill contact fields (name, phone, email, company, address, website)
        - Preview & edit before saving
        - Save to a dedicated Business Card Scan master record (not saved directly to res.partner)
        - Option to convert/save scanned record to a Contact (res.partner) or a Lead (crm.lead)
        - Clean scan history (all scanned records appear in All Scans list, regardless of conversion status)
    """,

    # --- Company / legal info ---
    'author': 'Infintor Solutions',
    'company': 'Infintor Solutions',
    'maintainer': 'Infintor Solutions',
    'website': 'https://www.infintor.com',
    'support': 'support@infintor.com',

    # --- Live demo (strongly recommended, sometimes required) ---
    # 'live_test_url': 'https://demo.yourcompany.com/odoo',

    # --- Licensing & pricing ---
    # Use 'OPL-1' instead of 'LGPL-3' if you plan to SELL this app.
    # LGPL-3 allows free redistribution - not compatible with paid listings.
    'license': 'Other proprietary',
    'price': 188.00,
    'currency': 'USD',

    'images': ['static/description/banner.png'],
    'depends': ['contacts', 'base', 'crm'],
    'data': [
        'security/ir.model.access.csv',

        'data/sequences.xml',
        'data/business_card_template_data.xml',

        'views/business_card_scan_views.xml',
        'views/business_card_contact_views.xml',
        'views/business_card_template_views.xml',
        'views/res_partner_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'business_card_scanner/static/src/css/scanner.css',
            'business_card_scanner/static/src/js/card_scanner.js',
            'business_card_scanner/static/src/xml/card_scanner_templates.xml',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}