# -*- coding: utf-8 -*-
import re
import logging
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BusinessCardScan(models.TransientModel):
    _name = 'business.card.scan'
    _description = 'Business Card Scanner'
    _transient_max_hours = 24
    _rec_name = 'name'

    name = fields.Char(string='Name', default='Business Card Scan')
    card_image          = fields.Binary(string='Card Image', attachment=False)
    card_image_filename = fields.Char(string='Image Filename')
    state = fields.Selection([
        ('draft',     'Scan'),
        ('extracted', 'Review'),
        ('saved',     'Saved'),
    ], default='draft', string='Status')

    contact_name = fields.Char(string='Full Name')
    job_title    = fields.Char(string='Job Title')
    company_name = fields.Char(string='Company')
    email        = fields.Char(string='Email')
    phone        = fields.Char(string='Phone')
    mobile       = fields.Char(string='Mobile')
    website      = fields.Char(string='Website')
    street       = fields.Char(string='Street')
    city         = fields.Char(string='City')
    state_id     = fields.Many2one('res.country.state', string='State/Region')
    country_id   = fields.Many2one('res.country', string='Country')
    zip_code     = fields.Char(string='ZIP')
    raw_text     = fields.Text(string='Raw Extracted Text')
    scan_source  = fields.Selection([
        ('camera', 'Camera Capture'),
        ('upload', 'File Upload'),
    ], string='Source', default='upload')

    log_id        = fields.Many2one('business.card.scan.log', string='Scan Log', readonly=True)
    partner_id    = fields.Many2one('res.partner', string='Saved Contact', readonly=True)
    bc_contact_id = fields.Many2one('business.card.contact', string='BC Staging Contact', readonly=True)

    EMAIL_RE = re.compile(r'^[\w\.\-\+]+@[\w\-]+\.[\w\.\-]+$')

    # ── Constraints ────────────────────────────────────────────────────────

    @api.constrains('email')
    def _check_email_format(self):
        for rec in self:
            if rec.email and not self.EMAIL_RE.match(rec.email.strip()):
                raise ValidationError(_(
                    '"%s" does not look like a valid email address. '
                    'Please correct it before saving.'
                ) % rec.email)

    # ── Actions ────────────────────────────────────────────────────────────

    @api.model
    def action_new_scan(self):
        record = self.create({
            'name':        'Business Card Scan',
            'state':       'draft',
            'scan_source': 'upload',
        })
        return {
            'type':      'ir.actions.act_window',
            'name':      'Business Card Scan',
            'res_model': self._name,
            'res_id':    record.id,
            'view_mode': 'form',
            'view_id':   self.env.ref(
                'business_card_scanner.view_business_card_scan_form'
            ).id,
            'target': 'current',
        }

    def action_extract_text(self):
        self.ensure_one()
        if self.state == 'saved':
            raise UserError(_(
                'This scan has already been saved.\n\n'
                'Click "New Scan" to scan another card.'
            ))
        if not self.card_image:
            raise UserError(_(
                'No image selected.\n\n'
                'Please upload a business card image or capture one with your '
                'camera before clicking Extract Info.'
            ))
        raw_text = self._perform_ocr()
        parsed   = self._parse_card_text(raw_text)

        has_useful_data = any(
            parsed.get(key) for key in ('name', 'company', 'email', 'phone')
        )
        if not has_useful_data:
            raise UserError(_(
                'No usable contact information could be recognized on this image.\n\n'
                'Try a clearer photo with good lighting, or enter the '
                'contact details manually below.'
            ))
        self.write({
            'raw_text':      raw_text,
            'contact_name':  parsed.get('name', ''),
            'job_title':     parsed.get('job_title', ''),
            'company_name':  parsed.get('company', ''),
            'email':         parsed.get('email', ''),
            'phone':         parsed.get('phone', ''),
            'mobile':        parsed.get('mobile', ''),
            'website':       parsed.get('website', ''),
            'street':        parsed.get('street', ''),
            'city':          parsed.get('city', ''),
            'zip_code':      parsed.get('zip_code', ''),
            'state':         'extracted',
            'partner_id':    False,
            'log_id':        False,
            'bc_contact_id': False,
        })
        return {
            'type':      'ir.actions.act_window',
            'res_model': self._name,
            'res_id':    self.id,
            'view_mode': 'form',
            'target':    'current',
        }

    def action_save_contact(self):
        """Save scanned card to the BC Contacts staging master (NOT res.partner)."""
        self.ensure_one()

        if self.state == 'saved':
            raise UserError(_(
                'This card has already been saved to BC Contacts.\n\n'
                'Click "View BC Contact" to open it, or "New Scan" to scan '
                'another card.'
            ))
        if self.state != 'extracted':
            raise UserError(_(
                'Please click "Extract Info" first and review the extracted '
                'details before saving.'
            ))
        if not self.contact_name and not self.company_name:
            raise UserError(_(
                'At least a name or company name is required to save a contact.'
            ))

        staging_vals = {
            'contact_name': self.contact_name or False,
            'job_title':    self.job_title    or False,
            'company_name': self.company_name or False,
            'email':        self.email        or False,
            'phone':        self.phone        or False,
            'mobile':       self.mobile       or False,
            'website':      self.website      or False,
            'street':       self.street       or False,
            'city':         self.city         or False,
            'zip_code':     self.zip_code     or False,
            'card_image':   self.card_image   or False,
            'raw_text':     self.raw_text     or False,
            'scan_source':  self.scan_source  or 'upload',
            'state':        'pending',
            'model_type':   'partner',
        }
        if self.state_id:
            staging_vals['state_id'] = self.state_id.id
        if self.country_id:
            staging_vals['country_id'] = self.country_id.id

        staging = self.env['business.card.contact'].create(staging_vals)

        log = False
        try:
            log = self.env['business.card.scan.log'].sudo().create({
                'contact_name':  self.contact_name,
                'company_name':  self.company_name,
                'email':         self.email,
                'phone':         self.phone,
                'card_image':    self.card_image,
                'scan_source':   self.scan_source or 'upload',
                'raw_text':      self.raw_text,
                'bc_contact_id': staging.id,
                'state':         'pending',
            })
            _logger.info('BCS: scan log created — id=%s ref=%s', log.id, log.name)
        except Exception as exc:
            _logger.error('BCS: failed to create scan log: %s', exc)

        write_vals = {'bc_contact_id': staging.id, 'state': 'saved'}
        if log:
            write_vals['log_id'] = log.id
        self.write(write_vals)

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Saved to BC Feed'),
                'message': _('"%s" has been saved to the Business Card Feed for review.') % (
                    self.contact_name or self.company_name or _('Contact')
                ),
                'type':    'success',
                'sticky':  False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_reset(self):
        self.write({
            'state':         'draft',
            'card_image':    False,
            'raw_text':      False,
            'contact_name':  False,
            'job_title':     False,
            'company_name':  False,
            'email':         False,
            'phone':         False,
            'mobile':        False,
            'website':       False,
            'street':        False,
            'city':          False,
            'zip_code':      False,
            'partner_id':    False,
            'log_id':        False,
            'bc_contact_id': False,
        })
        return {
            'type':      'ir.actions.act_window',
            'res_model': self._name,
            'res_id':    self.id,
            'view_mode': 'form',
            'target':    'current',
        }

    def action_view_bc_contact(self):
        self.ensure_one()
        if not self.bc_contact_id:
            raise UserError(_('No BC Contact saved yet.'))
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'business.card.contact',
            'res_id':    self.bc_contact_id.id,
            'view_mode': 'form',
            'target':    'current',
        }

    def action_view_contact(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('No contact saved yet.'))
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id':    self.partner_id.id,
            'view_mode': 'form',
            'target':    'current',
        }

    # ── OCR — provider resolution ──────────────────────────────────────────

    def _get_gemini_key(self):
        """Resolve the Google Gemini API key from Odoo AI Settings (ai.google_key)."""
        return self.env['ir.config_parameter'].sudo().get_param('ai.google_key', '').strip()

    def _get_openai_key(self):
        """Resolve the OpenAI API key from Odoo AI Settings (ai.openai_key)."""
        return self.env['ir.config_parameter'].sudo().get_param('ai.openai_key', '').strip()

    def _get_ai_provider(self):
        """
        Return the configured AI provider.

        Auto-detect based on which API key is present:
          - Only Gemini key set  → gemini
          - Only OpenAI key set  → openai
          - Both keys set        → gemini  (Gemini preferred)
          - No keys set          → raises clear error showing both options
        """
        has_gemini = bool(self._get_gemini_key())
        has_openai = bool(self._get_openai_key())

        if has_gemini and not has_openai:
            _logger.info('BCS: auto-selected Gemini (only Gemini key found)')
            return 'gemini'
        if has_openai and not has_gemini:
            _logger.info('BCS: auto-selected OpenAI (only OpenAI key found)')
            return 'openai'
        if has_gemini and has_openai:
            _logger.info('BCS: both keys found — defaulting to Gemini')
            return 'gemini'
        return None

    def _perform_ocr(self):
        """Dispatch OCR to the correct provider based on which key is set."""
        provider = self._get_ai_provider()
        _logger.info('BCS: using provider: %s', provider)
        if provider == 'gemini':
            return self._perform_ocr_gemini()
        if provider == 'openai':
            return self._perform_ocr_openai()
        raise UserError(_(
            'No AI API key configured.\n\n'
            'Please set one of the following in Settings › AI › Providers:\n\n'
            'Google Gemini:\n'
            '  Go to Settings › AI › Providers\n'
            '  Under "Google Gemini" enter your key\n'
            '  Key starts with: AIzaSy...\n'
            '  Get it from: https://aistudio.google.com/apikey\n\n'
            'OpenAI (ChatGPT):\n'
            '  Go to Settings › AI › Providers\n'
            '  Under "ChatGPT" enter your key\n'
            '  Key starts with: sk-...\n'
            '  Get it from: https://platform.openai.com/api-keys'
        ))

    # ── OCR — Gemini (with model fallback) ──────────────────────────────────

    # Ordered list of model names to try. Google periodically renames/retires
    # models per-account/region, so we try newest-known-good first and fall
    # back down the list. Update this list if Google ships new model names.
    GEMINI_MODEL_FALLBACKS = [
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-2.0-flash-001',
        'gemini-1.5-flash',
        'gemini-1.5-flash-latest',
    ]

    def _gemini_request(self, model_name, api_key, payload):
        """Make a single Gemini generateContent request for one model name.
        Tries x-goog-api-key header first, then ?key= query param.
        Returns the requests.Response object (caller inspects status_code).
        """
        url_base = (
            f'https://generativelanguage.googleapis.com'
            f'/v1beta/models/{model_name}:generateContent'
        )
        response = None
        for req_kwargs in [
            {
                'url': url_base,
                'headers': {
                    'Content-Type':   'application/json',
                    'x-goog-api-key': api_key,
                },
            },
            {
                'url': f'{url_base}?key={api_key}',
                'headers': {'Content-Type': 'application/json'},
            },
        ]:
            response = requests.post(
                req_kwargs['url'],
                headers=req_kwargs['headers'],
                json=payload,
                timeout=30,
            )
            # Only try the next auth method if this one was rejected as
            # unauthorized; any other status (200, 400, 404, 429...) is final.
            if response.status_code not in (401, 403):
                break
        return response

    def _perform_ocr_gemini(self):
        """OCR via Google Gemini Vision, trying multiple model names in order."""
        api_key = self._get_gemini_key()
        if not api_key:
            raise UserError(_(
                'Google Gemini API Key Not Set\n\n'
                'To use Google Gemini for OCR:\n'
                '  1. Go to https://aistudio.google.com/apikey\n'
                '  2. Create an API key (starts with AIzaSy...)\n'
                '  3. In Odoo: Settings › AI › Providers\n'
                '  4. Paste the key under "Google Gemini"\n\n'
                'Alternatively, you can use OpenAI instead:\n'
                '  1. Go to https://platform.openai.com/api-keys\n'
                '  2. Create a key (starts with sk-...)\n'
                '  3. In Odoo: Settings › AI › Providers\n'
                '  4. Paste the key under "ChatGPT"'
            ))
        try:
            image_data = self.card_image
            if isinstance(image_data, bytes):
                image_data = image_data.decode('utf-8')
            mime_type = self._get_mime_type()
            payload = {
                'contents': [{'parts': [
                    {'inline_data': {'mime_type': mime_type, 'data': image_data}},
                    {'text': (
                        'Extract all text from this business card image exactly '
                        'as it appears. Return only the raw text content, one '
                        'item per line. Do not add any explanation, formatting, '
                        'or markdown.'
                    )},
                ]}],
                'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 512},
            }

            response = None
            tried_models = []
            last_404_model = None

            for model_name in self.GEMINI_MODEL_FALLBACKS:
                tried_models.append(model_name)
                response = self._gemini_request(model_name, api_key, payload)

                if response.status_code == 404:
                    # This model isn't available for this key/region — try the next one.
                    last_404_model = model_name
                    _logger.warning('BCS Gemini: model "%s" returned 404, trying next fallback', model_name)
                    continue

                # Any non-404 status (200, 400, 401, 403, 429, 5xx) is final —
                # stop trying other models, this is a "real" error or success.
                _logger.info('BCS Gemini: model "%s" responded with status %s', model_name, response.status_code)
                break
            else:
                # Every model in the fallback list returned 404.
                raise UserError(_(
                    'Google Gemini Model Not Found (404)\n\n'
                    'None of the following models are available for your API key/region:\n'
                    '  • %s\n\n'
                    'Fix:\n'
                    '  1. Run this to see which models YOUR key can access:\n'
                    '     curl "https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY"\n'
                    '  2. Update GEMINI_MODEL_FALLBACKS in the code with a model name from that list\n'
                    '  3. Ensure your Google Cloud project has the Generative Language API enabled'
                ) % '\n  • '.join(tried_models))

            if response.status_code == 200:
                try:
                    data = response.json()
                    text = data['candidates'][0]['content']['parts'][0]['text']
                    _logger.info('BCS Gemini OCR ok (model=%s): %s', tried_models[-1], text[:100])
                    return text
                except (KeyError, IndexError, ValueError) as parse_err:
                    _logger.error('BCS Gemini parse error: %s | raw: %s', parse_err, response.text[:300])
                    raise UserError(_(
                        'Google Gemini returned an unexpected response.\n\n'
                        'The image may be unreadable or the API response format changed.\n'
                        'Please try again with a clearer image.\n\n'
                        'Technical detail: %s'
                    ) % parse_err)
            elif response.status_code == 400:
                raise UserError(_(
                    'Google Gemini Bad Request (400)\n\n'
                    'The image could not be processed. Possible reasons:\n'
                    '  • Image file is corrupted or unsupported format\n'
                    '  • Image is too large (max ~20MB)\n'
                    '  • Image content was blocked by safety filters\n\n'
                    'Fix: Try a different image (JPG or PNG, clear and well-lit).'
                ))
            elif response.status_code in (401, 403):
                raise UserError(_(
                    'Google Gemini API Key Error (%s)\n\n'
                    'Your Gemini API key was rejected. Possible reasons:\n'
                    '  • The key is invalid or was deleted\n'
                    '  • The key does not have Gemini API access\n'
                    '  • The Generative Language API is not enabled\n\n'
                    'Fix:\n'
                    '  1. Go to https://aistudio.google.com/apikey\n'
                    '  2. Create a new API key (starts with AIzaSy...)\n'
                    '  3. Paste it in Settings › AI › Providers › Google Gemini\n'
                    '  4. Enable API: console.cloud.google.com → APIs & Services\n'
                    '     → Enable "Generative Language API"'
                ) % response.status_code)
            elif response.status_code == 429:
                raise UserError(_(
                    'Google Gemini Quota Exceeded (429)\n\n'
                    'Your Gemini API key has hit its usage limit. Possible reasons:\n'
                    '  • Free tier quota used up for today\n'
                    '  • Billing not enabled on your Google Cloud project\n'
                    '  • Per-minute rate limit hit — wait 1 minute and retry\n\n'
                    'Fix:\n'
                    '  1. Go to https://console.cloud.google.com\n'
                    '  2. Select your project → Billing\n'
                    '  3. Attach an active billing account\n'
                    '  4. Then get a new key from https://aistudio.google.com/apikey'
                ))
            elif response.status_code in (500, 502, 503):
                raise UserError(_(
                    'Google Gemini Server Error (%s)\n\n'
                    'Google\'s servers are temporarily unavailable.\n'
                    'This is not an issue with your key or image.\n\n'
                    'Fix: Wait a few minutes and try again.\n'
                    'Check status at: https://status.cloud.google.com'
                ) % response.status_code)
            else:
                raise UserError(_(
                    'Google Gemini Unexpected Error (%s)\n\n%s'
                ) % (response.status_code, response.text[:300]))
        except UserError:
            raise
        except requests.exceptions.Timeout:
            raise UserError(_(
                'Google Gemini Request Timed Out\n\n'
                'The request took too long to respond.\n'
                'Possible reasons:\n'
                '  • Slow internet connection\n'
                '  • Google servers under load\n\n'
                'Fix: Check your internet and try again.'
            ))
        except requests.exceptions.ConnectionError:
            raise UserError(_(
                'Cannot Connect to Google Gemini\n\n'
                'Possible reasons:\n'
                '  • No internet connection\n'
                '  • Firewall or proxy blocking the request\n'
                '  • Google API is temporarily unreachable\n\n'
                'Fix: Check your internet connection and try again.'
            ))
        except Exception as e:
            _logger.error('BCS Gemini OCR error: %s', e)
            raise UserError(_(
                'Google Gemini OCR Failed\n\n'
                'An unexpected error occurred: %s\n\n'
                'Please try again or contact support.'
            ) % e)

    # ── OCR — OpenAI ───────────────────────────────────────────────────────

    def _perform_ocr_openai(self):
        """OCR via OpenAI GPT-4o Vision."""
        api_key = self._get_openai_key()
        if not api_key:
            raise UserError(_(
                'OpenAI API Key Not Set\n\n'
                'To use OpenAI for OCR:\n'
                '  1. Go to https://platform.openai.com/api-keys\n'
                '  2. Create a secret key (starts with sk-...)\n'
                '  3. In Odoo: Settings › AI › Providers\n'
                '  4. Paste the key under "ChatGPT"\n\n'
                'Alternatively, you can use Google Gemini instead:\n'
                '  1. Go to https://aistudio.google.com/apikey\n'
                '  2. Create a key (starts with AIzaSy...)\n'
                '  3. In Odoo: Settings › AI › Providers\n'
                '  4. Paste the key under "Google Gemini"'
            ))
        try:
            image_data = self.card_image
            if isinstance(image_data, bytes):
                image_data = image_data.decode('utf-8')
            mime_type = self._get_mime_type()
            payload = {
                'model': 'gpt-4o',
                'max_tokens': 512,
                'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'image_url', 'image_url': {
                            'url':    f'data:{mime_type};base64,{image_data}',
                            'detail': 'high',
                        }},
                        {'type': 'text', 'text': (
                            'Extract all text from this business card image exactly '
                            'as it appears. Return only the raw text content, one '
                            'item per line. Do not add any explanation, formatting, '
                            'or markdown.'
                        )},
                    ],
                }],
            }
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Content-Type':  'application/json',
                    'Authorization': f'Bearer {api_key}',
                },
                json=payload,
                timeout=30,
            )
            if response.status_code == 200:
                try:
                    data = response.json()
                    text = data['choices'][0]['message']['content']
                    _logger.info('BCS OpenAI OCR ok: %s', text[:100])
                    return text
                except (KeyError, IndexError, ValueError) as parse_err:
                    _logger.error('BCS OpenAI parse error: %s | raw: %s', parse_err, response.text[:300])
                    raise UserError(_(
                        'OpenAI returned an unexpected response.\n\n'
                        'The image may be unreadable or the API response format changed.\n'
                        'Please try again with a clearer image.\n\n'
                        'Technical detail: %s'
                    ) % parse_err)
            elif response.status_code == 400:
                raise UserError(_(
                    'OpenAI Bad Request (400)\n\n'
                    'The image could not be processed. Possible reasons:\n'
                    '  • Image file is corrupted or unsupported format\n'
                    '  • Image is too large (max 20MB)\n'
                    '  • Image content was blocked by safety filters\n\n'
                    'Fix: Try a different image (JPG or PNG, clear and well-lit).'
                ))
            elif response.status_code == 401:
                raise UserError(_(
                    'OpenAI API Key Error (401 Unauthorized)\n\n'
                    'Your OpenAI API key was rejected. Possible reasons:\n'
                    '  • The key is invalid, expired, or was deleted\n'
                    '  • You copied the key incorrectly\n\n'
                    'Fix:\n'
                    '  1. Go to https://platform.openai.com/api-keys\n'
                    '  2. Create a new secret key (starts with sk-...)\n'
                    '  3. Paste it in Settings › AI › Providers › ChatGPT'
                ))
            elif response.status_code == 402:
                raise UserError(_(
                    'OpenAI Payment Required (402)\n\n'
                    'Your OpenAI account has no active credits or billing.\n\n'
                    'Fix:\n'
                    '  1. Go to https://platform.openai.com/settings/organization/billing\n'
                    '  2. Add a payment method\n'
                    '  3. Purchase API credits\n'
                    '  4. Then retry'
                ))
            elif response.status_code == 403:
                raise UserError(_(
                    'OpenAI Access Forbidden (403)\n\n'
                    'Your account does not have permission to use this model.\n\n'
                    'Possible reasons:\n'
                    '  • GPT-4o access not enabled on your account\n'
                    '  • Organization policy restriction\n\n'
                    'Fix: Check your OpenAI account plan at\n'
                    'https://platform.openai.com/account/limits'
                ))
            elif response.status_code == 429:
                raise UserError(_(
                    'OpenAI Quota / Rate Limit Exceeded (429)\n\n'
                    'Possible reasons:\n'
                    '  • Your free credits have run out\n'
                    '  • No active billing on your OpenAI account\n'
                    '  • Too many requests — wait 1 minute and retry\n\n'
                    'Fix:\n'
                    '  1. Go to https://platform.openai.com/settings/organization/billing\n'
                    '  2. Add a payment method and credits\n'
                    '  3. Then retry'
                ))
            elif response.status_code in (500, 502, 503):
                raise UserError(_(
                    'OpenAI Server Error (%s)\n\n'
                    'OpenAI servers are temporarily unavailable.\n'
                    'This is not an issue with your key or image.\n\n'
                    'Fix: Wait a few minutes and try again.\n'
                    'Check status at: https://status.openai.com'
                ) % response.status_code)
            else:
                raise UserError(_(
                    'OpenAI Unexpected Error (%s)\n\n%s'
                ) % (response.status_code, response.text[:300]))
        except UserError:
            raise
        except requests.exceptions.Timeout:
            raise UserError(_(
                'OpenAI Request Timed Out\n\n'
                'The request took too long to respond.\n'
                'Possible reasons:\n'
                '  • Slow internet connection\n'
                '  • OpenAI servers under load\n\n'
                'Fix: Check your internet and try again.'
            ))
        except requests.exceptions.ConnectionError:
            raise UserError(_(
                'Cannot Connect to OpenAI\n\n'
                'Possible reasons:\n'
                '  • No internet connection\n'
                '  • Firewall or proxy blocking the request\n'
                '  • OpenAI API is temporarily unreachable\n\n'
                'Fix: Check your internet connection and try again.'
            ))
        except Exception as e:
            _logger.error('BCS OpenAI OCR error: %s', e)
            raise UserError(_(
                'OpenAI OCR Failed\n\n'
                'An unexpected error occurred: %s\n\n'
                'Please try again or contact support.'
            ) % e)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _get_mime_type(self):
        if self.card_image_filename:
            fname = self.card_image_filename.lower()
            if fname.endswith('.png'):  return 'image/png'
            if fname.endswith('.webp'): return 'image/webp'
            if fname.endswith('.bmp'):  return 'image/bmp'
        return 'image/jpeg'

    # ── Text parser ────────────────────────────────────────────────────────

    def _parse_card_text(self, text):
        result = {}
        if not text:
            return result
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # Email
        email_pat = r'[\w\.-]+@[\w\.-]+\.\w+'
        for line in lines:
            m = re.search(email_pat, line)
            if m:
                result['email'] = m.group(0)
                break

        # Website
        web_pat = r'(https?://|www\.)\S+'
        for line in lines:
            m = re.search(web_pat, line, re.IGNORECASE)
            if m:
                result['website'] = m.group(0)
                break

        # Phone / Mobile
        phone_pat  = r'[\+\d][\d\s\-\(\)\.]{7,15}'
        mobile_kw  = ['mobile', 'mob', 'cell', 'whatsapp', 'wp', 'm:']
        phone_kw   = ['phone', 'tel', 'office', 'direct', 'p:', 't:']
        labeled_mobile = None
        labeled_phone  = None
        all_phones     = []
        for line in lines:
            line_lower = line.lower()
            for m in re.finditer(phone_pat, line):
                num = m.group(0).strip()
                num_digits = re.sub(r'\D', '', num)
                if any(re.sub(r'\D', '', p) == num_digits for p in all_phones):
                    continue
                all_phones.append(num)
                if any(kw in line_lower for kw in mobile_kw):
                    if not labeled_mobile:
                        labeled_mobile = num
                elif any(kw in line_lower for kw in phone_kw):
                    if not labeled_phone:
                        labeled_phone = num
        if labeled_phone and labeled_mobile:
            result['phone']  = labeled_phone
            result['mobile'] = labeled_mobile
        elif labeled_mobile and not labeled_phone:
            result['mobile'] = labeled_mobile
            for num in all_phones:
                if num != labeled_mobile:
                    result['phone'] = num
                    break
            if not result.get('phone'):
                result['phone'] = labeled_mobile
        elif all_phones:
            result['phone'] = all_phones[0]
            if len(all_phones) > 1:
                result['mobile'] = all_phones[1]

        # Address
        street_kw = ['ave', 'avenue', 'street', 'st.', 'road', 'rd', 'blvd',
                     'lane', 'ln', 'drive', 'dr', 'suite', 'floor', 'way',
                     'place', 'pl', 'court', 'ct', 'circle', 'cir', 'terrace']
        zip_pat = r'\b(\d{5})(?:-\d{4})?\b'
        one_liner_pat = re.compile(
            r'^(.+?\d+\s+\S+.*?),\s*([^,]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$'
        )
        address_found = False
        for line in lines:
            m = one_liner_pat.match(line.strip())
            if m:
                result['street']      = m.group(1).strip()
                result['city']        = m.group(2).strip()
                result['zip_code']    = m.group(4).strip()
                result['_state_abbr'] = m.group(3).strip()
                address_found = True
                break
        if not address_found:
            for line in lines:
                if re.search(r'\d+', line) and any(kw in line.lower() for kw in street_kw):
                    result['street'] = line
                    break
            for line in lines:
                zm = re.search(zip_pat, line)
                if zm:
                    result['zip_code'] = zm.group(1)
                    before_zip = line[:zm.start()].strip().rstrip(',').strip()
                    state_abbr_m = re.search(r',?\s*([A-Z]{2})\s*$', before_zip)
                    if state_abbr_m:
                        result['_state_abbr'] = state_abbr_m.group(1)
                        before_zip = before_zip[:state_abbr_m.start()].strip().rstrip(',').strip()
                    if before_zip and not re.search(r'\d', before_zip):
                        result['city'] = before_zip
                    break

        state_abbr = result.pop('_state_abbr', None)
        if state_abbr:
            state_rec = self.env['res.country.state'].search([
                ('code', '=', state_abbr),
            ], limit=1)
            if state_rec:
                result['state_id']   = state_rec.id
                result['country_id'] = state_rec.country_id.id

        # Name / Job Title / Company
        skip_pats  = [email_pat, web_pat, phone_pat]
        name_cands = [l for l in lines if not any(re.search(p, l) for p in skip_pats)]
        addr_vals  = {result.get('street'), result.get('city'), result.get('zip_code')}
        name_cands = [l for l in name_cands if l not in addr_vals]
        name_cands = [l for l in name_cands if not re.fullmatch(zip_pat, l.strip())]

        def _looks_like_a_name(line):
            return sum(1 for ch in line if ch.isalpha()) >= 2

        company_kw = ['ltd', 'inc', 'corp', 'llc', 'limited', 'solutions',
                      'technologies', 'services', 'group', 'company', 'co.',
                      'enterprises', 'international', 'global', 'systems',
                      'consulting', 'associates', 'industries', 'ventures',
                      'studio', 'agency', 'labs', 'works', 'digital', 'media',
                      'pro', 'tech', 'soft', 'net', 'web', 'cloud']

        def _looks_like_company(line):
            return any(kw in line.lower() for kw in company_kw)

        def _looks_like_job_title(line):
            words = line.split()
            if len(words) > 7: return False
            letters = sum(1 for ch in line if ch.isalpha())
            if letters < 3: return False
            if _looks_like_company(line): return False
            return True

        def _looks_like_person_name(line):
            words = line.split()
            if len(words) < 2 or len(words) > 5: return False
            letters = sum(1 for ch in line if ch.isalpha())
            total   = len(line.replace(' ', ''))
            if total == 0: return False
            if letters / total < 0.9: return False
            if _looks_like_company(line): return False
            return True

        usable_name_cands = [l for l in name_cands if _looks_like_a_name(l)]
        person_name = None
        for line in usable_name_cands:
            if _looks_like_person_name(line):
                person_name = line
                break
        if not person_name and usable_name_cands:
            person_name = usable_name_cands[0]
        if person_name:
            result['name'] = person_name
        if person_name and person_name in usable_name_cands:
            name_idx = usable_name_cands.index(person_name)
            for line in usable_name_cands[name_idx + 1: name_idx + 3]:
                if _looks_like_job_title(line):
                    result['job_title'] = line
                    break
        for line in usable_name_cands:
            if line in (result.get('name'), result.get('job_title')):
                continue
            if _looks_like_company(line):
                result['company'] = line
                break
        if not result.get('company'):
            for i, line in enumerate(usable_name_cands[:-1]):
                next_line = usable_name_cands[i + 1]
                combined  = f'{line} {next_line}'
                if (_looks_like_company(combined)
                        and line not in (result.get('name'), result.get('job_title'))):
                    result['company'] = combined
                    break
        if not result.get('company') and person_name in usable_name_cands:
            name_idx = usable_name_cands.index(person_name)
            for line in usable_name_cands[:name_idx]:
                words = line.split()
                if 1 <= len(words) <= 5:
                    result['company'] = line
                    break
        return result


# ===========================================================================
# Business Card Contacts — Staging Master
# ===========================================================================
class BusinessCardContact(models.Model):
    _name        = 'business.card.contact'
    _description = 'Business Card Contacts (Staging)'
    _order       = 'create_date desc'
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _rec_name    = 'contact_name'

    name = fields.Char(
        string='Reference', default='New', readonly=True, copy=False,
    )
    contact_name = fields.Char(string='Full Name', tracking=True)
    job_title    = fields.Char(string='Job Title', tracking=True)
    company_name = fields.Char(string='Company', tracking=True)
    email        = fields.Char(string='Email', tracking=True)
    phone        = fields.Char(string='Phone', tracking=True)
    mobile       = fields.Char(string='Mobile', tracking=True)
    website      = fields.Char(string='Website', tracking=True)
    street       = fields.Char(string='Street')
    city         = fields.Char(string='City')
    state_id     = fields.Many2one('res.country.state', string='State/Region')
    country_id   = fields.Many2one('res.country', string='Country')
    zip_code     = fields.Char(string='ZIP')
    card_image   = fields.Binary(string='Card Image', attachment=True)
    raw_text     = fields.Text(string='Raw Extracted Text')
    scan_source  = fields.Selection([
        ('camera', 'Camera Capture'),
        ('upload', 'File Upload'),
    ], string='Source')
    state = fields.Selection([
        ('pending', 'Pending Review'),
        ('moved',   'Moved to Contacts'),
    ], default='pending', string='Status', tracking=True)
    partner_id = fields.Many2one('res.partner', string='Linked Contact', readonly=True)
    model_type = fields.Selection([
        ('partner', 'Partner'),
        ('lead',    'Lead'),
    ], string='Model', default='partner', tracking=True)

    # ── ORM overrides ──────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') in ('New', False, ''):
                try:
                    ref = self.env['ir.sequence'].next_by_code('business.card.contact')
                    vals['name'] = ref or 'BCC-%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S')
                except Exception:
                    vals['name'] = 'BCC-%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S')
        return super().create(vals_list)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _create_partner(self):
        """Create or find a res.partner from this BC contact."""
        partner_vals = {
            'name':       self.contact_name or self.company_name,
            'function':   self.job_title    or False,
            'email':      self.email        or False,
            'phone':      self.phone        or False,
            'website':    self.website      or False,
            'street':     self.street       or False,
            'city':       self.city         or False,
            'zip':        self.zip_code     or False,
            'image_1920': self.card_image   or False,
            'comment':    'Promoted from Business Card Staging on %s' % fields.Date.today(),
        }
        if self.country_id:
            partner_vals['country_id'] = self.country_id.id
        if self.state_id:
            partner_vals['state_id'] = self.state_id.id
        if self.mobile and 'mobile' in self.env['res.partner']._fields:
            partner_vals['mobile'] = self.mobile

        if self.company_name and self.company_name != self.contact_name:
            company = self.env['res.partner'].search([
                ('name', 'ilike', self.company_name),
                ('is_company', '=', True),
            ], limit=1)
            if not company:
                company = self.env['res.partner'].create({
                    'name':       self.company_name,
                    'is_company': True,
                })
            partner_vals['parent_id'] = company.id
            partner_vals['type']      = 'contact'

        return self.env['res.partner'].create(partner_vals)

    def _move_to_partner(self):
        """Create a res.partner and open it."""
        partner = self._create_partner()
        self.write({'state': 'moved', 'partner_id': partner.id, 'model_type': 'partner'})

        log = self.env['business.card.scan.log'].search(
            [('bc_contact_id', '=', self.id)], limit=1
        )
        if log:
            log.sudo().write({'partner_id': partner.id, 'state': 'moved'})

        return {
            'type':      'ir.actions.act_window',
            'name':      'Contact',
            'res_model': 'res.partner',
            'res_id':    partner.id,
            'view_mode': 'form',
            'target':    'current',
        }

    def _move_to_lead(self):
        """Create a res.partner as the customer, then create a crm.lead linked to it."""
        if 'crm.lead' not in self.env:
            raise UserError(_(
                'CRM module is not installed.\n'
                'Please install the CRM module or change the Model to "Partner".'
            ))

        partner = self._create_partner()

        lead_vals = {
            'name':         self.contact_name or self.company_name or _('New Lead'),
            'partner_id':   partner.id,
            'contact_name': self.contact_name  or False,
            'partner_name': self.company_name  or False,
            'email_from':   self.email         or False,
            'phone':        self.phone         or False,
            'website':      self.website       or False,
            'street':       self.street        or False,
            'city':         self.city          or False,
            'zip':          self.zip_code      or False,
            'description':  self.raw_text      or False,
        }
        if self.country_id:
            lead_vals['country_id'] = self.country_id.id
        if self.state_id:
            lead_vals['state_id'] = self.state_id.id

        lead = self.env['crm.lead'].create(lead_vals)

        self.write({'state': 'moved', 'partner_id': partner.id, 'model_type': 'lead'})

        log = self.env['business.card.scan.log'].search(
            [('bc_contact_id', '=', self.id)], limit=1
        )
        if log:
            log.sudo().write({'partner_id': partner.id, 'state': 'moved'})

        return {
            'type':      'ir.actions.act_window',
            'name':      'Lead',
            'res_model': 'crm.lead',
            'res_id':    lead.id,
            'view_mode': 'form',
            'target':    'current',
        }

    # ── Actions ────────────────────────────────────────────────────────────

    def action_move_to_contacts(self):
        """Promote this staged BC contact to res.partner or crm.lead based on model_type."""
        self.ensure_one()
        if self.state == 'moved':
            raise UserError(_('This contact has already been moved.'))
        if self.model_type == 'lead':
            return self._move_to_lead()
        return self._move_to_partner()

    def action_move_to_contacts_multi(self):
        """Bulk move — called from list view action."""
        moved = 0
        for rec in self:
            if rec.state == 'pending':
                rec.action_move_to_contacts()
                moved += 1
        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Done'),
                'message': _('%d contact(s) moved to main Contacts.') % moved,
                'type':    'success',
                'sticky':  False,
            },
        }

    def action_view_contact(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('This contact has not been moved yet.'))
        if self.model_type == 'lead' and 'crm.lead' in self.env:
            lead = self.env['crm.lead'].search(
                [('partner_id', '=', self.partner_id.id)], limit=1
            )
            if lead:
                return {
                    'type':      'ir.actions.act_window',
                    'res_model': 'crm.lead',
                    'res_id':    lead.id,
                    'view_mode': 'form',
                    'target':    'current',
                }
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id':    self.partner_id.id,
            'view_mode': 'form',
            'target':    'current',
        }


# ===========================================================================
# Permanent scan log
# ===========================================================================
class BusinessCardScanLog(models.Model):
    _name        = 'business.card.scan.log'
    _description = 'Business Card Scan History'
    _order       = 'create_date desc'
    _inherit     = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Scan Reference', default='New Scan', readonly=True, copy=False,
    )
    contact_name  = fields.Char(string='Full Name')
    company_name  = fields.Char(string='Company')
    email         = fields.Char(string='Email')
    phone         = fields.Char(string='Phone')
    card_image    = fields.Binary(string='Card Image', attachment=True)
    scan_source   = fields.Selection([
        ('camera', 'Camera Capture'),
        ('upload', 'File Upload'),
    ], string='Source')
    raw_text      = fields.Text(string='Raw Extracted Text')
    bc_contact_id = fields.Many2one('business.card.contact', string='BC Contact', readonly=True)
    partner_id    = fields.Many2one('res.partner', string='Contact', readonly=True)
    state         = fields.Selection([
        ('pending', 'Pending'),
        ('moved',   'Moved to Contacts'),
    ], default='pending', string='Status')

    # ── ORM overrides ──────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New Scan') in ('New Scan', False, ''):
                try:
                    ref = self.env['ir.sequence'].next_by_code('business.card.scan')
                    vals['name'] = ref or 'BCS-%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S')
                except Exception:
                    vals['name'] = 'BCS-%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S')
        return super().create(vals_list)

    # ── Actions ────────────────────────────────────────────────────────────

    def action_view_bc_contact(self):
        self.ensure_one()
        if not self.bc_contact_id:
            raise UserError(_('No BC Contact linked.'))
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'business.card.contact',
            'res_id':    self.bc_contact_id.id,
            'view_mode': 'form',
            'target':    'current',
        }

    def action_view_contact(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('Not yet moved to main Contacts.'))
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id':    self.partner_id.id,
            'view_mode': 'form',
            'target':    'current',
        }


# ===========================================================================
# res.partner extension
# ===========================================================================
class ResPartner(models.Model):
    _inherit = 'res.partner'

    business_card_count = fields.Integer(
        string='Business Card Count',
        compute='_compute_business_card_count',
    )

    def _compute_business_card_count(self):
        for partner in self:
            partner.business_card_count = self.env['business.card.contact'].search_count([
                ('partner_id', '=', partner.id)
            ])

    def action_open_business_card_scanner(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      'Business Card Scanner',
            'res_model': 'business.card.scan',
            'view_mode': 'form',
            'view_id':   self.env.ref(
                'business_card_scanner.view_business_card_scan_form'
            ).id,
            'target':  'new',
            'context': {'default_partner_id': self.id},
        }

    def action_view_business_card_feed(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      'Business Card Feed',
            'res_model': 'business.card.contact',
            'view_mode': 'list,form',
            'domain':    [('partner_id', '=', self.id)],
            'context':   {'default_partner_id': self.id},
        }