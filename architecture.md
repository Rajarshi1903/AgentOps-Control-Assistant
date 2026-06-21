                        ┌──────────────────────────┐
                        │     Business User        │
                        │ Supply Chain Planner /   │
                        │ Procurement Manager      │
                        └─────────────┬────────────┘
                                      │
                                      v
                        ┌──────────────────────────┐
                        │    User Request Layer    │
                        │ Natural language request │
                        └─────────────┬────────────┘
                                      │
                                      v
                        ┌──────────────────────────┐
                        │    Coordinator Agent     │
                        │ LLM-based orchestrator   │
                        └───────┬─────┬─────┬──────┘
                                |     |     |
                  ┌─────────────┼     |     ┼─────────────┐
                  │                   │                   │
                  v                   v                   v
     ┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
     │ Forecasting Agent  ->│ Inventory Agent    ->│ Procurement Agent  │
     │ Time-series model  │ │ Stock calculation  │ │ Supplier selection │
     └─────────┬──────────┘ └─────────┬──────────┘ └─────────┬──────────┘
               │                      │                      │
               └──────────────────────┼──────────────────────┘
                                      │
                                      v
                        ┌──────────────────────────┐
                        │    Logistics Agent       │
                        │ Route optimization       │
                        └─────────────┬────────────┘
                                      │
                                      v
                        ┌──────────────────────────┐
                        │  AgentOps Control Tower  │
                        │ Policy + Risk + Audit    │
                        └─────────────┬────────────┘
                                      │
              ┌───────────────────────┼────────────────────────┐
              │                       │                        │
              v                       v                        v
     ┌────────────────┐     ┌──────────────────┐      ┌────────────────┐
     │ Policy Engine  │     │ Risk Scoring     │      │ Audit Logger   │
     │ Allow/Block/   │     │ Low/Medium/High  │      │ Hash-chained   │
     │ Escalate       │     │ Critical         │      │ logs           │
     └───────┬────────┘     └────────┬─────────┘      └────────┬───────┘
             │                       │                         │
             └───────────────────────┼─────────────────────────┘
                                     │   
                                     v
                        ┌──────────────────────────┐
                        │ Human Approval Workflow  │    
                        │ Approve / Reject         │
                        └─────────────┬────────────┘
                                      │
                                      v 
                        ┌──────────────────────────┐
                        │ Dashboard / Control UI   │
                        │ Streamlit or React       |
                        |  + LLM  response         │
                        └──────────────────────────┘