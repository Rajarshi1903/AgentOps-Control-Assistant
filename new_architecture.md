User Query
    ↓
┌─────────────────────────────────────────┐
│  Coordinator Agent (LLM)                │
│  - Extracts intent, product_id, region  │
│  - Maps to workflow steps               │
│  - Selects supplier selection strategy  │
└─────────────────┬───────────────────────┘
                  ↓
    ┌───────────────────────────────── ┐
    │  LangGraph State Router          │
    │  - Executes workflow steps       │
    │  - Tracks completed steps        │
    │  - Propagates state              │
    └─────┬────────────────────────────┘
          ↓
  ╔═════════════════════════════════════════╗
  ║  BUSINESS LOGIC AGENTS (Conditional)    ║
  ║                                         ║
  ║  ├─ Forecasting Agent                   ║
  ║  │  └─ Weighted moving average          ║
  ║  │  └─ Spike detection                  ║
  ║  ├─ Inventory Agent                     ║
  ║  │  └─ Stock checking                   ║
  ║  │  └─ Shortage calculation             ║
  ║  ├─ Procurement Agent                   ║
  ║  │  └─ Supplier selection               ║
  ║  │  └─ Quantity recommendation          ║
  ║  └─ Logistics Agent                     ║
  ║     └─ Route selection                  ║
  ║     └─ Disruption impact                ║
  ║                                         ║
  ╚═════────┬─────────────────────────────╝
            ↓
    ┌─────────────────────────────────┐
    │  PDF-FIRST Policy Engine (RAG)   │
    │  - Retrieves from policy PDF     │
    │  - LLM extracts rules            │
    │  - Python applies guardrails     │
    │  - Decision: Allow/Block/Escalate│
    └─────┬─────────────────────────────┘
          ↓
    ┌─────────────────────────────────┐
    │  Risk Scoring Engine             │
    │  - Calculates numeric risk score │
    │  - Maps to Low/Medium/High/Critical
    │  - Adds risk factors             │
    └─────┬─────────────────────────────┘
          ↓
    ┌─────────────────────────────────┐
    │  Approval Agent                  │
    │  - Determines if approval needed │
    │  - Assigns reviewer role         │
    │  - Routes to human if required   │
    └─────┬─────────────────────────────┘
          ↓
    ┌─────────────────────────────────┐
    │  Audit Logger (SQLite)           │
    │  - Persists complete state       │
    │  - Generates unique audit ID     │
    │  - Stores evidence               │
    └─────┬─────────────────────────────┘
          ↓
    ┌─────────────────────────────────┐
    │  Final Response Agent (LLM)      │
    │  - Summarizes decision           │
    │  - Explains to business user     │
    │  - Includes evidence             │
    └─────┬─────────────────────────────┘
          ↓
    Dashboard / Control UI