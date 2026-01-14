# HFC Export Performance Optimization Plan
**Date**: 2026-01-12
**Target**: `_collect_export_data()` function in `extraction_controller.py`
**Goal**: Reduce export time from O(N×M) queries to O(1) constant queries

---

## 📊 PHASE 1: CURRENT STATE ANALYSIS

### Current Implementation Overview
**File**: `robotia_document_extractor/controllers/extraction_controller.py:1833`

**Current Flow**:
```python
1. _build_filter_domain(filters)          # Build search domain
2. Document.search(domain, order=...)     # Query 1: Get all documents
3. all_documents.grouped(lambda d: ...)   # N queries if not prefetched
4. max(docs, key=lambda d: ...)           # Python-side max per group
5. Sort in Python by organization name    # Python-side sorting
6. Document.browse([ids])                 # Re-convert to recordset
7. Return documents                       # NO prefetching
```

### Performance Bottlenecks Identified

#### 🔴 **Critical Bottleneck #1: N+1 Query in Grouping**
**Location**: Line 1868-1869
```python
grouped_docs = all_documents.grouped(
    lambda d: (d.organization_id.id, d.year, d.document_type)
)
```

**Problem**:
- Accessing `d.organization_id.id` triggers lazy loading
- For 1000 documents → potentially 1000 SQL queries
- Odoo's `grouped()` doesn't prefetch relations

**Impact**:
- Query count: O(N) where N = document count
- Time complexity: Linear scaling with dataset

**Evidence**:
```
Example with 500 documents:
- Initial search: 1 query
- Grouping iteration: 500 queries (one per organization_id access)
- Total: 501 queries just for grouping
```

---

#### 🟠 **Major Bottleneck #2: N×M Queries in Sheet Functions**
**Location**: All 6 `_fill_sheet*` functions (lines 2285-2700+)

**Problem**:
- Each sheet function independently accesses One2many fields
- No prefetching strategy for related records
- Example from `_fill_sheet1_company` (line 2301):
  ```python
  for doc in documents:
      doc_activity_codes = doc.activity_field_ids.mapped('code')  # Query per doc
      org = doc.organization_id                                    # Query per doc
  ```

**Impact**:
- Query count: O(N × M) where M = number of relationships (~8)
- 6 sheet functions × 100 documents × 8 relations = ~4,800 queries

**Relationships accessed**:
1. `organization_id` (Many2one)
2. `activity_field_ids` (Many2many)
3. `substance_usage_ids` (One2many)
4. `quota_usage_ids` (One2many)
5. `equipment_product_ids` (One2many)
6. `equipment_ownership_ids` (One2many)
7. `equipment_product_report_ids` (One2many)
8. `equipment_ownership_report_ids` (One2many)
9. `collection_recycling_ids` (One2many)
10. `collection_recycling_report_ids` (One2many)

**Nested relations** (add more queries):
- `substance_usage_ids.substance_id.name`
- `substance_usage_ids.activity_field_id.code`
- `equipment_product_ids.equipment_type_id.name`
- `equipment_ownership_ids.province_id.name`
- etc.

---

#### 🟡 **Medium Bottleneck #3: Redundant Python Processing**
**Location**: Line 1877, 1881-1887

**Problem 1**: Redundant `max()` calculation
```python
latest = max(docs, key=lambda d: (d.create_date or d.id))
```
- Data already sorted by `create_date DESC` in line 1855
- Re-evaluating max is wasteful

**Problem 2**: Python-side sorting
```python
latest_docs.sort(
    key=lambda d: (d.organization_id.name or '', d.year or 0, ...)
)
```
- Sorting in Python after DB query
- Accessing `organization_id.name` may trigger queries
- PostgreSQL is much faster at sorting

**Impact**:
- CPU waste: O(N log N) sorting
- Potential queries: O(N) for organization names

---

#### 🟡 **Minor Bottleneck #4: Missing Indexes**

**Current indexed fields** (from `document_extraction.py`):
- ✅ `name` (computed, line 25)
- ✅ `document_type` (line 34)
- ✅ `year` (line 80)
- ✅ `state` (line 105)
- ✅ `organization_id` (line 166)
- ✅ `extraction_log_id` (line 122)
- ✅ `source` (line 136)
- ✅ `ocr_status` (line 148)
- ✅ `gdrive_file_id` (line 157)

**Missing indexes** (used in filters):
- ❌ `create_date` - Used for finding latest document (line 1855, 1877)
- ❌ `activity_field_ids` - Many2many relation table needs index
- ❌ `business_id` in `res.partner` - Used in organization filter (line 1815)

**Impact**:
- Sequential scans on large tables
- Slower filtering when using organization_code filter

---

### Performance Metrics Estimation

**Scenario**: Export 200 documents with filters

**Current implementation**:
```
1. Initial filter search:           1 query
2. Grouping (organization access):  200 queries
3. Sheet 1 (company info):          200 queries (org + activity fields)
4. Sheet 2-6 (One2many access):     1,000+ queries (200 docs × 5 sheets × 1+ relations)
---------------------------------------------------------------------
TOTAL:                              ~1,401+ queries
Time estimate:                      10-30 seconds (depending on DB latency)
```

**Optimized implementation** (proposed):
```
1. read_group (latest IDs):         1 query (GROUP BY in PostgreSQL)
2. search_read (document fields):   1 query (batch load all fields)
3. Prefetch One2many relations:     10 queries (one per relation type)
4. Sheet 1-6 (cached access):       0 queries (use prefetched data)
---------------------------------------------------------------------
TOTAL:                              ~12 queries
Time estimate:                      1-3 seconds (mostly data processing)
```

**Expected speedup**: **5-20x** depending on dataset size and DB latency

---

## 🎯 PHASE 2: OPTIMIZATION STRATEGY

### Strategy Overview: read_group + search_read + Prefetching

#### Step 1: Use `read_group()` for Grouping (Database-Level)
**Replace**: Python-side `grouped()` + `max()`
**With**: PostgreSQL `GROUP BY` + `MAX(id)`

**Benefits**:
- Single SQL query with aggregate function
- No N+1 problem
- Returns only latest document IDs per group

**Implementation**:
```python
grouped_data = Document.read_group(
    domain=doc_domain,
    fields=['id:max', 'organization_id', 'year', 'document_type'],
    groupby=['organization_id', 'year', 'document_type'],
    lazy=False  # Do all grouping in one call
)
# Result: [{'id': 123, 'organization_id': (5, 'Company A'), 'year': 2024, ...}, ...]
```

**SQL equivalent**:
```sql
SELECT MAX(id) as id, organization_id, year, document_type
FROM document_extraction
WHERE <filter_conditions>
GROUP BY organization_id, year, document_type
```

---

#### Step 2: Use `search_read()` for Efficient Field Loading
**Replace**: `search()` + field access
**With**: `search_read()` with explicit field list

**Benefits**:
- Single query loads all needed fields
- Returns dictionaries (fast access)
- No lazy loading surprises

**Implementation**:
```python
# Extract latest document IDs from read_group
latest_ids = [group['id'] for group in grouped_data]

# Load all fields in one query
document_data = Document.search_read(
    domain=[('id', 'in', latest_ids)],
    fields=[
        'id', 'year', 'document_type', 'organization_id', 'organization_name',
        'business_id', 'activity_field_ids', 'substance_usage_ids',
        'quota_usage_ids', 'equipment_product_ids', ...
    ],
    order='organization_id, year, document_type'
)
```

**SQL equivalent**:
```sql
SELECT id, year, document_type, organization_id, organization_name, ...
FROM document_extraction
WHERE id IN (123, 456, 789, ...)
ORDER BY organization_id, year, document_type
```

---

#### Step 3: Batch Prefetch All Relations
**Replace**: On-demand lazy loading
**With**: Explicit prefetching via `mapped()`

**Benefits**:
- Force Odoo to load relations in batches
- Eliminates N+1 queries in sheet functions
- Uses Odoo's built-in prefetch mechanism

**Implementation**:
```python
# Convert to recordset
documents = Document.browse([data['id'] for data in document_data])

# Prefetch Many2one relations
documents.mapped('organization_id.name')
documents.mapped('organization_id.business_id')
documents.mapped('contact_state_id.name')

# Prefetch Many2many relations
documents.mapped('activity_field_ids.code')

# Prefetch One2many relations
all_substance_usage = documents.mapped('substance_usage_ids')
all_substance_usage.mapped('substance_id.name')
all_substance_usage.mapped('activity_field_id.code')

# Repeat for all 10 One2many relationships
```

**Result**: All data cached in Odoo's prefetch system

---

#### Step 4: Add Database Indexes
**Target**: Fields used in WHERE clauses and JOINs

**New indexes needed**:
1. `document_extraction.create_date` - For finding latest documents
2. `document_extraction_activity_field_ids_rel` (Many2many table) - For activity filter
3. `res_partner.business_id` - For organization code search

**Implementation**: SQL migration script (see Phase 4)

---

### Why This Approach?

#### Advantages:
1. ✅ **Minimal code changes** - Works within Odoo ORM
2. ✅ **Proven pattern** - Uses standard Odoo APIs (`read_group`, `search_read`, `mapped`)
3. ✅ **Maintains compatibility** - Sheet functions don't need changes
4. ✅ **Database-level optimization** - Leverages PostgreSQL's strengths
5. ✅ **Predictable performance** - Query count becomes constant O(1)
6. ✅ **Easy to test** - Can A/B test old vs new implementation
7. ✅ **Low risk** - No raw SQL, stays within ORM security

#### Alternatives considered (and why rejected):
- ❌ **Raw SQL with window functions** - Bypasses ORM, security risks
- ❌ **Parallel processing** - Complex, threading issues in Odoo
- ❌ **Caching layer** - Adds complexity, stale data issues

---

## 🗄️ PHASE 3: DATABASE INDEXING STRATEGY

### Index Analysis

#### Existing Indexes (Already Optimal)
From `document_extraction.py`:
```python
✅ year (index=True)              # Line 80 - Used in year range filters
✅ state (index=True)             # Line 105 - Used in status filter
✅ organization_id (index=True)   # Line 166 - Used in org filter & grouping
✅ document_type (index=True)     # Line 34 - Used in grouping
```

#### Missing Indexes (Need to Add)

##### 1. `create_date` Index
**Table**: `document_extraction`
**Column**: `create_date`
**Reason**:
- Used in ORDER BY clause (line 1855)
- Used to find latest document per group (line 1877)
- High cardinality field (unique per record)

**SQL**:
```sql
CREATE INDEX idx_document_extraction_create_date
ON document_extraction(create_date DESC);
```

**Impact**: Faster sorting and max() aggregation

---

##### 2. Composite Index for Grouping
**Table**: `document_extraction`
**Columns**: `(organization_id, year, document_type, create_date DESC)`
**Reason**:
- Matches exact GROUP BY clause in read_group
- Includes ORDER BY column for faster MAX()
- Covers the entire query pattern

**SQL**:
```sql
CREATE INDEX idx_document_extraction_group_latest
ON document_extraction(organization_id, year, document_type, create_date DESC);
```

**Impact**:
- PostgreSQL can use index-only scan for grouping
- 10-50x faster GROUP BY operations
- Most important index to add

---

##### 3. Many2many Relation Index
**Table**: `document_extraction_activity_field_ids_rel` (auto-generated)
**Columns**: `(document_extraction_id, activity_field_id)`
**Reason**:
- Used in activity_field filter (line 1798)
- Many2many queries without index are slow

**SQL**:
```sql
-- Check if index exists
SELECT indexname FROM pg_indexes
WHERE tablename = 'document_extraction_activity_field_ids_rel';

-- Create if missing
CREATE INDEX IF NOT EXISTS idx_doc_activity_rel_doc_id
ON document_extraction_activity_field_ids_rel(document_extraction_id);

CREATE INDEX IF NOT EXISTS idx_doc_activity_rel_activity_id
ON document_extraction_activity_field_ids_rel(activity_field_id);
```

**Impact**: Faster filtering by activity fields

---

##### 4. Partner (Organization) Index
**Table**: `res_partner`
**Column**: `business_id`
**Reason**:
- Used in organization code filter (line 1815)
- ILIKE searches are slow without index
- Custom field, may not have index

**SQL**:
```sql
CREATE INDEX idx_res_partner_business_id
ON res_partner(business_id);

-- For case-insensitive ILIKE searches (PostgreSQL)
CREATE INDEX idx_res_partner_business_id_lower
ON res_partner(LOWER(business_id));
```

**Impact**: 100x faster organization code searches

---

### Index Size Estimation

**Assumptions**:
- 10,000 documents
- 500 organizations
- 100 activity fields

**Estimated index sizes**:
```
1. create_date index:           ~200 KB (timestamp + row pointer)
2. Composite index:             ~500 KB (4 columns × 10K rows)
3. Many2many index:             ~100 KB (two integers × ~20K relations)
4. business_id index:           ~50 KB (varchar × 500 partners)
---------------------------------------------------------------------
TOTAL additional space:         ~850 KB (~1 MB)
```

**Cost**: Negligible storage impact, massive query improvement

---

### Index Maintenance Considerations

#### Write Performance Impact
- **INSERT**: +2-5% slower (4 additional indexes to update)
- **UPDATE**: Only if indexed columns change
- **DELETE**: Minimal impact

**Trade-off**: Acceptable for read-heavy workload (exports are read operations)

#### Index Bloat Prevention
```sql
-- Monitor index bloat (run quarterly)
SELECT schemaname, tablename, indexname,
       pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
  AND tablename IN ('document_extraction', 'res_partner')
ORDER BY pg_relation_size(indexrelid) DESC;

-- Rebuild if bloated (>30% bloat)
REINDEX INDEX CONCURRENTLY idx_document_extraction_group_latest;
```

---

## 🛠️ PHASE 4: IMPLEMENTATION PLAN

### Step-by-Step Implementation

#### **Step 1: Create Baseline Performance Metrics** ⏱️ 1 hour

**Actions**:
1. Create test script to measure current performance
2. Generate test dataset (100, 500, 1000 documents)
3. Record query count and execution time

**Deliverable**: `tests/performance/baseline_export_performance.py`
```python
# Test script structure
def test_export_performance():
    # Create test data
    # Measure query count using pg_stat_statements
    # Measure execution time
    # Output: CSV with metrics
```

**Success criteria**: Baseline metrics documented

---

#### **Step 2: Add Database Indexes** ⏱️ 30 minutes

**Actions**:
1. Create SQL migration script
2. Test on development database
3. Verify index usage with EXPLAIN ANALYZE

**Deliverable**: `migrations/1.0.2/post-add_export_performance_indexes.sql`

```sql
-- Migration script
-- Version: 1.0.2
-- Description: Add indexes for HFC export performance

-- Index 1: create_date for sorting and max aggregation
CREATE INDEX IF NOT EXISTS idx_document_extraction_create_date
ON document_extraction(create_date DESC);

-- Index 2: Composite index for efficient grouping
CREATE INDEX IF NOT EXISTS idx_document_extraction_group_latest
ON document_extraction(organization_id, year, document_type, create_date DESC);

-- Index 3: Many2many relation indexes
CREATE INDEX IF NOT EXISTS idx_doc_activity_rel_doc_id
ON document_extraction_activity_field_ids_rel(document_extraction_id);

CREATE INDEX IF NOT EXISTS idx_doc_activity_rel_activity_id
ON document_extraction_activity_field_ids_rel(activity_field_id);

-- Index 4: Partner business_id for organization filter
CREATE INDEX IF NOT EXISTS idx_res_partner_business_id
ON res_partner(business_id);

-- Analyze tables to update statistics
ANALYZE document_extraction;
ANALYZE res_partner;
ANALYZE document_extraction_activity_field_ids_rel;

-- Verification: Check index usage
-- Run this AFTER first export to see if indexes are used:
-- SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read
-- FROM pg_stat_user_indexes
-- WHERE tablename = 'document_extraction'
-- ORDER BY idx_scan DESC;
```

**Success criteria**:
- All 4 indexes created successfully
- No errors in migration log
- Index sizes are reasonable (check `pg_relation_size`)

---

#### **Step 3: Implement Optimized Function** ⏱️ 2 hours

**Actions**:
1. Create new function `_collect_export_data_v2()`
2. Keep old function for comparison
3. Add feature flag to switch between implementations

**Deliverable**: Updated `extraction_controller.py`

**Code structure**:
```python
# Add at top of class
USE_OPTIMIZED_EXPORT = True  # Feature flag for A/B testing

def _collect_export_data(self, filters):
    """Router function - switches between old and new"""
    if self.USE_OPTIMIZED_EXPORT:
        return self._collect_export_data_v2(filters)
    else:
        return self._collect_export_data_v1(filters)

def _collect_export_data_v1(self, filters):
    """Original implementation (renamed for comparison)"""
    # Current code moved here unchanged

def _collect_export_data_v2(self, filters):
    """
    OPTIMIZED: Uses read_group + search_read + prefetching
    Performance: O(1) constant queries instead of O(N×M)
    """
    # Step 1: Use read_group to find latest document IDs
    grouped_data = Document.read_group(...)

    # Step 2: Use search_read to load fields efficiently
    document_data = Document.search_read(...)

    # Step 3: Batch prefetch all relations
    documents.mapped('organization_id.name')
    # ... etc

    # Step 4: Return same format as v1
    return {'documents': documents, ...}
```

**Success criteria**:
- New function returns identical data structure
- Old function still works
- Feature flag allows instant rollback

---

#### **Step 4: Add Query Logging** ⏱️ 30 minutes

**Actions**:
1. Add query counter decorator
2. Log query count before/after optimization
3. Add timing metrics

**Deliverable**: `utils/performance_monitor.py`

```python
import time
from functools import wraps
from odoo import sql_db

def log_query_performance(func):
    """Decorator to log query count and execution time"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Get initial query count
        cr = args[0].env.cr
        initial_count = cr._obj.query_count if hasattr(cr._obj, 'query_count') else 0

        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time

        # Calculate queries executed
        final_count = cr._obj.query_count if hasattr(cr._obj, 'query_count') else 0
        query_count = final_count - initial_count

        _logger.info(f"{func.__name__}: {query_count} queries in {elapsed:.2f}s")
        return result

    return wrapper

# Usage:
@log_query_performance
def _collect_export_data_v2(self, filters):
    ...
```

**Success criteria**:
- Query count logged for each export
- Timing metrics visible in logs

---

#### **Step 5: Testing & Validation** ⏱️ 3 hours

**Test cases**:

1. **Functional tests** (data integrity):
   ```python
   def test_v1_vs_v2_identical_output():
       """Verify v2 returns same data as v1"""
       filters = {...}
       v1_result = controller._collect_export_data_v1(filters)
       v2_result = controller._collect_export_data_v2(filters)
       assert v1_result['documents'].ids == v2_result['documents'].ids
   ```

2. **Performance tests** (query count):
   ```python
   def test_query_count_reduction():
       """Verify query count is constant"""
       # Test with 10 docs
       queries_10 = measure_queries(10)
       # Test with 100 docs
       queries_100 = measure_queries(100)
       # Should be similar (constant O(1))
       assert abs(queries_10 - queries_100) < 5
   ```

3. **Load tests** (large datasets):
   ```python
   def test_large_export():
       """Export 1000 documents under 5 seconds"""
       create_test_documents(1000)
       start = time.time()
       controller.export_hfc_report(filters)
       elapsed = time.time() - start
       assert elapsed < 5.0
   ```

4. **Edge cases**:
   - Empty result set
   - Single document
   - Multiple documents same org/year/type
   - Missing related records (orphaned IDs)

**Success criteria**:
- All tests pass
- Query count reduced by >90%
- Export time reduced by >5x

---

#### **Step 6: Documentation & Rollout** ⏱️ 1 hour

**Actions**:
1. Update CLAUDE.md with optimization notes
2. Add comments to code explaining strategy
3. Create rollback procedure
4. Prepare deployment checklist

**Deliverables**:
- Updated documentation
- Rollback script
- Deployment checklist

---

### Implementation Schedule

**Total estimated time**: ~8 hours (1 day)

```
Day 1:
├─ Morning (4h)
│  ├─ Step 1: Baseline metrics (1h)
│  ├─ Step 2: Add indexes (0.5h)
│  ├─ Step 3: Implement v2 function (2h)
│  └─ Step 4: Add logging (0.5h)
│
└─ Afternoon (4h)
   ├─ Step 5: Testing (3h)
   └─ Step 6: Documentation (1h)
```

---

## 🧪 PHASE 5: TESTING STRATEGY

### Test Environment Setup

**Requirements**:
1. Staging database with production-like data
2. PostgreSQL query logging enabled
3. Odoo profiler enabled (`--dev=all`)

**Enable query logging**:
```python
# In odoo.conf
[options]
log_level = debug
log_handler = :INFO,odoo.sql_db:DEBUG

# Or programmatically
import logging
logging.getLogger('odoo.sql_db').setLevel(logging.DEBUG)
```

---

### Performance Comparison Matrix

**Test scenarios**:

| Scenario | Document Count | Filters | Expected Queries (v1) | Expected Queries (v2) | Target Speedup |
|----------|----------------|---------|------------------------|------------------------|----------------|
| Small    | 10             | None    | ~100                   | ~12                    | 8x             |
| Medium   | 100            | Year    | ~1,000                 | ~12                    | 80x            |
| Large    | 500            | All     | ~5,000                 | ~12                    | 400x           |
| XL       | 1000           | All     | ~10,000                | ~12                    | 800x           |

---

### Query Analysis Tools

**1. PostgreSQL EXPLAIN ANALYZE**:
```sql
EXPLAIN ANALYZE
SELECT MAX(id), organization_id, year, document_type
FROM document_extraction
WHERE state = 'completed'
GROUP BY organization_id, year, document_type;

-- Look for:
-- - "Index Scan using idx_document_extraction_group_latest"
-- - "GroupAggregate" or "HashAggregate"
-- - Execution time < 50ms
```

**2. Odoo Query Counter**:
```python
# Add to test
from odoo.tests.common import TransactionCase

class TestExportPerformance(TransactionCase):
    def test_query_count(self):
        with self.assertQueryCount(__lt__=15):  # Less than 15 queries
            controller._collect_export_data_v2(filters)
```

**3. cProfile for Python profiling**:
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

controller.export_hfc_report(filters)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 slowest functions
```

---

### Acceptance Criteria

**Must pass all**:
- ✅ Query count reduced by >90%
- ✅ Export time reduced by >5x for 100+ documents
- ✅ All functional tests pass (data integrity)
- ✅ No memory leaks (test with 1000+ documents)
- ✅ Indexes used by PostgreSQL (verify with EXPLAIN)
- ✅ Zero bugs in staging environment (3 day soak test)

---

## 🔄 PHASE 6: ROLLBACK PROCEDURE

### Feature Flag Rollback (Instant)

**If issues found in production**:
```python
# In extraction_controller.py
USE_OPTIMIZED_EXPORT = False  # Switch back to v1

# Or via system parameter (no code change needed)
IrConfig = env['ir.config_parameter'].sudo()
IrConfig.set_param('robotia_document_extractor.use_optimized_export', 'false')

# Then in code:
USE_OPTIMIZED_EXPORT = IrConfig.get_param(
    'robotia_document_extractor.use_optimized_export',
    'true'
) == 'true'
```

**Time to rollback**: < 1 minute (change config + restart)

---

### Index Rollback (Optional)

**If indexes cause issues** (unlikely):
```sql
-- Drop indexes (does NOT affect data)
DROP INDEX IF EXISTS idx_document_extraction_create_date;
DROP INDEX IF EXISTS idx_document_extraction_group_latest;
DROP INDEX IF EXISTS idx_doc_activity_rel_doc_id;
DROP INDEX IF EXISTS idx_doc_activity_rel_activity_id;
DROP INDEX IF EXISTS idx_res_partner_business_id;

-- Analyze to update stats
ANALYZE document_extraction;
```

**When to rollback indexes**:
- ❌ **DO NOT** rollback unless:
  - Write performance degrades by >20%
  - Index bloat causes disk space issues
  - Query planner chooses wrong index

**Time to rollback**: ~5 minutes (run SQL script)

---

### Complete Rollback Checklist

1. ☐ Switch feature flag to `False`
2. ☐ Restart Odoo server
3. ☐ Test one export to verify v1 works
4. ☐ Monitor logs for query count (should be high again)
5. ☐ Document issue for post-mortem
6. ☐ (Optional) Drop indexes if needed

---

## 📝 PHASE 7: POST-DEPLOYMENT MONITORING

### Metrics to Track

**1. Export Performance** (track weekly):
```sql
-- Average export time by document count
SELECT
    COUNT(*) as doc_count,
    AVG(execution_time_ms) as avg_time_ms,
    MAX(execution_time_ms) as max_time_ms
FROM export_log
WHERE export_date >= NOW() - INTERVAL '7 days'
GROUP BY (COUNT(*)/100) * 100  -- Group by hundreds
ORDER BY doc_count;
```

**2. Index Usage** (track monthly):
```sql
-- Check if indexes are being used
SELECT
    indexrelname AS index_name,
    idx_scan AS times_used,
    idx_tup_read AS rows_read,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
  AND tablename = 'document_extraction'
ORDER BY idx_scan DESC;

-- Unused indexes (consider dropping if idx_scan = 0 after 3 months)
```

**3. Query Performance** (track daily):
```sql
-- Enable pg_stat_statements extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Top 10 slowest queries
SELECT
    query,
    calls,
    mean_exec_time::numeric(10,2) as avg_ms,
    max_exec_time::numeric(10,2) as max_ms
FROM pg_stat_statements
WHERE query LIKE '%document_extraction%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

---

### Success Metrics (3 months post-deployment)

**Targets**:
- Query count: <15 per export (vs ~1000+ before)
- Export time: <3 seconds for 100 docs (vs ~15-30s before)
- User complaints: 0 (performance-related)
- Database CPU: -20% reduction
- Index hit ratio: >95% for new indexes

---

## 🎁 PHASE 8: FUTURE ENHANCEMENTS (Optional)

### Additional Optimizations (if needed)

**1. Materialized View for Analytics** (if dashboard is slow):
```sql
CREATE MATERIALIZED VIEW mv_document_extraction_latest AS
SELECT DISTINCT ON (organization_id, year, document_type)
    id, organization_id, year, document_type, create_date, state
FROM document_extraction
WHERE state = 'completed'
ORDER BY organization_id, year, document_type, create_date DESC;

CREATE INDEX ON mv_document_extraction_latest(organization_id, year, document_type);

-- Refresh daily via cron
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_document_extraction_latest;
```

**2. Partial Indexes** (if filters are predictable):
```sql
-- Index only completed documents (most common filter)
CREATE INDEX idx_document_extraction_completed
ON document_extraction(organization_id, year, document_type, create_date)
WHERE state = 'completed';
```

**3. Database Partitioning** (if table grows >1M rows):
```sql
-- Partition by year (for time-series data)
CREATE TABLE document_extraction_2024 PARTITION OF document_extraction
FOR VALUES FROM (2024) TO (2025);
```

---

## 📚 REFERENCES & RESOURCES

### Odoo Performance Documentation
- [Odoo Performance Optimization](https://www.odoo.com/documentation/18.0/developer/reference/performance.html)
- [ORM Performance Best Practices](https://www.odoo.com/documentation/18.0/developer/reference/backend/orm.html#performance)

### PostgreSQL Indexing
- [PostgreSQL Index Types](https://www.postgresql.org/docs/current/indexes-types.html)
- [EXPLAIN ANALYZE Tutorial](https://www.postgresql.org/docs/current/using-explain.html)

### Similar Optimizations in Odoo
- Odoo's own `read_group` implementation: `/odoo/models.py:2800`
- Stock module's inventory aggregation patterns
- Accounting module's report generation optimizations

---

## ✅ IMPLEMENTATION CHECKLIST

### Pre-Implementation
- [ ] Backup production database
- [ ] Create staging environment with production data
- [ ] Measure baseline performance metrics
- [ ] Get approval from stakeholders

### Implementation
- [ ] Create SQL migration script for indexes
- [ ] Test indexes in staging
- [ ] Implement `_collect_export_data_v2()` function
- [ ] Add feature flag for rollback capability
- [ ] Add query logging and monitoring
- [ ] Write unit tests for data integrity
- [ ] Write performance tests

### Testing
- [ ] Test with 10 documents
- [ ] Test with 100 documents
- [ ] Test with 500 documents
- [ ] Test with 1000 documents
- [ ] Test all filter combinations
- [ ] Test edge cases (empty results, single doc, etc.)
- [ ] Verify query count reduction (>90%)
- [ ] Verify execution time reduction (>5x)
- [ ] 3-day soak test in staging

### Deployment
- [ ] Deploy to staging first
- [ ] Monitor staging for 3 days
- [ ] Deploy indexes to production (off-peak hours)
- [ ] Deploy code to production
- [ ] Enable feature flag (v2)
- [ ] Monitor production for 24 hours
- [ ] Document final metrics

### Post-Deployment
- [ ] Update documentation (CLAUDE.md)
- [ ] Share performance improvements with team
- [ ] Schedule monthly index usage review
- [ ] Plan for future optimizations (if needed)

---

## 🎯 EXPECTED OUTCOMES

### Quantitative Improvements
- **Query count**: 1401+ → 12 queries (**99% reduction**)
- **Export time**: 10-30s → 1-3s (**5-10x faster**)
- **Database CPU**: -20% reduction
- **User satisfaction**: Improved (no more waiting)

### Qualitative Improvements
- **Scalability**: Can handle 10x more documents without slowdown
- **Maintainability**: Code is cleaner and easier to understand
- **Reliability**: Predictable performance regardless of dataset size
- **Debuggability**: Clear logging shows where time is spent

---

## 📞 SUPPORT & ESCALATION

**If issues arise**:
1. Check logs: `/var/log/odoo/odoo-server.log`
2. Verify indexes: Run verification queries from Phase 3
3. Check feature flag: Confirm v2 is enabled
4. Rollback if needed: See Phase 6
5. Report issue: Create ticket with:
   - Error logs
   - Query logs
   - Test case to reproduce
   - Database size and version

---

**Plan prepared by**: Claude Code AI Assistant
**Date**: 2026-01-12
**Status**: Ready for implementation
**Estimated effort**: 8 hours (1 developer day)
**Risk level**: Low (rollback available via feature flag)
