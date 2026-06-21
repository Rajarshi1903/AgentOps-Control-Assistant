# Dataset Generation Analysis
## Complete Mapping: Generation Scripts → Data Files

---

## 1. **products.csv**

### Responsible Script
- [generate_products.py](generation_scripts/generate_products.py)

### Generation Flow
**Direct static definition** — no dependencies, no randomness. 10 products are hardcoded as Python dictionaries, converted to DataFrame, and saved as CSV.

### Transformations
- None. Data is written directly from hardcoded list to DataFrame to CSV.

### Parameters
- **File path**: `data/products.csv`
- **Output format**: CSV with 7 columns

### Randomness/Seeds
- **None**. Dataset is completely deterministic.

### Filters
- **None**. All 10 products are always included.

### Output Schema
```
product_id (string)       : P-101 to P-110, sequential IDs
product_name (string)     : Descriptive names (e.g., "Smart Sensor Module")
category (string)         : One of {Electronics, Electrical, Mechanical, Packaging, Industrial Material}
unit_of_measure (string)  : {units, meters, rolls, sheets, boxes}
unit_price (integer)      : Price in INR, range 120-5800
criticality (string)      : {High, Medium, Low} - indicates safety stock multiplier
status (string)           : Always "Active"
```

### Column Derivation

| Column | Derivation | Logic |
|--------|-----------|-------|
| product_id | Hardcoded sequence | P-101, P-102, ..., P-110 |
| product_name | Hardcoded domain names | Based on product type |
| category | Hardcoded by domain | Electronics, Mechanical, etc. |
| unit_of_measure | Hardcoded per product | Matches product type |
| unit_price | Hardcoded per product | Range: 120 (Corrugated Box) to 5800 (Hydraulic Pump) |
| criticality | Hardcoded per product | High: P-101, P-103, P-105, P-106; Medium: others with moderate importance; Low: Packaging products (P-104, P-110) |
| status | Always "Active" | All products eligible for sales/inventory |

### Key Dependencies
- **None**. This is the root dataset.

---

## 2. **sales_history.csv**

### Responsible Script
- [generate_sales_history.py](generation_scripts/generate_sales_history.py)

### Generation Flow
1. **Load products.csv** (filter: active products only)
2. **For each product-region-date combination**:
   - Calculate base demand (product + category + region-specific)
   - Apply weekly pattern multiplier
   - Apply trend over 90 days
   - Apply season effect
   - Apply promotion effect (8% probability)
   - Apply event spike (controlled scenario spikes)
3. **Generate units_sold** using negative binomial distribution
4. **Calculate revenue** = units_sold × unit_price
5. **Save to sales_history.csv**

### Transformations
- **Demand calculation**: Base demand × (region multiplier) × (weekday multiplier) × (trend multiplier) × (season multiplier) × (promotion multiplier) × (event multiplier)
- **Unit generation**: Negative binomial distribution (dispersion=25) applied to expected_demand
- **Revenue**: Integer multiplication then rounding

### Parameters
- **Random seed**: `np.random.seed(42)` (deterministic)
- **Date range**: 90 days ending 2026-05-26 (2026-02-26 to 2026-05-26)
- **Promotion probability**: 8% of days
- **Base demand by product** (product-level overrides):
  - P-101: 95 units/day
  - P-102: 210 units/day
  - P-103: 45 units/day
  - P-104: 130 units/day
  - P-105: 65 units/day
  - P-106: 35 units/day
  - P-107: 85 units/day
  - P-108: 75 units/day
  - P-109: 55 units/day
  - P-110: 300 units/day

### Randomness/Seeds
- **Seed**: `np.random.seed(42)` → reproducible across runs
- **Distribution**: Negative binomial with parameters (dispersion=25, p=25/(25+expected_demand))
- **Stochastic elements**: promotion_flag assignment (Bernoulli 0.08), demand variance

### Filters
- **Products**: Only "Active" products from products.csv
- **Regions**: All 4 regions (North, South, East, West)
- **Date range**: 90-day window

### Output Schema
```
date (string, YYYY-MM-DD)     : 2026-02-26 to 2026-05-26, daily
product_id (string)           : P-101 to P-110
region (string)               : {North, South, East, West}
units_sold (integer)          : ≥ 1, realistic variance
revenue (float)               : units_sold × unit_price, rounded to 2 decimals
promotion_flag (integer)      : {0, 1}, 8% probability = 1
season (string)               : {Normal, Peak} - May = Peak
event_flag (integer)          : {0, 1}, marks controlled demand spikes
```

### Column Derivation

| Column | Derivation | Logic |
|--------|-----------|-------|
| date | Sequential from 2026-02-26 | 90-day range, daily granularity |
| product_id | Cartesian product | All 10 active products |
| region | Cartesian product | All 4 regions |
| units_sold | Negative binomial(dispersion=25, p=p_from_expected) | Expected demand modified by weekly/seasonal/trend/event factors |
| revenue | units_sold × unit_price | Direct multiplication, 2 decimals |
| promotion_flag | Bernoulli(0.08) | Random, ~8% of days flagged |
| season | {Normal if month≠5, Peak if month=5} | Month-based (May = Peak) |
| event_flag | Indicator for controlled spikes | 1 if within spike scenario date range |

### Controlled Scenarios (Event Spikes)
- **P-101, South**: 2026-05-20 to 2026-05-26, multiplier=1.90 (demand spike)
- **P-103, North**: 2026-05-22 to 2026-05-26, multiplier=1.60
- **P-105, South**: 2026-05-21 to 2026-05-26, multiplier=1.80
- **P-104, East**: 2026-05-23 to 2026-05-26, multiplier=1.25

### Key Dependencies
- **products.csv**: Required for product_id list, unit_price for revenue calc, status filtering

### Row Count
- Expected: `len(active_products) × len(regions) × len(date_range)` = 10 × 4 × 90 = **3,600 rows**

---

## 3. **suppliers.csv**

### Responsible Script
- [generate_suppliers.py](generation_scripts/generate_suppliers.py)

### Generation Flow
1. **Load products.csv** (active only)
2. **For each product**:
   - Determine supplier count (2-3 per product, total=25)
   - Check for controlled scenario overrides (P-101, P-103, P-105)
   - For non-scenario products: generate random suppliers per type distribution
3. **For each supplier**:
   - Assign type: approved_compliant, approved_under_review, or unapproved
   - Generate unit_cost, lead_time, reliability, capacity based on type
   - Assign region randomly (except controlled scenarios)
   - Map supplier_id, supplier_name, compliance_status

### Transformations
- **unit_cost**: 60-85% of product unit_price (approved higher, unapproved lower)
- **lead_time**: Category-based ranges ± type adjustment
- **reliability_score**: Type-based ranges (approved 86-99, under_review 75-86, unapproved 55-75)
- **max_capacity**: Category-based ranges with type multiplier

### Parameters
- **Random seed**: `np.random.seed(42)`
- **Total supplier count**: 25 (hardcoded sum of supplier_count_map)
- **Supplier types distribution**:
  - For product with 2 suppliers: 50% approved_compliant, 50% mixed
  - For product with 3 suppliers: first always approved_compliant, remainder mixed
- **Lead time ranges by category**:
  - Packaging: 2-5 days
  - Electrical: 3-7 days
  - Electronics: 5-10 days
  - Mechanical: 6-14 days
  - Industrial Material: 4-8 days
- **Capacity ranges by category**:
  - Packaging: 1000-5000
  - Electrical: 800-3000
  - Electronics: 200-1000
  - Mechanical: 100-800
  - Industrial Material: 500-2000

### Randomness/Seeds
- **Seed**: `np.random.seed(42)` → reproducible
- **Stochastic**: supplier_type distribution, lead_time within range, reliability_score within range, capacity within range, region selection

### Filters
- **Products**: Active only (status="Active")
- **Excluded**: Only 3 products have hardcoded scenario data (P-101, P-103, P-105); others generated

### Output Schema
```
supplier_id (string)        : S-001 to S-025, sequential
supplier_name (string)      : Selected from pool of 25 names (no duplicates)
product_id (string)         : P-101 to P-110
region (string)             : {North, South, East, West}
unit_cost (integer)         : 60-85% of product unit_price
lead_time_days (integer)    : Category-dependent, range 2-14 days
reliability_score (integer) : 55-99 depending on approval status
is_approved (string)        : {Yes, No}
max_capacity (integer)      : Category and type-dependent
compliance_status (string)  : {Compliant, Under Review, Non-Compliant}
```

### Column Derivation

| Column | Derivation | Logic |
|--------|-----------|-------|
| supplier_id | Sequential counter | S-001 through S-025 |
| supplier_name | Unique from name pool (or fallback) | 25 names provided, fallback "Regional Supplier {id}" |
| product_id | Product iteration | Each product gets 2-3 suppliers |
| region | Random choice or controlled | For scenario products: fixed (S-001→South, S-007→North, etc.); others random |
| unit_cost | Probability-weighted by type | approved_compliant: 70-85% of unit_price; unapproved: 60-70% |
| lead_time_days | Category range ± type adjustment | Base range (e.g., Electronics 5-10) adjusted by ±1 if approved/unapproved |
| reliability_score | Type-based range | approved_compliant: 86-99; under_review: 75-86; unapproved: 55-75 |
| is_approved | Type → status mapping | approved_compliant: "Yes"; others: "No" |
| max_capacity | Category range × type multiplier | Base range × 1.0-1.2 (approved) or 0.6-0.9 (unapproved) |
| compliance_status | Type mapping | approved_compliant: "Compliant"; under_review: "Under Review"; unapproved: "Non-Compliant" |

### Controlled MVP Scenarios
- **P-101 (3 suppliers)**:
  - S-001: Alpha Components, South, approved, cost=1800, lead_time=5, reliability=92
  - S-002: Beta Industrial, South, unapproved, cost=1550, lead_time=4, reliability=68
  - S-003: Nova Electronics, West, approved, cost=1950, lead_time=7, reliability=88
- **P-103 (3 suppliers)**:
  - S-007: Omega Precision, North, approved, cost=3300, lead_time=8, reliability=90
  - (others generated)
- **P-105 (3 suppliers)**:
  - S-012: Pioneer Electronics, West, approved, cost=2300, lead_time=6, reliability=91
  - S-013: Southern Tech, South, approved, cost=2450, lead_time=5, reliability=87
  - (others as needed)

### Key Dependencies
- **products.csv**: Required for product_id list, unit_price, category, criticality

### Validation Constraints
- Every product must have ≥ 2 suppliers
- At least one unapproved supplier must exist
- unit_cost < unit_price always

---

## 4. **inventory.csv**

### Responsible Script
- [generate_inventory.py](generation_scripts/generate_inventory.py)

### Generation Flow
1. **Load products.csv** (active only) and **sales_history.csv**
2. **Calculate avg_daily_demand** per product-region from sales_history
3. **For each product-region combination** (40 rows: 10 products × 4 regions):
   - Get criticality from product master
   - Calculate **safety_stock** = avg_daily_demand × criticality_multiplier
   - Calculate **reorder_point** = safety_stock + (avg_daily_demand × lead_time_buffer)
   - Generate **current_stock** with scenario overrides or realistic patterns
4. **Map warehouse_id** to region (WH-NORTH-01, WH-SOUTH-01, WH-EAST-01, WH-WEST-01)
5. **Save to inventory.csv** with reassigned inventory_id after sorting

### Transformations
- **avg_daily_demand**: Mean of units_sold grouped by (product_id, region) from sales_history
- **safety_stock**: avg_daily_demand × criticality_multiplier (High: 0.45-0.60, Medium: 0.30-0.45, Low: 0.18-0.30)
- **reorder_point**: safety_stock + (avg_daily_demand × lead_time_buffer)
- **current_stock**: Realistic pattern or scenario override

### Parameters
- **Random seed**: `np.random.seed(42)`
- **Regions**: North, South, East, West (4 fixed)
- **Warehouse mapping**: 1:1 per region
- **Last updated**: 2026-05-26 (fixed)
- **Safety stock multiplier by criticality**:
  - High: uniform(0.45, 0.60)
  - Medium: uniform(0.30, 0.45)
  - Low: uniform(0.18, 0.30)
- **Lead time buffer by criticality**:
  - High: randint(4, 6) days
  - Medium: randint(3, 5) days
  - Low: randint(2, 4) days
- **Stock pattern distribution** (general): healthy=55%, near_reorder=30%, low=15%

### Randomness/Seeds
- **Seed**: `np.random.seed(42)` → reproducible
- **Stochastic**: safety_multiplier (uniform), lead_time_buffer (randint), stock pattern selection

### Filters
- **Products**: Active only
- **Regions**: All 4

### Output Schema
```
inventory_id (string)     : INV-001 to INV-040, reassigned after sort
product_id (string)       : P-101 to P-110
warehouse_id (string)     : WH-{REGION}-01
region (string)           : {North, South, East, West}
current_stock (integer)   : Dynamic, range 40-~2000
safety_stock (integer)    : avg_daily_demand × [0.18-0.60] depending on criticality
reorder_point (integer)   : safety_stock + (avg_daily_demand × lead_time_buffer)
last_updated (string)     : 2026-05-26
```

### Column Derivation

| Column | Derivation | Logic |
|--------|-----------|-------|
| inventory_id | Sequential after sorting | INV-001 to INV-040 |
| product_id | Product-region Cartesian | All 10 products × 4 regions |
| warehouse_id | Region → fixed warehouse | North→WH-NORTH-01, etc. |
| region | Region code | North, South, East, West |
| current_stock | Scenario override OR pattern | Scenario if (P-101,South)→80; else pattern-based |
| safety_stock | avg_daily_demand × criticality_multiplier | High multiplier 0.45-0.60, Medium 0.30-0.45, Low 0.18-0.30 |
| reorder_point | safety_stock + (avg_daily_demand × lead_time_buffer) | Ensures stock not depleted before replenishment |
| last_updated | Fixed date | 2026-05-26 |

### Controlled MVP Scenarios
- **P-101, South (INV-003)**: current_stock = 80 (force procurement escalation)
- **P-103, North**: current_stock = avg_daily_demand × 0.9 (low to force procurement)
- **P-105, South**: current_stock = avg_daily_demand × 0.8 (low to force logistics planning)
- **P-104, East**: current_stock = reorder_point × 1.6 (healthy, no procurement needed)
- **P-102, West**: current_stock = reorder_point × 0.95 (near reorder, borderline)

### Key Dependencies
- **products.csv**: Required for product_id, criticality, status
- **sales_history.csv**: Required for avg_daily_demand calculation

### Row Count
- Expected: `len(active_products) × len(regions)` = 10 × 4 = **40 rows**

---

## 5. **routes.csv**

### Responsible Script
- [generate_routes.py](generation_scripts/generate_routes.py)

### Generation Flow
1. **Load suppliers.csv** and **inventory.csv** (validation pass)
2. **For each supplier**:
   - Determine route_count: 3 if important_scenario_supplier, else 2
   - Choose destination regions (ensure scenario destinations included, same-region route present)
3. **For each destination**:
   - Get warehouse_id from region
   - Calculate distance_km (synthetic realistic ranges per region pair)
   - Choose transport_mode based on distance probability
   - Estimate delivery time based on distance and mode
   - Calculate base_cost (fixed + km-based, mode-dependent)
   - Assign risk_level (based on distance, mode, cross-region)
   - Set is_active (93% Yes, 7% No; scenario suppliers mostly Yes)
4. **Save to routes.csv**

### Transformations
- **distance_km**: Drawn from region-pair-specific ranges (e.g., North-South 1400-1900 km)
- **transport_mode**: Probabilistic based on distance (long distances favor Rail/Air)
- **estimated_time_days**: Mode and distance-based ranges (Road short: 1-3 days, Air: 1-3 days always, Rail: 2-9 days)
- **base_cost**: `fixed_cost + (distance_km × cost_per_km) × variation(0.92-1.08)`
  - Road: fixed=4000, cost_per_km=22-32
  - Rail: fixed=6000, cost_per_km=14-22
  - Air: fixed=18000, cost_per_km=45-70
- **risk_level**: Assigned based on distance, mode, cross-region status

### Parameters
- **Random seed**: `np.random.seed(42)`
- **Distance matrix**: Region-pair-specific synthetic ranges (all in km)
- **Transport mode probabilities**:
  - ≤350 km: Road 75%, Rail 20%, Air 5%
  - 351-900 km: Road 55%, Rail 35%, Air 10%
  - >900 km: Road 35%, Rail 45%, Air 20%
- **Important scenario suppliers** (get 3 routes): S-001, S-004, S-005, S-007, S-012, S-013
- **Scenario destination map**: S-001→South, S-004→West, etc. (forced route inclusion)

### Randomness/Seeds
- **Seed**: `np.random.seed(42)`
- **Stochastic**: distance within range, transport mode by probability, estimated_days variation, cost variation

### Filters
- **Suppliers**: All from suppliers.csv (25 total)
- **Regions**: All 4 (destination choices)

### Output Schema
```
route_id (string)              : R-001 to R-0{N}, sequential
source_node (string)           : supplier_id (always)
source_type (string)           : "Supplier" (always)
destination_node (string)      : warehouse_id (always)
destination_type (string)      : "Warehouse" (always)
supplier_id (string)           : S-001 to S-025
origin_region (string)         : Supplier's region
destination_region (string)    : Target region
warehouse_id (string)          : WH-{REGION}-01
distance_km (integer)          : Synthetic realistic ranges
transport_mode (string)        : {Road, Rail, Air}
base_cost (integer)            : Rounded to nearest 100
estimated_time_days (integer)  : Mode and distance-based
risk_level (string)            : {Low, Medium, High}
is_active (string)             : {Yes, No}
```

### Column Derivation

| Column | Derivation | Logic |
|--------|-----------|-------|
| route_id | Sequential counter | R-001 to R-N |
| source_node | From supplier_id | Always equals supplier_id |
| source_type | Hardcoded | Always "Supplier" |
| destination_node | From warehouse_id | Always equals warehouse_id |
| destination_type | Hardcoded | Always "Warehouse" |
| supplier_id | Supplier iteration | All 25 suppliers |
| origin_region | Supplier region | From suppliers.csv |
| destination_region | Route destination choice | Scenario-driven or random |
| warehouse_id | destination_region → warehouse | Region mapping |
| distance_km | Random from region-pair range | E.g., (North,South): 1400-1900 km |
| transport_mode | Distance-based probability | Long dist → Rail/Air favored |
| base_cost | Fixed + (distance × rate) × variation | Mode-specific rates, ±8% variation |
| estimated_time_days | Mode and distance lookup | Air fastest (1-3), Road mode-dependent, Rail slowest for long dist |
| risk_level | Distance + mode + cross-region | Longer and cross-region = higher risk; High risk scenario: S-012→South set to "High" |
| is_active | Mostly Yes (93%), scenario rules | Scenario suppliers mostly active; random 7% inactive |

### Controlled MVP Scenarios
- **S-001 to South (P-101 main)**:
  - distance_km: 172 (same-region short)
  - transport_mode: Road
  - risk_level: Low (forced)
  - is_active: Yes
- **S-012 to South (P-105 route disruption)**:
  - risk_level: High (forced)
  - transport_mode: Road (forced)
  - estimated_time_days: max(calculated, 5)

### Key Dependencies
- **suppliers.csv**: Required for supplier_id, region (origin)
- **inventory.csv**: Required for warehouse validation (destination regions)

### Validation Constraints
- Every supplier must have ≥ 1 active route
- At least one inactive route must exist
- At least one High risk route must exist
- Scenario suppliers must have routes to required destinations

### Row Count
- Expected: `(25 suppliers × 2 routes) + (6 scenario suppliers × 3 routes) = 50 + 18 = 68-70+ routes` (varies slightly due to randomness)

---

## 6. **disruptions.csv**

### Responsible Script
- [generate_disruptions.py](generation_scripts/generate_disruptions.py)

### Generation Flow
1. **Load routes.csv** (validation pass)
2. **Define 15 hardcoded disruption records** with:
   - Specific route_id assignments
   - Disruption type (Weather, Rail Delay, Road Closure, Capacity Constraint, etc.)
   - Severity and status (Active, Resolved, Planned)
   - Date ranges
   - Impact parameters
3. **Validate**:
   - Mode compatibility (Road disruptions only on Road routes, etc.)
   - Date logic (end_date ≥ start_date)
   - Route existence
4. **Save to disruptions.csv**

### Transformations
- **None**. Disruptions are explicitly curated, not derived.

### Parameters
- **Planning date**: 2026-05-26 (reference date for context)
- **Hardcoded disruption count**: 15 (exactly)
- **Disruption clustering**: Similar disruptions on nearby routes
  - West-South corridor: D-001, D-002, D-003 (all Weather, High severity, Active)
  - Rail corridor: D-004, D-005 (Rail-specific, Active)
  - Road/Air: D-006, D-007 (Capacity/Closure, Active)
  - Historical (Resolved): D-008 to D-012 (5 disruptions)
  - Planned: D-013 to D-015 (3 disruptions)

### Randomness/Seeds
- **None**. All 15 disruptions are hardcoded with fixed dates and impacts.

### Filters
- **Routes**: Only specific route_id values from routes.csv are referenced

### Output Schema
```
disruption_id (string)       : D-001 to D-015
route_id (string)            : R-### (from routes.csv)
disruption_type (string)     : {Weather, Rail Delay, Infrastructure Maintenance, Road Closure, Capacity Constraint, Air Traffic Delay, Accident, Fuel Shortage, Strike}
severity (string)            : {Low, Medium, High, Critical}
status (string)              : {Active, Resolved, Planned}
start_date (string, YYYY-MM-DD) : When disruption began/begins
end_date (string, YYYY-MM-DD)   : When disruption ended/ends
impact_delay_days (integer)  : Expected delay in days (0 if Resolved)
impact_cost (integer)        : Cost impact in INR (0 if Resolved)
description (string)         : Human-readable reason and impact
```

### Column Derivation

| Column | Derivation | Logic |
|--------|-----------|-------|
| disruption_id | Hardcoded sequence | D-001 to D-015 |
| route_id | Hardcoded assignment | Each disruption assigned specific route (e.g., D-001→R-027) |
| disruption_type | Hardcoded per disruption | Type matches route transport mode (Road routes get Weather/Closure, Rail routes get Rail Delay, etc.) |
| severity | Hardcoded per disruption | Active disruptions: High/Medium; Resolved: Medium/Low; Planned: High/Medium |
| status | Hardcoded per disruption | Active (7 disruptions), Resolved (5 disruptions), Planned (3 disruptions) |
| start_date | Hardcoded fixed date | Recent/current (Active), past (Resolved), future (Planned) |
| end_date | Hardcoded fixed date | end_date ≥ start_date always; Resolved ends in past, Planned ends in future |
| impact_delay_days | Hardcoded per disruption | Active/Planned: 1-3 days; Resolved: 0 |
| impact_cost | Hardcoded per disruption | Active/Planned: 4500-15000 INR; Resolved: 0 |
| description | Hardcoded narrative | Explains disruption context and impact |

### Curated Disruption Assignments

| ID | Route | Type | Severity | Status | Reason |
|---|---|---|---|---|---|
| D-001 | R-027 (West-South, Road) | Weather | High | Active | Demo escalation focal point |
| D-002 | R-012 (West-South, Road) | Weather | High | Active | Correlated corridor disruption |
| D-003 | R-042 (West-South, Road) | Weather | High | Active | Correlated corridor disruption |
| D-004 | R-017 (Rail) | Rail Delay | Medium | Active | Rail-specific disruption |
| D-005 | R-054 (Rail) | Infrastructure Maintenance | Medium | Active | Rail infrastructure event |
| D-006 | R-020 (Road) | Road Closure | Medium | Active | Road-specific disruption |
| D-007 | R-048 (Air) | Capacity Constraint | High | Active | Air capacity event |
| D-008 to D-012 | Various | Mixed | Low/Medium | Resolved | Historical context |
| D-013 to D-015 | Various | Mixed | Medium/High | Planned | Future visibility |

### Key Dependencies
- **routes.csv**: Required for route_id validation and transport_mode compatibility check

### Validation Constraints
- Exactly 15 disruption records
- No duplicate disruption_id
- All route_id values must exist in routes.csv
- Disruption type must be compatible with route transport_mode

---

## 7. **agent_permissions.csv**

### Responsible Script
- [generate_agent_permissions.py](generation_scripts/generate_agent_permissions.py)

### Generation Flow
1. **Define 10 hardcoded agent records** with:
   - Agent identity (id, name, type)
   - Dataset access list
   - Tool access list
   - Restricted dataset list
   - Financial limits
   - External communication permission
   - Approval requirements
   - Status
2. **Validation**:
   - Exactly 10 agents
   - No duplicate agent_id
   - All required columns present
3. **Save to agent_permissions.csv**

### Transformations
- **None**. Permissions are explicitly defined, not derived.

### Parameters
- **Total agents**: 10 (hardcoded)
- **Common restricted datasets**: hr_data.csv, payroll.csv, employee_records.csv, customer_pii.csv (all agents)

### Randomness/Seeds
- **None**. Completely deterministic.

### Filters
- **None**. All 10 agents are always included.

### Output Schema
```
agent_id (string)                    : Unique agent identifier
agent_name (string)                  : Descriptive agent name
agent_type (string)                  : {orchestrator, business_agent, governance_agent, logging_agent, presentation_agent}
allowed_datasets (string)            : Semicolon-separated CSV file names
allowed_tools (string)               : Semicolon-separated tool names
restricted_datasets (string)         : Semicolon-separated restricted dataset names
max_action_value (integer)           : Max financial action value in INR
can_external_communicate (string)    : {Yes, No}
approval_required (string)           : {Yes, No, Conditional}
status (string)                      : {Active, Inactive, Suspended}
```

### Column Derivation

| Column | Derivation | Logic |
|--------|-----------|-------|
| agent_id | Hardcoded | coordinator_agent, forecasting_agent, inventory_agent, procurement_agent, logistics_agent, policy_engine, risk_scoring_engine, audit_logger, dashboard_agent, experimental_agent |
| agent_name | Hardcoded | Human-readable version of agent_id |
| agent_type | Hardcoded | Categorizes agent role |
| allowed_datasets | Hardcoded per agent | Coordinator: all business datasets; Forecasting: products + sales_history; etc. |
| allowed_tools | Hardcoded per agent | Tools specific to agent function |
| restricted_datasets | Hardcoded | Same for most (hr_data, payroll, employee_records, customer_pii); Procurement agent adds suppliers/inventory restrictions |
| max_action_value | Hardcoded | Coordinator: 50000; Procurement: 50000; Others: 0 |
| can_external_communicate | Hardcoded | All: "No" (internal governance) |
| approval_required | Hardcoded | Coordinator: Conditional; Experimental: Yes; Most others: No |
| status | Hardcoded | Active: 9 agents; Experimental: Suspended |

### Agent Profiles

| Agent ID | Type | Primary Purpose | Allowed Datasets | Max Value | Approval |
|---|---|---|---|---|---|
| coordinator_agent | orchestrator | Orchestration | All business + governance | 50000 | Conditional |
| forecasting_agent | business | Demand forecasting | products, sales_history | 0 | No |
| inventory_agent | business | Inventory checking | products, inventory | 0 | No |
| procurement_agent | business | Procurement decisions | products, inventory, suppliers | 50000 | Conditional |
| logistics_agent | business | Route optimization | suppliers, routes, disruptions | 0 | Conditional |
| policy_engine | governance | Policy enforcement | agent_permissions, policy_rules | 0 | No |
| risk_scoring_engine | governance | Risk calculation | agent_permissions, policy_rules, suppliers, routes, disruptions | 0 | No |
| audit_logger | logging | Audit recording | audit_logs.db, agent_activity_log | 0 | No |
| dashboard_agent | presentation | Dashboard display | business data + audit logs | 0 | No |
| experimental_agent | business | Testing/experimentation | products only | 0 | Yes |

### Key Dependencies
- **None**. This is a governance/metadata dataset, not derived from others.

### Validation Constraints
- Exactly 10 agents
- No duplicate agent_id
- All required columns present

---

## 8. **policy_rules.yaml**

### Responsible Script
- [generate_policy_rules.py](generation_scripts/generate_policy_rules.py)

### Generation Flow
1. **Define governance policy YAML structure** with:
   - Metadata
   - Decision priority
   - 8 policy rules (POL-001 to POL-008)
   - Risk scoring framework
   - Risk levels
   - Decision rules
2. **Validation**: None (hardcoded structure)
3. **Save to policy_rules.yaml**

### Transformations
- **None**. YAML is generated as literal string.

### Parameters
- **Version**: 1.0
- **Currency**: INR
- **Last updated**: 2026-06-01
- **Decision priority**: [Block, Escalate, Allow] (highest to lowest strictness)
- **Risk scoring**: base_score=10, max_score=100

### Randomness/Seeds
- **None**. Completely deterministic.

### Filters
- **None**. All policies always included.

### Output Schema
**YAML structure with sections:**
- **metadata**: Version, project name, currency, description, owner
- **decision_priority**: Ordered list (Block > Escalate > Allow)
- **policies**: Array of 8 policy rules
- **risk_scoring**: Base score, max score, scoring factors
- **risk_levels**: Low/Medium/High/Critical thresholds
- **decision_rules**: Default decision logic

### Policy Rules (POL-001 to POL-008)

| ID | Name | Category | Condition | Action | Severity |
|---|---|---|---|---|---|
| POL-001 | High Value Procurement Approval | Financial Risk | procurement_value > 50000 | Escalate | High |
| POL-002 | Unapproved Vendor Block | Vendor Compliance | is_approved == "No" | Block | Critical |
| POL-003 | Missing Source Traceability Block | Traceability | source_citation_missing == true | Block | High |
| POL-004 | External Communication Approval | External Action | external_communication_attempted == true | Escalate | High |
| POL-005 | Restricted Data Access Block | Data Access | restricted_data_accessed == true | Block | Critical |
| POL-006 | High Route Disruption Review | Operational | route_disruption_severity in [High, Critical] AND status==Active | Escalate | High |
| POL-007 | Suspended Agent Block | Agent Status | agent_status != "Active" | Block | Critical |
| POL-008 | Unauthorized Tool Use Block | Tool Governance | unauthorized_tool_used == true | Block | High |

### Risk Scoring Factors

| Factor | Category | Points | Condition | Applies to |
|---|---|---|---|---|
| high_value_procurement | Financial | 30 | procurement_value > 50000 | Procurement decisions |
| unapproved_vendor | Vendor Compliance | 40 | is_approved == "No" | Vendor risk |
| external_communication | External Action | 25 | external_communication_attempted | Communication |
| restricted_data_access | Data Access | 30 | restricted_data_accessed | Data governance |
| missing_source_citation | Traceability | 20 | source_citation_missing | Source tracking |
| route_disruption | Operational | 25 | route_disruption_exists | Route risk |
| low_forecast_confidence | Model Confidence | 20 | forecast_confidence < 0.70 | Forecast quality |

### Risk Levels
- **Low**: 0-30 points
- **Medium**: 31-60 points
- **High**: 61-80 points
- **Critical**: 81-100 points

### Decision Logic
1. If any policy triggers "Block" → final decision = **Block**
2. Else if any policy triggers "Escalate" → final decision = **Escalate**
3. Else if risk_based_escalation enabled AND risk_level ∈ {High, Critical} → **Escalate**
4. Else → **Allow**

### Key Dependencies
- **None**. This is a governance framework, not derived from datasets.

---

## Summary Table: All Datasets

| Dataset | Script | Dependencies | Row Count | Seed | Deterministic |
|---|---|---|---|---|---|
| **products.csv** | generate_products.py | None | 10 | None | ✓ Yes |
| **sales_history.csv** | generate_sales_history.py | products.csv | 3,600 | 42 | ✓ Yes |
| **suppliers.csv** | generate_suppliers.py | products.csv | 25 | 42 | ✓ Yes |
| **inventory.csv** | generate_inventory.py | products.csv, sales_history.csv | 40 | 42 | ✓ Yes |
| **routes.csv** | generate_routes.py | suppliers.csv, inventory.csv | ~68-70 | 42 | ✓ Yes |
| **disruptions.csv** | generate_disruptions.py | routes.csv | 15 | None | ✓ Yes |
| **agent_permissions.csv** | generate_agent_permissions.py | None | 10 | None | ✓ Yes |
| **policy_rules.yaml** | generate_policy_rules.py | None | 1 (YAML) | None | ✓ Yes |

---

## Generation Dependency Graph

```
products.csv
    ├── sales_history.csv
    │   ├── inventory.csv
    │   │   └── routes.csv
    │   │       └── disruptions.csv
    │   └── suppliers.csv
    │       └── routes.csv
    │           └── disruptions.csv
    ├── suppliers.csv
    │   └── routes.csv
    │       └── disruptions.csv
    └── inventory.csv
        └── routes.csv
            └── disruptions.csv

agent_permissions.csv (independent)
policy_rules.yaml (independent)
```

---

## Key Insights

### Determinism & Reproducibility
- All stochastic generation uses `np.random.seed(42)`, making outputs reproducible across runs
- Both structure and parameters are explicitly defined, not randomly evolved
- 3 datasets (products, disruptions, permissions, policies) have zero randomness

### MVP Scenario Engineering
The generation logic intentionally creates specific test cases:
- **P-101, South**: Low inventory (80 units) to trigger procurement escalation
- **P-103, North**: Demand spike (1.60×) to test forecasting
- **P-105, South**: Route disruption (High risk) + low inventory to test logistics+procurement interaction
- **P-104, East**: Healthy inventory (no procurement) to demonstrate normal flow
- **S-001 → South**: Primary supplier, low-risk route for baseline case

### Data Quality Constraints
- Every product has ≥2 suppliers, ≥1 approved
- Every supplier has ≥1 active route
- Supplier cost < product price (always)
- Safety stock < reorder point < current stock (generally)
- Disruption types match route transport modes

### Geographic Clustering
- Disruptions cluster on West-South corridor (weather), North-South rail (congestion)
- Scenario suppliers (P-101, P-103, P-105) anchor specific regions (South, North)
- Distance matrix reflects synthetic India-like geography

---

## Conclusion

All 8 datasets are generated through a coordinated pipeline rooted in `products.csv`. Static governance data (permissions, policies, disruptions) provides environmental constraints. Stochastic business data (sales, inventory, routes) provides realistic variance while maintaining MVP test scenarios through hardcoded overrides. The entire pipeline is reproducible via seed=42.

