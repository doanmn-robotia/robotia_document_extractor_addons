# -*- coding: utf-8 -*-

from odoo import models, api
import re
import logging

_logger = logging.getLogger(__name__)


class FuzzyMatcher(models.AbstractModel):
    """
    Common fuzzy matching utilities for controlled substances and other master data.
    Provides normalization and multi-strategy search capabilities.
    """
    _name = 'fuzzy.matcher'
    _description = 'Fuzzy Matching Utilities'

    @api.model
    def normalize_hs_code(self, hs_code_text):
        """
        Normalize HS code to standard 8-digit format.

        Handles various input formats:
        - "2903.45.00" -> "29034500"
        - "2903-45-00" -> "29034500"
        - "290345" -> "29034500" (pads with 00)
        - "2903.45" -> "29034500"

        Args:
            hs_code_text (str): HS code in any format

        Returns:
            str: Normalized 8-digit HS code, or empty string if invalid
        """
        if not hs_code_text:
            return ''

        # Remove dots, dashes, spaces
        cleaned = re.sub(r'[.\-\s]', '', str(hs_code_text).strip())

        # Keep only digits
        digits_only = re.sub(r'\D', '', cleaned)

        if not digits_only:
            return ''

        # Pad to 8 digits if shorter (e.g., "290345" -> "29034500")
        if len(digits_only) < 8:
            digits_only = digits_only.ljust(8, '0')

        # Truncate to 8 digits if longer
        return digits_only[:8]

    @api.model
    def normalize_substance_code(self, code_text):
        """
        Normalize substance code for fuzzy matching.

        Handles various input formats:
        - "R-134a" -> "r134a"
        - "R 134a" -> "r134a"
        - "HFC-134a" -> "hfc134a"
        - "r134a" -> "r134a"

        Args:
            code_text (str): Substance code/name in any format

        Returns:
            str: Normalized lowercase code without spaces/dashes
        """
        if not code_text:
            return ''

        # Remove spaces, dashes, underscores
        cleaned = re.sub(r'[\s\-_]', '', str(code_text).strip())

        # Convert to lowercase for case-insensitive matching
        return cleaned.lower()

    @api.model
    def search_substance_fuzzy(self, search_term, hs_code_term=None):
        """
        Multi-strategy fuzzy search for controlled substance.

        Search strategies (in priority order):
        1. Exact match (name or code)
        2. Normalized code match (ignoring spaces/dashes/case)
        3. HS code exact match (if hs_code_term provided)
        4. HS code prefix match (if hs_code_term provided)
        5. Partial ILIKE match on name/code

        Args:
            search_term (str): Substance name or code from AI extraction
            hs_code_term (str, optional): HS code from AI extraction (bảng 2.1)

        Returns:
            recordset: controlled.substance records (may be empty)
        """
        if not search_term and not hs_code_term:
            return self.env['controlled.substance']

        search_term = search_term.strip()
        _logger.debug(f"Fuzzy search: term='{search_term}', hs_code='{hs_code_term}'")

        # Strategy 1: Exact match on name or code
        exact_match = self.env['controlled.substance'].search([
            '|',
            ('name', '=', search_term),
            ('code', '=', search_term),
        ], limit=1)

        if exact_match:
            _logger.info(f"Exact match found: '{search_term}' -> {exact_match.name}")
            return exact_match

        # Strategy 2: Normalized code match (case-insensitive, no spaces/dashes)
        normalized_search = self.normalize_substance_code(search_term)

        # Get all substances and check normalized codes
        all_substances = self.env['controlled.substance'].search([
            '|',
            ('active', '=', True),
            ('active', '=', False)
        ])

        for substance in all_substances:
            # Check normalized name
            if self.normalize_substance_code(substance.name) == normalized_search:
                _logger.info(f"Normalized name match: '{search_term}' -> {substance.name}")
                return substance

            # Check normalized code
            if substance.code and self.normalize_substance_code(substance.code) == normalized_search:
                _logger.info(f"Normalized code match: '{search_term}' -> {substance.name} (code={substance.code})")
                return substance

        # Strategy 3 & 4: HS code matching (if provided)
        if hs_code_term:
            normalized_hs = self.normalize_hs_code(hs_code_term)

            if normalized_hs:
                # Strategy 3: Exact HS code match
                # Priority 1: Match primary HS code
                hs_exact_match = self.env['controlled.substance'].search([
                    ('hs_code_id.code', '=', normalized_hs)
                ], limit=1)

                if hs_exact_match:
                    _logger.info(f"HS code exact match (primary): hs='{hs_code_term}' -> {hs_exact_match.name}")
                    return hs_exact_match

                # Priority 2: Match alternative HS codes
                hs_alt_match = self.env['controlled.substance'].search([
                    ('sub_hs_code_ids.code', '=', normalized_hs)
                ], limit=1)

                if hs_alt_match:
                    _logger.info(f"HS code exact match (alternative): hs='{hs_code_term}' -> {hs_alt_match.name}")
                    return hs_alt_match

                # Strategy 4: HS code prefix match (first 6 digits)
                if len(normalized_hs) >= 6:
                    hs_prefix = normalized_hs[:6]
                    # Priority 1: Match primary HS code prefix
                    hs_prefix_match = self.env['controlled.substance'].search([
                        ('hs_code_id.code', '=ilike', f'{hs_prefix}%')
                    ], limit=1)

                    if hs_prefix_match:
                        _logger.info(f"HS code prefix match (primary): hs='{hs_code_term}' -> {hs_prefix_match.name}")
                        return hs_prefix_match

                    # Priority 2: Match alternative HS code prefix
                    hs_alt_prefix_match = self.env['controlled.substance'].search([
                        ('sub_hs_code_ids.code', '=ilike', f'{hs_prefix}%')
                    ], limit=1)

                    if hs_alt_prefix_match:
                        _logger.info(f"HS code prefix match (alternative): hs='{hs_code_term}' -> {hs_alt_prefix_match.name}")
                        return hs_alt_prefix_match

        # Strategy 5: Partial ILIKE match (last resort)
        # Search for partial matches in name or code
        partial_match = self.env['controlled.substance'].search([
            '|',
            ('name', 'ilike', search_term),
            ('code', 'ilike', search_term)
        ], limit=1)

        if partial_match:
            _logger.info(f"Partial match found: '{search_term}' -> {partial_match.name}")
            return partial_match

        # No match found
        _logger.warning(f"No fuzzy match found for: term='{search_term}', hs_code='{hs_code_term}'")
        return self.env['controlled.substance']

    @api.model
    def search_hs_code_fuzzy(self, hs_code_text):
        """
        Fuzzy search for HS code.

        Args:
            hs_code_text (str): HS code in any format

        Returns:
            recordset: hs.code record or empty recordset
        """
        if not hs_code_text:
            return self.env['hs.code']

        normalized = self.normalize_hs_code(hs_code_text)

        if not normalized:
            return self.env['hs.code']

        # Exact match on normalized code
        exact_match = self.env['hs.code'].search([
            ('code', '=', normalized)
        ], limit=1)

        if exact_match:
            return exact_match

        # Prefix match (first 6 digits)
        if len(normalized) >= 6:
            prefix = normalized[:6]
            prefix_match = self.env['hs.code'].search([
                ('code', '=ilike', f'{prefix}%')
            ], limit=1)

            if prefix_match:
                return prefix_match

        return self.env['hs.code']

    @api.model
    def search_country_fuzzy(self, search_term):
        """
        Fuzzy search for country by code or name.

        IMPORTANT: This is a FALLBACK function - only call after exact search fails.

        Search strategies (in order):
        1. Case-insensitive code match: 'vn' -> 'VN'
        2. Normalized name match: 'Viet Nam' -> 'vietnam'
        3. Partial ILIKE match: 'United' -> 'United States'

        Args:
            search_term (str): Country code or name to search

        Returns:
            recordset: res.country record or empty recordset
        """
        if not search_term:
            return self.env['res.country']

        search_term = search_term.strip()
        _logger.debug(f"Fuzzy search country: '{search_term}'")

        # Strategy 1: Case-insensitive code match
        country = self.env['res.country'].search([
            ('code', '=ilike', search_term)
        ], limit=1)

        if country:
            _logger.info(f"Country fuzzy matched (code): '{search_term}' -> {country.name} ({country.code})")
            return country

        # Strategy 2: Normalized name match
        normalized_search = self.normalize_substance_code(search_term)

        all_countries = self.env['res.country'].search([])
        for country in all_countries:
            if self.normalize_substance_code(country.name) == normalized_search:
                _logger.info(f"Country fuzzy matched (normalized name): '{search_term}' -> {country.name} ({country.code})")
                return country

        # Strategy 3: Partial ILIKE match on name
        country = self.env['res.country'].search([
            ('name', 'ilike', search_term)
        ], limit=1)

        if country:
            _logger.info(f"Country fuzzy matched (partial name): '{search_term}' -> {country.name} ({country.code})")
            return country

        _logger.warning(f"Country fuzzy search failed: '{search_term}'")
        return self.env['res.country']

    @api.model
    def search_state_fuzzy(self, search_term, country_id=None):
        """
        Fuzzy search for state/province by code or name.

        IMPORTANT: This is a FALLBACK function - only call after exact search fails.

        Search strategies (in order):
        1. Case-insensitive code match (within country if provided)
        2. Normalized name match
        3. Partial ILIKE match on name

        Args:
            search_term (str): State code or name to search
            country_id (int, optional): Country ID to restrict search

        Returns:
            recordset: res.country.state record or empty recordset
        """
        if not search_term:
            return self.env['res.country.state']

        search_term = search_term.strip()
        _logger.debug(f"Fuzzy search state: '{search_term}', country_id={country_id}")

        # Build domain with optional country filter
        base_domain = [('country_id', '=', country_id)] if country_id else []

        # Strategy 1: Case-insensitive code match
        domain = base_domain + [('code', '=ilike', search_term)]
        state = self.env['res.country.state'].search(domain, limit=1)

        if state:
            _logger.info(f"State fuzzy matched (code): '{search_term}' -> {state.name} ({state.code})")
            return state

        # Strategy 2: Normalized name match
        normalized_search = self.normalize_substance_code(search_term)

        all_states = self.env['res.country.state'].search(base_domain)
        for state in all_states:
            if self.normalize_substance_code(state.name) == normalized_search:
                _logger.info(f"State fuzzy matched (normalized name): '{search_term}' -> {state.name} ({state.code})")
                return state

        # Strategy 3: Partial ILIKE match on name
        domain = base_domain + [('name', 'ilike', search_term)]
        state = self.env['res.country.state'].search(domain, limit=1)

        if state:
            _logger.info(f"State fuzzy matched (partial name): '{search_term}' -> {state.name} ({state.code})")
            return state

        _logger.warning(f"State fuzzy search failed: '{search_term}', country_id={country_id}")
        return self.env['res.country.state']
