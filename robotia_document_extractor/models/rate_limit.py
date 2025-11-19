# -*- coding: utf-8 -*-

from odoo import models, fields, api


class RateLimit(models.Model):
    """
    Rate limiting model for API endpoints
    Stores last request timestamp per user+action to prevent abuse
    """
    _name = 'rate.limit'
    _description = 'API Rate Limit'
    _rec_name = 'user_id'

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        required=True,
        index=True,
        ondelete='cascade'
    )
    action = fields.Char(
        string='Action',
        required=True,
        index=True,
        help='Action identifier (e.g., "extract_document", "export_excel")'
    )
    last_request = fields.Datetime(
        string='Last Request Time',
        required=True,
        default=fields.Datetime.now,
        help='Timestamp of last API call'
    )
    request_count = fields.Integer(
        string='Request Count',
        default=1,
        help='Number of requests in current time window'
    )

    _sql_constraints = [
        ('user_action_unique',
         'UNIQUE(user_id, action)',
         'Rate limit record must be unique per user and action')
    ]

    @api.model
    def check_rate_limit(self, user_id, action, limit_seconds=5):
        """
        Check if user can perform action based on rate limit

        Args:
            user_id (int): User ID
            action (str): Action identifier
            limit_seconds (int): Minimum seconds between requests

        Returns:
            dict: {'allowed': bool, 'wait_seconds': int, 'message': str}
        """
        now = fields.Datetime.now()

        # Search for existing rate limit record
        rate_record = self.search([
            ('user_id', '=', user_id),
            ('action', '=', action)
        ], limit=1)

        if rate_record:
            # Calculate time since last request
            time_diff = (now - rate_record.last_request).total_seconds()

            if time_diff < limit_seconds:
                # Rate limit exceeded
                wait_seconds = int(limit_seconds - time_diff) + 1
                return {
                    'allowed': False,
                    'wait_seconds': wait_seconds,
                    'message': f'Rate limit exceeded. Please wait {wait_seconds} seconds.'
                }

            # Update last request time
            rate_record.write({
                'last_request': now,
                'request_count': rate_record.request_count + 1
            })
        else:
            # Create new rate limit record
            self.create({
                'user_id': user_id,
                'action': action,
                'last_request': now,
                'request_count': 1
            })

        return {
            'allowed': True,
            'wait_seconds': 0,
            'message': 'OK'
        }

    @api.model
    def cleanup_old_records(self, days=30):
        """
        Cleanup rate limit records older than N days
        Should be called by scheduled action (cron)

        Args:
            days (int): Delete records older than this many days
        """
        cutoff_date = fields.Datetime.now() - fields.timedelta(days=days)
        old_records = self.search([('last_request', '<', cutoff_date)])
        count = len(old_records)
        old_records.unlink()
        return count
