# -*- coding: utf-8 -*-
"""
Test suite for extraction logging mechanism

This test ensures that EVERY AI call is logged accurately with:
- Input file (attachment)
- AI response JSON (if succeeded)
- Exact status (success/error)
- Detailed error messages

Test scenarios:
1. Success case: AI extraction succeeds
2. Validation failures: Invalid file type, size, format
3. AI extraction failure: Gemini API error
4. Attachment creation failure
5. Log save failure
6. Unexpected exceptions
"""

from odoo.tests.common import TransactionCase
from unittest.mock import patch, MagicMock
import base64


class TestExtractionLogging(TransactionCase):
    """Test extraction logging mechanism"""

    def setUp(self):
        super().setUp()
        self.controller = self.env['ir.http']._get_controller_class('extract_document')

        # Sample valid PDF binary (minimal PDF structure)
        self.valid_pdf = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 1\ntrailer\n<<\n>>\n%%EOF'

    def test_01_success_case(self):
        """Test successful extraction with complete logging"""
        # Mock AI extraction service
        with patch.object(self.env['document.extraction.service'], 'extract_pdf') as mock_extract:
            mock_extract.return_value = {
                'year': 2024,
                'organization_name': 'Test Company',
            }

            # Call extraction
            result = self.controller._process_pdf_extraction(
                pdf_binary=self.valid_pdf,
                filename='test.pdf',
                document_type='01',
                run_ocr=False
            )

            # Verify success
            self.assertTrue(result['success'])
            self.assertIsNotNone(result['extracted_data'])
            self.assertIsNotNone(result['attachment'])
            self.assertIsNotNone(result['log'])

            # Verify log
            log = result['log']
            self.assertEqual(log.status, 'success')
            self.assertIsNotNone(log.attachment_id)
            self.assertIsNotNone(log.ai_response_json)
            self.assertEqual(log.file_name, 'test.pdf')
            self.assertEqual(log.document_type, '01')

    def test_02_invalid_file_type(self):
        """Test invalid file extension"""
        result = self.controller._process_pdf_extraction(
            pdf_binary=b'fake data',
            filename='test.txt',
            document_type='01',
            run_ocr=False
        )

        # Verify failure
        self.assertFalse(result['success'])
        self.assertIsNone(result['attachment'])
        self.assertIsNotNone(result['log'])

        # Verify log
        log = result['log']
        self.assertEqual(log.status, 'error')
        self.assertIn('Invalid file type', log.error_message)

    def test_03_file_too_large(self):
        """Test file size exceeds limit"""
        large_pdf = b'%PDF' + b'x' * (51 * 1024 * 1024)  # 51MB

        result = self.controller._process_pdf_extraction(
            pdf_binary=large_pdf,
            filename='large.pdf',
            document_type='01',
            run_ocr=False
        )

        # Verify failure
        self.assertFalse(result['success'])
        self.assertIsNone(result['attachment'])
        self.assertIsNotNone(result['log'])

        # Verify log
        log = result['log']
        self.assertEqual(log.status, 'error')
        self.assertIn('too large', log.error_message)

    def test_04_invalid_pdf_format(self):
        """Test invalid PDF magic bytes"""
        result = self.controller._process_pdf_extraction(
            pdf_binary=b'not a pdf',
            filename='fake.pdf',
            document_type='01',
            run_ocr=False
        )

        # Verify failure
        self.assertFalse(result['success'])
        self.assertIsNone(result['attachment'])
        self.assertIsNotNone(result['log'])

        # Verify log
        log = result['log']
        self.assertEqual(log.status, 'error')
        self.assertIn('Invalid PDF format', log.error_message)

    def test_05_ai_extraction_failure(self):
        """Test AI extraction raises exception"""
        # Mock AI extraction to raise error
        with patch.object(self.env['document.extraction.service'], 'extract_pdf') as mock_extract:
            mock_extract.side_effect = Exception('Gemini API error: Rate limit exceeded')

            result = self.controller._process_pdf_extraction(
                pdf_binary=self.valid_pdf,
                filename='test.pdf',
                document_type='01',
                run_ocr=False
            )

            # Verify failure
            self.assertFalse(result['success'])
            self.assertIsNone(result['extracted_data'])

            # CRITICAL: Verify attachment was created BEFORE AI call
            self.assertIsNotNone(result['attachment'],
                                "Attachment should exist even when AI fails")

            # Verify log
            log = result['log']
            self.assertEqual(log.status, 'error')
            self.assertIn('AI extraction failed', log.error_message)
            self.assertIsNotNone(log.attachment_id,
                                "Log should have attachment_id even when AI fails")
            self.assertIn('Gemini API error', log.ai_response_json,
                         "Log should contain full error traceback")

    def test_06_attachment_creation_failure(self):
        """Test attachment creation raises exception"""
        # Mock attachment creation to fail
        with patch.object(self.env['ir.attachment'], 'create') as mock_create:
            mock_create.side_effect = Exception('Database connection error')

            result = self.controller._process_pdf_extraction(
                pdf_binary=self.valid_pdf,
                filename='test.pdf',
                document_type='01',
                run_ocr=False
            )

            # Verify failure
            self.assertFalse(result['success'])
            self.assertIsNone(result['attachment'])

            # Verify log exists and has error status
            log = result['log']
            self.assertEqual(log.status, 'error')
            self.assertIn('Failed to create attachment', log.error_message)

    def test_07_log_save_failure(self):
        """Test log.write() raises exception after successful extraction"""
        # Mock successful AI extraction
        with patch.object(self.env['document.extraction.service'], 'extract_pdf') as mock_extract:
            mock_extract.return_value = {'year': 2024}

            # Mock log.write() to fail on success update
            original_write = self.env['google.drive.extraction.log'].write
            call_count = [0]

            def failing_write(vals):
                call_count[0] += 1
                # Fail on the 3rd write (success update)
                if call_count[0] >= 3:
                    raise Exception('Database write error')
                return original_write(vals)

            with patch.object(self.env['google.drive.extraction.log'], 'write', side_effect=failing_write):
                result = self.controller._process_pdf_extraction(
                    pdf_binary=self.valid_pdf,
                    filename='test.pdf',
                    document_type='01',
                    run_ocr=False
                )

                # Verify extraction succeeded but save failed
                self.assertFalse(result['success'])
                self.assertIsNotNone(result['extracted_data'],
                                    "Extracted data should exist even if log save fails")
                self.assertIsNotNone(result['attachment'])
                self.assertIn('Save Failed', result['error']['title'])

    def test_08_unexpected_exception(self):
        """Test unexpected exception in pipeline"""
        # Mock an unexpected error during year calculation
        with patch.object(self.env['document.extraction.service'], 'extract_pdf') as mock_extract:
            mock_extract.return_value = {'year': 'invalid'}  # This will cause error in year calculation

            # This should be caught by the catch-all exception handler
            result = self.controller._process_pdf_extraction(
                pdf_binary=self.valid_pdf,
                filename='test.pdf',
                document_type='01',
                run_ocr=False
            )

            # Even with unexpected error, log should exist
            self.assertIsNotNone(result['log'])

    def test_09_verify_log_always_has_attachment_after_validation(self):
        """
        CRITICAL TEST: Verify that once validation passes,
        the log ALWAYS has an attachment, regardless of AI success/failure
        """
        test_cases = [
            ('AI success', lambda: {'year': 2024}, True),
            ('AI failure', lambda: Exception('AI error'), False),
        ]

        for case_name, ai_behavior, should_succeed in test_cases:
            with self.subTest(case=case_name):
                # Setup mock
                with patch.object(self.env['document.extraction.service'], 'extract_pdf') as mock_extract:
                    if should_succeed:
                        mock_extract.return_value = ai_behavior()
                    else:
                        mock_extract.side_effect = ai_behavior()

                    result = self.controller._process_pdf_extraction(
                        pdf_binary=self.valid_pdf,
                        filename=f'test_{case_name}.pdf',
                        document_type='01',
                        run_ocr=False
                    )

                    # CRITICAL ASSERTION: Log must have attachment
                    self.assertIsNotNone(result['log'],
                                       f"[{case_name}] Log should always exist")
                    self.assertIsNotNone(result['log'].attachment_id,
                                       f"[{case_name}] Log should always have attachment_id after validation")
                    self.assertIsNotNone(result['attachment'],
                                       f"[{case_name}] Attachment should always exist after validation")
