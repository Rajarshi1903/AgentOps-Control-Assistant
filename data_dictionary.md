The project needs 8 files:
1. products.csv
-> master dataset- tells what products are currently existing in the system
-> columns: product_id = unique identifier
            product_name = human readable prodcut name
            category = type of product (electronic, packaging,..)
            unit_of_measure = units (metres, rolls,..)
            unit_price = selling price per unit
            criticality = buisness importance (high, medium, low)
            status = whether prodcut is active or not


2. sales_history.csv
-> this captures histortical demand (used by Forecasting Agent)- 90 days of data (10 products * 4 regions)
-> incldes seasonality, promotions and demand spikes
-> columns: date = date of sales
            product_id = which prodcut was sold
            region = where was it sold
            units_sold = quantity sold
            revenue = units sold * unit price
            promotion_flag = whether promotion was running (0/1)
            season = normal or peak
            event_flag = demand spike indicator (0/1)


3. inventory.csv
-> tracks current stock levels (Inventory Agent)- to detect shortage
-> columns: inventory_id = unique
            product_id = product in stock
            warehouse_id = contains warehouse location
            region = region of warehouse
            current_stock = available stock
            safety_stock = minimum buffer stock
            reorder_point = threshold to trigger reorder
            last_updated = last invetory update'
            max_capacity = max supply quantity
            compliance_status = compliant/Under Review/Non-compliant


4. suppliers.csv
-> defines who can supply each product and what conditions(used by Procurement Agent)
-> columns: supplier_id = unique supplier ID
            supplier_name = supplier name
            product_id = product they supply
            region = supplier location
            region = supplier location
            unit_cost = cost per unit
            lead_time_days = delivery time
            reliability_score = performance score(0-100)
            is_approved = Yes/No(governance critical)


5. routes.csv
-> used in the Logistics stage by the Logistics Agent to suggest best route in terms of cost, time, risk and availability
-> columns: route_id = unique identifier
            supplier_id = supplier from whome goods are being shipped
            origin_region = supplier's region (should match the region field in suppliers.csv)
            destination_region = region where goods need to be delivered (North, South, East, West)
            warehouse_id = warehouse receiving the goods (destination region must match this id)
            distance_km = approximate transport distance (order : Same-region < Neighbouring-region < Cross-region)
            transport_mode = road/rail/air
            base_cost = logistics cost for this route (different from procurement cost)
            estimated_time_delays = expected delivery time
            risk_level = baseline route risk (Low/Medium/High)- weather exposure, congestion, dist,...
            is_active = Yes/No
        for making compatible with graph representations later, additional columns: source_node, source_type, destination_node, destination_type




6. disruptions.csv
-> used by the Logistics Agent and the Governance Layer (Heavy rainfall, road closure, rail congestion, port delay, strike...)
-> proc. agent select suppler, log. agent finds routes, log. agent checks disruptions, policy engine evaluates route risk
-> columns: disruption_id =  unique identifier
            route_id = route affected by disruption
            disruption_type = weather/ road closure/ rail delay/ port congestion/...
            severity = seriousness of the disruption
            status = current state of disruption
            start_date = date when disruption started
            end_date = expected/ actual end date
            impact_delay_days = additional delays caused by disruption
            imapact_cost = additional logistics cost caused by disruption
            description = short text describing the issue


7. agent_permissions.csv 
-> governance dataset
-> agent world control- which agent is allowed to access what, which tool, kind of action allowed, block/escalation on crosssing boundaries
-> questions it will answer:    1. Is this agent allowed to access this dataset?
                                2. Is this agent allowed to call this tool?
                                3. Is this agent allowed to recommend this financiala action?
                                4. Is this agent allowed to communicate externally?
                                5. Should this action be allowed, blocked or escalated?
-> columns: agent_id = coordinator agent, forecasting agent, inventory agent,...
            agent_name = Coordinator Agent, Forecasting Agent,...
            agent_type = orchestrator, buiness_agent, governance_agent, logging_agent, presentation_agent
            allowed_datasets = dataset list the agent is allowed to access
            allowed_tools = tools/ functions each agent wil be allowed to use
            restricted_datasets = data that agent must never access
            max_action_value = max financial value that agent can recommend (0 for non-financial ones)
            can_external_communicate = whether agent is allowed to communicate outisde the system
            approval_required = whether that agent's sensitive action requires human approval (Yes/Conditional/No)
            status = agent currently active or not


8. policy_rules.yaml
-> 1. tells the system which actions are allowed?
   2. Which actions should be escalated?
   3. Which actions should be blocked?
   4. How should risk scores be calculated?
   5. What risk level should be assigned?
   6. What should be logged/edited?