# -*- coding: utf-8 -*-

# Master Data Models
from . import controlled_substance
from . import substance_group
from . import activity_field
from . import equipment_type
from . import hs_code
from . import recycling_technology
from . import recycling_facility
from . import collection_location

# Partner Extensions
from . import res_partner

# Document Extraction
from . import document_extraction
from . import substance_usage
from . import equipment_product
from . import equipment_ownership
from . import collection_recycling
from . import quota_usage
from . import equipment_product_report
from . import equipment_ownership_report
from . import collection_recycling_report

# Services
from . import extraction_service
from . import res_config_settings
from . import google_drive_service

# Chatbot
from . import chatbot_conversation
from . import chatbot_message
from . import chatbot_service

# Aggregation Models (SQL Views)
from . import substance_aggregate
