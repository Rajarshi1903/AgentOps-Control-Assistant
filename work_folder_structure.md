agentops-control-tower/
│
├── data/
│   ├── products.csv
│   ├── sales_history.csv
│   ├── inventory.csv
│   ├── suppliers.csv
│   ├── routes.csv
│   ├── disruptions.csv
│   ├── agent_permissions.csv
│   └── policy_rules.yaml
│
├── src/
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── agent_outputs.py
│   │   ├── governance.py
│   │   ├── audit.py
│   │   ├── final_response.py
│   │   └── state.py
│   │
│   ├── agents/
│   │   ├── coordinator_agent.py
│   │   ├── forecasting_agent.py
│   │   ├── inventory_agent.py
│   │   ├── procurement_agent.py
│   │   └── logistics_agent.py
│   │
│   ├── governance/
│   │   ├── permissions.py
│   │   ├── policy_engine.py
│   │   └── risk_scoring_engine.py
│   │
│   ├── graph/
│   │   └── workflow_graph.py
│   │
│   ├── storage/
│   │   ├── sqlite_store.py
│   │   └── schema.sql
│   │
│   ├── services/
│   │   ├── azure_openai_client.py
│   │   ├── azure_search_client.py
│   │   └── config.py
│   │
│   └── app.py
│
├── tests/
│   ├── test_schemas.py
│   ├── test_policy_engine.py
│   └── test_workflow.py
│
├── .env
├── requirements.txt
└── README.md