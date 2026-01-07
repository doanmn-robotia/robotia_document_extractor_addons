# -*- coding: utf-8 -*-

from odoo import models, api


class EquipmentCapacityMixin(models.AbstractModel):
    """
    Mixin for equipment models to handle capacity normalization

    Automatically populates 'capacity' field from 'cooling_capacity' and 'power_capacity'
    when capacity is empty.

    Logic:
    - If capacity is empty and has both cooling & power → capacity = "cooling/power"
    - If capacity is empty and has only cooling → capacity = cooling
    - If capacity is empty and has only power → capacity = power
    - If capacity already has value → no change
    """
    _name = 'equipment.capacity.mixin'
    _description = 'Equipment Capacity Normalization Mixin'

    def _normalize_capacity(self, vals):
        """
        Normalize capacity field from cooling_capacity and power_capacity

        Args:
            vals (dict): Values dictionary for create/write

        Returns:
            dict: Updated vals with normalized capacity
        """
        # If capacity is empty or None
        if not vals.get('capacity'):
            cooling = vals.get('cooling_capacity')
            power = vals.get('power_capacity')

            if cooling and power:
                # Both exist → combine with "/"
                vals['capacity'] = f"{cooling}/{power}"
            elif cooling:
                # Only cooling
                vals['capacity'] = cooling
            elif power:
                # Only power
                vals['capacity'] = power

        return vals

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to normalize capacity"""
        for vals in vals_list:
            vals = self._normalize_capacity(vals)
        return super(EquipmentCapacityMixin, self).create(vals_list)

    def write(self, vals):
        """Override write to normalize capacity"""
        # Normalize capacity for write operation
        # Note: For write, we only get changed fields in vals
        # If cooling or power is being updated but not capacity, we need to normalize
        if 'cooling_capacity' in vals or 'power_capacity' in vals:
            # Merge with existing record values
            merged_vals = vals.copy()

            # Get first record for reference (in batch write, normalization applies to all)
            if self:
                record = self[0]
                if 'cooling_capacity' not in merged_vals:
                    merged_vals['cooling_capacity'] = record.cooling_capacity
                if 'power_capacity' not in merged_vals:
                    merged_vals['power_capacity'] = record.power_capacity
                if 'capacity' not in merged_vals:
                    merged_vals['capacity'] = record.capacity

            # Normalize and update vals
            normalized = self._normalize_capacity(merged_vals)
            if 'capacity' in normalized:
                vals['capacity'] = normalized['capacity']
        else:
            # If capacity is being set directly, just normalize
            vals = self._normalize_capacity(vals)

        return super(EquipmentCapacityMixin, self).write(vals)
