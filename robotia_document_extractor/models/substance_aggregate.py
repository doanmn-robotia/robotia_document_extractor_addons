# -*- coding: utf-8 -*-

from odoo import models, fields, tools
import logging

_logger = logging.getLogger(__name__)


class SubstanceAggregate(models.Model):
    """
    Aggregation view for substance usage across all documents
    This is a SQL view for efficient dashboard queries
    """
    _name = 'substance.aggregate'
    _description = 'Substance Usage Aggregation'
    _auto = False
    _rec_name = 'substance_id'
    _order = 'year desc, total_usage_kg desc'

    # Dimensions
    substance_id = fields.Many2one('controlled.substance', string='Substance', readonly=True)
    year = fields.Integer(string='Year', readonly=True)
    organization_id = fields.Many2one('res.partner', string='Organization', readonly=True)
    document_type = fields.Selection([
        ('01', 'Registration (Form 01)'),
        ('02', 'Report (Form 02)')
    ], string='Document Type', readonly=True)
    usage_type = fields.Selection([
        ('production', 'Production'),
        ('import', 'Import'),
        ('export', 'Export'),
        ('equipment_manufacturing', 'Equipment Manufacturing'),
        ('equipment_operation', 'Equipment Operation'),
        ('collection', 'Collection'),
        ('reuse', 'Reuse'),
        ('recycle', 'Recycle'),
        ('disposal', 'Disposal')
    ], string='Usage Type', readonly=True)

    # Measures
    total_production_kg = fields.Float(string='Total Production (kg)', readonly=True)
    total_import_kg = fields.Float(string='Total Import (kg)', readonly=True)
    total_export_kg = fields.Float(string='Total Export (kg)', readonly=True)
    total_usage_kg = fields.Float(string='Total Usage (kg)', readonly=True)
    total_co2e = fields.Float(string='Total CO2 Equivalent (ton)', readonly=True)
    document_count = fields.Integer(string='Document Count', readonly=True)
    organization_count = fields.Integer(string='Organization Count', readonly=True)

    def init(self):
        """Create SQL view for substance aggregation"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE OR REPLACE VIEW substance_aggregate AS (
                -- From substance_usage (Form 01 - 3 years data)
                -- FIX: Calculate correct average (divide by count of non-null years, not always 3)
                SELECT
                    ROW_NUMBER() OVER () as id,
                    su.substance_id,
                    de.year,
                    de.organization_id,
                    de.document_type,
                    su.usage_type,
                    SUM(CASE WHEN su.usage_type = 'production' THEN
                        COALESCE(su.avg_quantity_kg,
                            (COALESCE(su.year_1_quantity_kg, 0) +
                             COALESCE(su.year_2_quantity_kg, 0) +
                             COALESCE(su.year_3_quantity_kg, 0)) /
                            NULLIF((CASE WHEN su.year_1_quantity_kg IS NOT NULL THEN 1 ELSE 0 END +
                                    CASE WHEN su.year_2_quantity_kg IS NOT NULL THEN 1 ELSE 0 END +
                                    CASE WHEN su.year_3_quantity_kg IS NOT NULL THEN 1 ELSE 0 END), 0)::float)
                        ELSE 0 END) as total_production_kg,
                    SUM(CASE WHEN su.usage_type = 'import' THEN
                        COALESCE(su.avg_quantity_kg,
                            (COALESCE(su.year_1_quantity_kg, 0) +
                             COALESCE(su.year_2_quantity_kg, 0) +
                             COALESCE(su.year_3_quantity_kg, 0)) /
                            NULLIF((CASE WHEN su.year_1_quantity_kg IS NOT NULL THEN 1 ELSE 0 END +
                                    CASE WHEN su.year_2_quantity_kg IS NOT NULL THEN 1 ELSE 0 END +
                                    CASE WHEN su.year_3_quantity_kg IS NOT NULL THEN 1 ELSE 0 END), 0)::float)
                        ELSE 0 END) as total_import_kg,
                    SUM(CASE WHEN su.usage_type = 'export' THEN
                        COALESCE(su.avg_quantity_kg,
                            (COALESCE(su.year_1_quantity_kg, 0) +
                             COALESCE(su.year_2_quantity_kg, 0) +
                             COALESCE(su.year_3_quantity_kg, 0)) /
                            NULLIF((CASE WHEN su.year_1_quantity_kg IS NOT NULL THEN 1 ELSE 0 END +
                                    CASE WHEN su.year_2_quantity_kg IS NOT NULL THEN 1 ELSE 0 END +
                                    CASE WHEN su.year_3_quantity_kg IS NOT NULL THEN 1 ELSE 0 END), 0)::float)
                        ELSE 0 END) as total_export_kg,
                    SUM(COALESCE(su.avg_quantity_kg,
                            (COALESCE(su.year_1_quantity_kg, 0) +
                             COALESCE(su.year_2_quantity_kg, 0) +
                             COALESCE(su.year_3_quantity_kg, 0)) /
                            NULLIF((CASE WHEN su.year_1_quantity_kg IS NOT NULL THEN 1 ELSE 0 END +
                                    CASE WHEN su.year_2_quantity_kg IS NOT NULL THEN 1 ELSE 0 END +
                                    CASE WHEN su.year_3_quantity_kg IS NOT NULL THEN 1 ELSE 0 END), 0)::float)) as total_usage_kg,
                    SUM(COALESCE(su.avg_quantity_co2,
                            (COALESCE(su.year_1_quantity_co2, 0) +
                             COALESCE(su.year_2_quantity_co2, 0) +
                             COALESCE(su.year_3_quantity_co2, 0)) /
                            NULLIF((CASE WHEN su.year_1_quantity_co2 IS NOT NULL THEN 1 ELSE 0 END +
                                    CASE WHEN su.year_2_quantity_co2 IS NOT NULL THEN 1 ELSE 0 END +
                                    CASE WHEN su.year_3_quantity_co2 IS NOT NULL THEN 1 ELSE 0 END), 0)::float)) as total_co2e,
                    COUNT(DISTINCT de.id) as document_count,
                    COUNT(DISTINCT de.organization_id) as organization_count
                FROM substance_usage su
                INNER JOIN document_extraction de ON su.document_id = de.id
                WHERE su.substance_id IS NOT NULL
                  AND su.is_title = False
                GROUP BY su.substance_id, de.year, de.organization_id, de.document_type, su.usage_type

                UNION ALL

                -- From quota_usage (Form 02 - quota allocated and used)
                SELECT
                    ROW_NUMBER() OVER () + 1000000 as id,
                    qu.substance_id,
                    de.year,
                    de.organization_id,
                    de.document_type,
                    CASE
                        WHEN qu.usage_type = 'production' THEN 'production'::text
                        WHEN qu.usage_type = 'import' THEN 'import'::text
                        WHEN qu.usage_type = 'export' THEN 'export'::text
                    END as usage_type,
                    SUM(CASE WHEN qu.usage_type = 'production' THEN qu.total_quota_kg ELSE 0 END) as total_production_kg,
                    SUM(CASE WHEN qu.usage_type = 'import' THEN qu.total_quota_kg ELSE 0 END) as total_import_kg,
                    SUM(CASE WHEN qu.usage_type = 'export' THEN qu.total_quota_kg ELSE 0 END) as total_export_kg,
                    SUM(qu.total_quota_kg) as total_usage_kg,
                    SUM(qu.total_quota_co2) as total_co2e,
                    COUNT(DISTINCT de.id) as document_count,
                    COUNT(DISTINCT de.organization_id) as organization_count
                FROM quota_usage qu
                INNER JOIN document_extraction de ON qu.document_id = de.id
                WHERE qu.substance_id IS NOT NULL
                  AND qu.is_title = False
                GROUP BY qu.substance_id, de.year, de.organization_id, de.document_type, qu.usage_type

                UNION ALL

                -- From equipment_product (Form 01 - Equipment manufacturing/import)
                SELECT
                    ROW_NUMBER() OVER () + 2000000 as id,
                    ep.substance_id,
                    de.year,
                    de.organization_id,
                    de.document_type,
                    'equipment_manufacturing'::text as usage_type,
                    0 as total_production_kg,
                    0 as total_import_kg,
                    0 as total_export_kg,
                    0 as total_usage_kg,  -- substance_quantity_per_unit is now Char (2025-12-18)
                    0 as total_co2e,  -- substance_quantity_per_unit is now Char (2025-12-18)
                    COUNT(DISTINCT de.id) as document_count,
                    COUNT(DISTINCT de.organization_id) as organization_count
                FROM equipment_product ep
                INNER JOIN document_extraction de ON ep.document_id = de.id
                LEFT JOIN controlled_substance cs ON ep.substance_id = cs.id
                WHERE ep.substance_id IS NOT NULL
                  AND ep.is_title = False
                GROUP BY ep.substance_id, de.year, de.organization_id, de.document_type

                UNION ALL

                -- From equipment_ownership (Form 01 - Equipment operation/refills)
                SELECT
                    ROW_NUMBER() OVER () + 3000000 as id,
                    eo.substance_id,
                    de.year,
                    de.organization_id,
                    de.document_type,
                    'equipment_operation'::text as usage_type,
                    0 as total_production_kg,
                    0 as total_import_kg,
                    0 as total_export_kg,
                    -- Disabled: refill fields are now Char type
                    0 as total_usage_kg,
                    0 as total_co2e,
                    COUNT(DISTINCT de.id) as document_count,
                    COUNT(DISTINCT de.organization_id) as organization_count
                FROM equipment_ownership eo
                INNER JOIN document_extraction de ON eo.document_id = de.id
                LEFT JOIN controlled_substance cs ON eo.substance_id = cs.id
                WHERE eo.substance_id IS NOT NULL
                  AND eo.is_title = False
                GROUP BY eo.substance_id, de.year, de.organization_id, de.document_type

                UNION ALL

                -- From collection_recycling (Form 01 - Collection, Reuse, Recycle, Disposal)
                SELECT
                    ROW_NUMBER() OVER () + 4000000 as id,
                    cr.substance_id,
                    de.year,
                    de.organization_id,
                    de.document_type,
                    cr.activity_type::text as usage_type,
                    0 as total_production_kg,
                    0 as total_import_kg,
                    0 as total_export_kg,
                    SUM(COALESCE(cr.quantity_kg, 0)) as total_usage_kg,
                    SUM(COALESCE(cr.quantity_co2, 0)) as total_co2e,
                    COUNT(DISTINCT de.id) as document_count,
                    COUNT(DISTINCT de.organization_id) as organization_count
                FROM collection_recycling cr
                INNER JOIN document_extraction de ON cr.document_id = de.id
                WHERE cr.substance_id IS NOT NULL
                  AND cr.is_title = False
                GROUP BY cr.substance_id, de.year, de.organization_id, de.document_type, cr.activity_type

                UNION ALL

                -- From equipment_product_report (Form 02 - Equipment manufacturing/import report)
                SELECT
                    ROW_NUMBER() OVER () + 5000000 as id,
                    epr.substance_id,
                    de.year,
                    de.organization_id,
                    de.document_type,
                    'equipment_manufacturing'::text as usage_type,
                    0 as total_production_kg,
                    0 as total_import_kg,
                    0 as total_export_kg,
                    0 as total_usage_kg,  -- substance_quantity_per_unit is now Char (2025-12-18)
                    0 as total_co2e,  -- substance_quantity_per_unit is now Char (2025-12-18)
                    COUNT(DISTINCT de.id) as document_count,
                    COUNT(DISTINCT de.organization_id) as organization_count
                FROM equipment_product_report epr
                INNER JOIN document_extraction de ON epr.document_id = de.id
                LEFT JOIN controlled_substance cs ON epr.substance_id = cs.id
                WHERE epr.substance_id IS NOT NULL
                  AND epr.is_title = False
                GROUP BY epr.substance_id, de.year, de.organization_id, de.document_type

                UNION ALL

                -- From equipment_ownership_report (Form 02 - Equipment operation report)
                SELECT
                    ROW_NUMBER() OVER () + 6000000 as id,
                    eor.substance_id,
                    de.year,
                    de.organization_id,
                    de.document_type,
                    'equipment_operation'::text as usage_type,
                    0 as total_production_kg,
                    0 as total_import_kg,
                    0 as total_export_kg,
                    -- Disabled: refill fields are now Char type
                    0 as total_usage_kg,
                    0 as total_co2e,
                    COUNT(DISTINCT de.id) as document_count,
                    COUNT(DISTINCT de.organization_id) as organization_count
                FROM equipment_ownership_report eor
                INNER JOIN document_extraction de ON eor.document_id = de.id
                LEFT JOIN controlled_substance cs ON eor.substance_id = cs.id
                WHERE eor.substance_id IS NOT NULL
                  AND eor.is_title = False
                GROUP BY eor.substance_id, de.year, de.organization_id, de.document_type

                UNION ALL

                -- From collection_recycling_report (Form 02 - Collection/Recycling report - unpivot 4 columns)
                SELECT * FROM (
                    SELECT
                        ROW_NUMBER() OVER () + 7000000 as id,
                        crr.substance_id,
                        de.year,
                        de.organization_id,
                        de.document_type,
                        'collection'::text as usage_type,
                        0 as total_production_kg,
                        0 as total_import_kg,
                        0 as total_export_kg,
                        SUM(COALESCE(crr.collection_quantity_kg, 0)) as total_usage_kg,
                        SUM(COALESCE(crr.collection_quantity_kg, 0) * COALESCE(cs.gwp, 0) / 1000.0) as total_co2e,
                        COUNT(DISTINCT de.id) as document_count,
                        COUNT(DISTINCT de.organization_id) as organization_count
                    FROM collection_recycling_report crr
                    INNER JOIN document_extraction de ON crr.document_id = de.id
                    LEFT JOIN controlled_substance cs ON crr.substance_id = cs.id
                    WHERE crr.substance_id IS NOT NULL
                      AND crr.collection_quantity_kg > 0
                    GROUP BY crr.substance_id, de.year, de.organization_id, de.document_type

                    UNION ALL

                    SELECT
                        ROW_NUMBER() OVER () + 7100000 as id,
                        crr.substance_id,
                        de.year,
                        de.organization_id,
                        de.document_type,
                        'reuse'::text as usage_type,
                        0, 0, 0,
                        SUM(COALESCE(crr.reuse_quantity_kg, 0)) as total_usage_kg,
                        SUM(COALESCE(crr.reuse_quantity_kg, 0) * COALESCE(cs.gwp, 0) / 1000.0) as total_co2e,
                        COUNT(DISTINCT de.id), COUNT(DISTINCT de.organization_id)
                    FROM collection_recycling_report crr
                    INNER JOIN document_extraction de ON crr.document_id = de.id
                    LEFT JOIN controlled_substance cs ON crr.substance_id = cs.id
                    WHERE crr.substance_id IS NOT NULL
                      AND crr.reuse_quantity_kg > 0
                    GROUP BY crr.substance_id, de.year, de.organization_id, de.document_type

                    UNION ALL

                    SELECT
                        ROW_NUMBER() OVER () + 7200000 as id,
                        crr.substance_id,
                        de.year,
                        de.organization_id,
                        de.document_type,
                        'recycle'::text as usage_type,
                        0, 0, 0,
                        SUM(COALESCE(crr.recycle_quantity_kg, 0)) as total_usage_kg,
                        SUM(COALESCE(crr.recycle_quantity_kg, 0) * COALESCE(cs.gwp, 0) / 1000.0) as total_co2e,
                        COUNT(DISTINCT de.id), COUNT(DISTINCT de.organization_id)
                    FROM collection_recycling_report crr
                    INNER JOIN document_extraction de ON crr.document_id = de.id
                    LEFT JOIN controlled_substance cs ON crr.substance_id = cs.id
                    WHERE crr.substance_id IS NOT NULL
                      AND crr.recycle_quantity_kg > 0
                    GROUP BY crr.substance_id, de.year, de.organization_id, de.document_type

                    UNION ALL

                    SELECT
                        ROW_NUMBER() OVER () + 7300000 as id,
                        crr.substance_id,
                        de.year,
                        de.organization_id,
                        de.document_type,
                        'disposal'::text as usage_type,
                        0, 0, 0,
                        SUM(COALESCE(crr.disposal_quantity_kg, 0)) as total_usage_kg,
                        SUM(COALESCE(crr.disposal_quantity_kg, 0) * COALESCE(cs.gwp, 0) / 1000.0) as total_co2e,
                        COUNT(DISTINCT de.id), COUNT(DISTINCT de.organization_id)
                    FROM collection_recycling_report crr
                    INNER JOIN document_extraction de ON crr.document_id = de.id
                    LEFT JOIN controlled_substance cs ON crr.substance_id = cs.id
                    WHERE crr.substance_id IS NOT NULL
                      AND crr.disposal_quantity_kg > 0
                    GROUP BY crr.substance_id, de.year, de.organization_id, de.document_type
                ) collection_report_unpivot
            )
        ''')

    def get_dashboard_data(self, substance_id=None, organization_id=None, year_from=None, year_to=None):
        """
        Get aggregated data for dashboards
        Returns dict with KPIs and chart data

        Returns structure matches frontend expectations:
        {
            'kpis': {
                'total_usage_kg': float,
                'total_co2e': float,
                'organization_count': int,
                'document_count': int
            },
            'charts': {
                'trend_by_year': [...],
                'top_companies': [...],
                'by_document_type': [...]
            },
            'details': {
                'organizations': [...]
            }
        }
        """
        domain = []
        if substance_id:
            domain.append(('substance_id', '=', substance_id))
        if organization_id:
            domain.append(('organization_id', '=', organization_id))
        if year_from:
            domain.append(('year', '>=', year_from))
        if year_to:
            domain.append(('year', '<=', year_to))

        records = self.search(domain)

        # Calculate KPIs
        total_kg = sum(records.mapped('total_usage_kg'))
        total_co2e = sum(records.mapped('total_co2e'))
        org_count = len(set(records.mapped('organization_id').ids))

        # Fix: Count unique documents properly using composite key
        # Since SQL view doesn't have document_id, use (year, organization_id, document_type) as proxy
        unique_docs = set()
        for record in records:
            doc_key = (record.year, record.organization_id.id if record.organization_id else 0, record.document_type)
            unique_docs.add(doc_key)
        doc_count = len(unique_docs)

        # Prepare trend chart data by year
        chart_data_by_year = {}
        for record in records:
            year = record.year
            if year not in chart_data_by_year:
                chart_data_by_year[year] = {
                    'year': year,
                    'total_kg': 0,
                    'production': 0,
                    'import': 0,
                    'export': 0
                }
            chart_data_by_year[year]['total_kg'] += record.total_usage_kg
            chart_data_by_year[year]['production'] += record.total_production_kg
            chart_data_by_year[year]['import'] += record.total_import_kg
            chart_data_by_year[year]['export'] += record.total_export_kg

        # Calculate top companies
        top_companies = {}
        for record in records:
            if record.organization_id:
                org_id = record.organization_id.id
                if org_id not in top_companies:
                    top_companies[org_id] = {
                        'organization_id': org_id,
                        'organization_name': record.organization_id.name,
                        'total_kg': 0,
                        'total_co2e': 0
                    }
                top_companies[org_id]['total_kg'] += record.total_usage_kg
                top_companies[org_id]['total_co2e'] += record.total_co2e

        top_companies_list = sorted(
            top_companies.values(),
            key=lambda x: x['total_kg'],
            reverse=True
        )[:10]  # Top 10

        # Calculate by activity type (usage_type)
        # Map to Vietnamese labels
        activity_type_labels = {
            'production': 'Sản xuất',
            'import': 'Nhập khẩu',
            'export': 'Xuất khẩu',
            'equipment_manufacturing': 'SX/NK Thiết bị',
            'equipment_operation': 'Vận hành thiết bị',
            'collection': 'Thu gom',
            'reuse': 'Tái sử dụng',
            'recycle': 'Tái chế',
            'disposal': 'Tiêu hủy'
        }

        by_activity_type = {}
        for record in records:
            if record.usage_type:
                activity = record.usage_type
                if activity not in by_activity_type:
                    by_activity_type[activity] = {
                        'activity_type': activity,
                        'activity_label': activity_type_labels.get(activity, activity.title()),
                        'total_kg': 0,
                        'total_co2e': 0
                    }
                by_activity_type[activity]['total_kg'] += record.total_usage_kg
                by_activity_type[activity]['total_co2e'] += record.total_co2e

        # Sort by total_kg descending
        by_activity_sorted = sorted(
            by_activity_type.values(),
            key=lambda x: x['total_kg'],
            reverse=True
        )

        # Get quota comparison data
        quota_comparison = self._get_quota_comparison(substance_id, organization_id, year_from, year_to)

        return {
            'kpis': {
                'total_usage_kg': total_kg or 0,  # Never return None
                'total_co2e': total_co2e or 0,
                'organization_count': org_count or 0,
                'document_count': doc_count or 0
            },
            'charts': {
                'trend_by_year': sorted(chart_data_by_year.values(), key=lambda x: x['year']),
                'top_companies': top_companies_list or [],  # Never return None
                'by_activity_type': by_activity_sorted or [],
                'quota_comparison': quota_comparison or []
            },
            'details': {
                'organizations': top_companies_list or []
            }
        }

    def _get_quota_comparison(self, substance_id=None, organization_id=None, year_from=None, year_to=None):
        """
        Get quota allocated vs used comparison by organization

        This data comes from quota_usage records (Form 02)
        Shows top 10 organizations by allocated quota

        Returns:
            list: [
                {
                    'organization_id': int,
                    'organization_name': str,
                    'allocated_quota_kg': float,
                    'used_quota_kg': float,
                    'utilization_rate': float  # used / allocated * 100
                },
                ...
            ]
        """
        QuotaUsage = self.env['quota.usage']

        # Build domain for quota_usage records
        domain = []
        if substance_id:
            domain.append(('substance_id', '=', substance_id))
        if organization_id:
            domain.append(('document_id.organization_id', '=', organization_id))
        if year_from:
            domain.append(('document_id.year', '>=', year_from))
        if year_to:
            domain.append(('document_id.year', '<=', year_to))

        # Exclude title rows
        domain.append(('is_title', '=', False))

        # Search quota usage records
        quota_records = QuotaUsage.search(domain)

        # Group by organization
        org_data = {}
        for record in quota_records:
            if record.document_id and record.document_id.organization_id:
                org_id = record.document_id.organization_id.id
                org_name = record.document_id.organization_id.name

                if org_id not in org_data:
                    org_data[org_id] = {
                        'organization_id': org_id,
                        'organization_name': org_name,
                        'allocated_quota_kg': 0,
                        'used_quota_kg': 0
                    }

                org_data[org_id]['allocated_quota_kg'] += record.allocated_quota_kg or 0
                org_data[org_id]['used_quota_kg'] += record.total_quota_kg or 0

        # Calculate utilization rate
        for org_id, data in org_data.items():
            allocated = data['allocated_quota_kg']
            used = data['used_quota_kg']
            data['utilization_rate'] = (used / allocated * 100) if allocated > 0 else 0

        # Sort by allocated quota (descending) and return top 10
        sorted_data = sorted(
            org_data.values(),
            key=lambda x: x['allocated_quota_kg'],
            reverse=True
        )[:10]

        return sorted_data

    def _get_data_by_type(self, records):
        """Group data by usage type"""
        type_data = {}
        for record in records:
            usage_type = record.usage_type
            if usage_type not in type_data:
                type_data[usage_type] = {'name': usage_type, 'value': 0}
            type_data[usage_type]['value'] += record.total_usage_kg
        return list(type_data.values())

    def _get_data_by_substance(self, records):
        """Group data by substance"""
        substance_data = {}
        for record in records:
            if record.substance_id:
                sub_id = record.substance_id.id
                if sub_id not in substance_data:
                    substance_data[sub_id] = {
                        'id': sub_id,
                        'name': record.substance_id.name,
                        'value': 0
                    }
                substance_data[sub_id]['value'] += record.total_usage_kg
        return sorted(substance_data.values(), key=lambda x: x['value'], reverse=True)[:10]  # Top 10
