# -*- coding: utf-8 -*-
import base64
import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class BusinessCardController(http.Controller):

    @http.route('/business_card/upload', type='http', auth='user', methods=['POST'], csrf=True)
    def upload_card(self, **kwargs):
        """Handle card image upload from the frontend scanner widget."""
        try:
            image_file = kwargs.get('card_image')
            scan_id = kwargs.get('scan_id')

            if not image_file:
                return json.dumps({'success': False, 'error': 'No image provided'})

            image_data = base64.b64encode(image_file.read()).decode('utf-8')

            if scan_id:
                scan = request.env['business.card.scan'].browse(int(scan_id))
                scan.write({
                    'card_image': image_data,
                    'card_image_filename': image_file.filename,
                })
            else:
                scan = request.env['business.card.scan'].create({
                    'card_image': image_data,
                    'card_image_filename': getattr(image_file, 'filename', 'card.jpg'),
                    'scan_source': 'upload',
                })

            return json.dumps({'success': True, 'scan_id': scan.id})

        except Exception as e:
            _logger.error('Card upload error: %s', str(e))
            return json.dumps({'success': False, 'error': str(e)})

    @http.route('/business_card/ocr/<int:scan_id>', type='json', auth='user', methods=['POST'])
    def run_ocr(self, scan_id, **kwargs):
        """Run OCR on an existing scan record."""
        try:
            scan = request.env['business.card.scan'].browse(scan_id)
            if not scan.exists():
                return {'success': False, 'error': 'Scan not found'}
            scan.action_extract_text()
            return {
                'success': True,
                'data': {
                    'name': scan.contact_name,
                    'job_title': scan.job_title,
                    'company': scan.company_name,
                    'email': scan.email,
                    'phone': scan.phone,
                    'mobile': scan.mobile,
                    'website': scan.website,
                    'street': scan.street,
                    'city': scan.city,
                    'zip_code': scan.zip_code,
                    'raw_text': scan.raw_text,
                }
            }
        except Exception as e:
            _logger.error('OCR error: %s', str(e))
            return {'success': False, 'error': str(e)}
