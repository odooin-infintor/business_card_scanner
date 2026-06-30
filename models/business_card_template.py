# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class BusinessCardTemplate(models.Model):
    _name        = 'business.card.template'
    _description = 'Business Card Template'
    _rec_name    = 'name'

    name          = fields.Char(string='Title', required=True, default='Business Card Template')
    target_model  = fields.Selection([
        ('partner', 'Partner'),
        ('lead',    'Lead'),
    ], string='Model', required=True, default='partner')
    auto_evaluate = fields.Boolean(string='Auto Evaluate', default=True,
                                   help='Automatically move card to the target model on save.')
    mapping_ids   = fields.One2many(
        'business.card.field.mapping', 'template_id', string='Field Mapping'
    )
    active        = fields.Boolean(default=True)
    notes         = fields.Text(string='Notes')

    @api.model
    def get_default_template(self):
        return self.search([('active', '=', True)], order='id asc', limit=1)


class BusinessCardFieldMapping(models.Model):
    _name        = 'business.card.field.mapping'
    _description = 'Business Card Field Mapping'
    _order       = 'sequence, id'

    template_id  = fields.Many2one('business.card.template', string='Template',
                                   required=True, ondelete='cascade')
    sequence     = fields.Integer(default=10)
    card_field   = fields.Selection([
        ('contact_name', 'Full Name'),
        ('job_title',    'Job Title'),
        ('company_name', 'Company'),
        ('email',        'Email'),
        ('phone',        'Phone'),
        ('mobile',       'Mobile'),
        ('website',      'Website'),
        ('street',       'Street'),
        ('city',         'City'),
        ('zip_code',     'ZIP'),
    ], string='Card Field', required=True)
    partner_field = fields.Char(
        string='Partner Field',
        help='Technical field name on res.partner (e.g. name, function, email)',
    )
    lead_field    = fields.Char(
        string='Lead Field',
        help='Technical field name on crm.lead (e.g. contact_name, job_position, email_from)',
    )