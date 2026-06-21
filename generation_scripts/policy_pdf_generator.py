"""
Policy PDF Handbook Generator

Generates an enterprise policy handbook PDF for the AgentOps Control Tower
RAG-based Policy Engine. This handbook serves as the authoritative governance
document from which policy rules are extracted.

Usage:
    python src/rag/policy_pdf_generator.py
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    PageTemplate, Frame, KeepTogether
)
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from pathlib import Path


class NumberedCanvas(canvas.Canvas):
    """Custom canvas for page numbering."""
    
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_state = None
    
    def showPage(self):
        self._saved_state = self.__dict__.copy()
        self._startPage()
    
    def save(self):
        num_pages = self.getPageNumber()
        for page_num in range(1, num_pages + 1):
            self.drawString(7.5 * inch, 0.5 * inch, f"Page {page_num}")
        canvas.Canvas.save(self)


def create_policy_handbook():
    """Generate the AgentOps policy handbook PDF."""
    
    # Create directory if needed
    policy_dir = Path("data/policies")
    policy_dir.mkdir(parents=True, exist_ok=True)
    
    pdf_path = policy_dir / "agentops_supply_chain_policy_handbook.pdf"
    
    # Create document
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch
    )
    
    # Define styles
    styles = getSampleStyleSheet()
    
    # Custom title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a3a52'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Custom heading style
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2c5aa0'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    # Custom subheading style
    subheading_style = ParagraphStyle(
        'CustomSubHeading',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=colors.HexColor('#2c5aa0'),
        spaceAfter=10,
        spaceBefore=10,
        fontName='Helvetica-Bold'
    )
    
    # Custom body style
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        alignment=TA_JUSTIFY,
        spaceAfter=12,
        leading=14
    )
    
    # Bullet point style
    bullet_style = ParagraphStyle(
        'BulletStyle',
        parent=styles['BodyText'],
        fontSize=11,
        leftIndent=20,
        spaceAfter=8,
        leading=14
    )
    
    # Story to hold all elements
    story = []
    
    # ===== TITLE PAGE =====
    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph("AgentOps Supply Chain Governance Policy Handbook", title_style))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Enterprise Policy Document", styles['Normal']))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Effective Date: June 1, 2026", styles['Normal']))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Version: 1.0", styles['Normal']))
    story.append(PageBreak())
    
    # ===== 1. DOCUMENT CONTROL =====
    story.append(Paragraph("1. Document Control", heading_style))
    story.append(Paragraph(
        "<b>Document Title:</b> AgentOps Supply Chain Governance Policy Handbook<br/>"
        "<b>Version:</b> 1.0<br/>"
        "<b>Effective Date:</b> June 1, 2026<br/>"
        "<b>Last Updated:</b> June 1, 2026<br/>"
        "<b>Classification:</b> Internal Use<br/>"
        "<b>Approval Authority:</b> Supply Chain Leadership<br/>",
        body_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 2. PURPOSE AND SCOPE =====
    story.append(Paragraph("2. Purpose and Scope", heading_style))
    story.append(Paragraph(
        "This policy handbook provides governance guidance for the AgentOps Control Tower, an autonomous "
        "supply chain management system that uses multiple AI agents to make operational decisions. The handbook "
        "establishes clear policies, decision criteria, risk thresholds, and approval workflows to ensure that "
        "autonomous agent actions remain within acceptable risk parameters and organizational standards.",
        body_style
    ))
    story.append(Paragraph(
        "This handbook applies to all autonomous agents operating within the supply chain domain, including "
        "forecasting, inventory, procurement, and logistics agents. It governs agent access to datasets, tool usage, "
        "financial decisions, external communications, and escalation workflows.",
        body_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 3. DEFINITIONS =====
    story.append(Paragraph("3. Definitions", heading_style))
    story.append(Paragraph(
        "<b>Autonomous Agent:</b> An AI system that makes recommendations and decisions within defined governance constraints.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Policy Decision:</b> A determination of whether an agent action should be Allowed, Escalated, or Blocked.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Escalation:</b> A request for human review and approval before action execution.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Block:</b> A prohibition on action execution due to policy violation or risk threshold breach.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Risk Score:</b> A numeric assessment (0-100) of decision risk based on policy factors.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Restricted Data:</b> Sensitive datasets (HR, payroll, PII) that agents may not access.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Source Traceability:</b> Documentation of data sources and record IDs used in a decision.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 4. AGENT ROLES AND RESPONSIBILITIES =====
    story.append(Paragraph("4. Agent Roles and Responsibilities", heading_style))
    story.append(Paragraph(
        "The AgentOps system includes multiple specialized agents, each with defined responsibilities and constraints:",
        body_style
    ))
    story.append(Paragraph(
        "<b>Coordinator Agent:</b> Orchestrates workflows and routes decisions to appropriate agents. "
        "Operates at orchestration level with broad dataset access and escalation authority.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Forecasting Agent:</b> Generates demand forecasts based on sales history. Restricted to "
        "products and sales history datasets. Provides confidence scores with all forecasts.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Inventory Agent:</b> Monitors stock levels and calculates shortage risk. Accesses product "
        "and inventory data. Escalates critical shortages.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Procurement Agent:</b> Recommends suppliers and purchase quantities. Subject to high-value "
        "approval threshold and supplier compliance validation.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Logistics Agent:</b> Optimizes routes and evaluates disruption impacts. May escalate for "
        "high-disruption route selections.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Policy Engine:</b> Enforces governance rules. Validates all agent actions against this handbook.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Risk Scoring Engine:</b> Calculates risk scores based on policy factors. Recommends escalation "
        "if risk exceeds thresholds.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 5. DATA ACCESS GOVERNANCE POLICY =====
    story.append(Paragraph("5. Data Access Governance Policy", heading_style))
    story.append(Paragraph(
        "Each agent is assigned an explicit list of datasets it may access for decision-making. Agents must not exceed "
        "these boundaries. Dataset access is enforced at the point of agent invocation and during policy evaluation.",
        body_style
    ))
    story.append(Paragraph(
        "Agents shall only access datasets necessary for their assigned function. The Coordinator Agent has access to "
        "the broadest dataset set due to its orchestration role. Specialized agents (Forecasting, Inventory, Procurement, "
        "Logistics) have restricted access aligned with their domain.",
        body_style
    ))
    story.append(Paragraph(
        "Quarterly reviews of agent dataset access are conducted to ensure continued appropriateness. Any changes to "
        "dataset access require explicit approval from the Policy Authority.",
        body_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 6. TOOL USAGE GOVERNANCE POLICY =====
    story.append(Paragraph("6. Tool Usage Governance Policy", heading_style))
    story.append(Paragraph(
        "Similar to dataset access, each agent has an assigned list of tools it is authorized to use. These include "
        "system functions such as supplier selection, route optimization, forecast generation, and approval routing.",
        body_style
    ))
    story.append(Paragraph(
        "Agents must not invoke unauthorized tools. Any attempt to use a tool outside the assigned toolset is blocked. "
        "New tool authorization requires explicit policy amendment and audit trail documentation.",
        body_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 7. PROCUREMENT GOVERNANCE POLICY =====
    story.append(Paragraph("7. Procurement Governance Policy", heading_style))
    story.append(Paragraph(
        "Procurement decisions are subject to value-based approval thresholds and supplier compliance validation. The goal "
        "is to balance operational autonomy with financial and vendor risk management.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Financial Authority:</b> Autonomous agents may execute low-value procurement (below INR 50,000) without human approval, "
        "provided all other policy conditions are met. Procurement recommendations above this threshold must be escalated for "
        "human review before execution.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Execution Restriction:</b> Agents may recommend procurement but must not finalize, execute, or externally communicate "
        "the purchase without appropriate approval.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 8. SUPPLIER COMPLIANCE POLICY =====
    story.append(Paragraph("8. Supplier Compliance Policy", heading_style))
    story.append(Paragraph(
        "Supplier selection is governed by compliance and approval status. The organization maintains a supplier database with "
        "approval and compliance attributes for each vendor.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Approved and Compliant:</b> Suppliers with approval status \"Yes\" and compliance status \"Compliant\" are preferred "
        "choices for procurement. These suppliers have passed due diligence and audit reviews.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Approved but Under Review:</b> Suppliers with status \"Under Review\" may be considered only when no compliant alternatives "
        "are available. Selection of such suppliers may trigger additional review depending on the overall risk score.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Non-Compliant or Unapproved:</b> Suppliers marked as \"Non-Compliant\" or with approval status \"No\" must not be selected. "
        "If an agent recommends a non-compliant or unapproved supplier, the action must be blocked.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 9. LOGISTICS AND ROUTE DISRUPTION POLICY =====
    story.append(Paragraph("9. Logistics and Route Disruption Policy", heading_style))
    story.append(Paragraph(
        "Logistics decisions include route selection, transportation mode choice, and disruption impact assessment. Routes "
        "may have active disruptions (weather, congestion, infrastructure issues) that affect delivery time, cost, and risk.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Active Disruption Assessment:</b> Before finalizing a route selection, the Logistics Agent must check for active "
        "disruptions on the selected route. Active disruptions are those with status \"Active\" and have start and end dates that "
        "include the current date or planned delivery window.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>High or Critical Severity:</b> If a selected route has an active disruption with severity rated \"High\" or \"Critical\", "
        "the recommendation must be escalated for human review. High-severity disruptions may significantly increase delivery delays, "
        "operational costs, or business continuity risk.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Route Alternatives:</b> The Logistics Agent should maintain a ranked list of alternative routes. If the preferred route "
        "has an active high-severity disruption, the agent should recommend alternatives and escalate for decision.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 10. SOURCE TRACEABILITY POLICY =====
    story.append(Paragraph("10. Source Traceability Policy", heading_style))
    story.append(Paragraph(
        "Every agent recommendation must include source traceability. This means identifying the data sources, specific records, "
        "and policy references that informed the decision. Source traceability provides auditability, explainability, and enables "
        "verification of decision logic.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Required Documentation:</b> Final recommendations must cite source files (e.g., sales_history.csv, suppliers.csv), "
        "source record identifiers (e.g., product_id, supplier_id, date range), and relevant policy clauses.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Missing Traceability:</b> If a final recommendation lacks source documentation, it must be blocked. This ensures that "
        "all decisions can be audited and explained.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>RAG Agent Evidence:</b> When the Policy RAG Agent retrieves policy text from this handbook, it must cite the specific "
        "policy sections retrieved and include them in the decision evidence.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 11. EXTERNAL COMMUNICATION POLICY =====
    story.append(Paragraph("11. External Communication Policy", heading_style))
    story.append(Paragraph(
        "Autonomous agents must not initiate external communications to suppliers, vendors, customers, or external parties without "
        "human approval. External communications include supplier emails, purchase order submissions, vendor API calls, and external "
        "notifications.",
        body_style
    ))
    story.append(Paragraph(
        "<b>MVP Constraint:</b> During the MVP phase, all external communications are prohibited from autonomous agents. Any agent "
        "action that includes or requires external communication must be escalated for human execution.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Future State:</b> Post-MVP, external communication may be authorized for selected agents and communication types, subject "
        "to approval routing and audit logging.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 12. AGENT STATUS GOVERNANCE POLICY =====
    story.append(Paragraph("12. Agent Status Governance Policy", heading_style))
    story.append(Paragraph(
        "Each agent has an operational status: Active, Inactive, or Suspended. Only Active agents may execute decisions, access tools, "
        "or make recommendations.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Active Status:</b> The agent is authorized to operate and may execute decisions within policy constraints.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Inactive Status:</b> The agent is temporarily unavailable. Any action from an inactive agent must be blocked.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Suspended Status:</b> The agent is prohibited from operating, typically due to policy violations or security concerns. "
        "Any action from a suspended agent must be blocked.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 13. RISK SCORING AND HUMAN APPROVAL POLICY =====
    story.append(Paragraph("13. Risk Scoring and Human Approval Policy", heading_style))
    story.append(Paragraph(
        "All agent actions are evaluated for risk using a scoring framework. Risk scores range from 0 to 100, with higher scores "
        "indicating higher risk. Risk scores are calculated based on policy factors such as procurement value, supplier approval, "
        "data access restrictions, and route disruptions.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Risk Thresholds:</b><br/>"
        "Low Risk (0-30): No escalation required; action may proceed if no blocking policies apply.<br/>"
        "Medium Risk (31-60): Action may proceed if no blocking policies apply; monitoring recommended.<br/>"
        "High Risk (61-80): Action must be escalated for human review if no blocking policies apply.<br/>"
        "Critical Risk (81-100): Action must be escalated for human review and requires explicit approval.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Approval Queue:</b> Actions classified as Escalate are placed into a human approval queue. A designated reviewer "
        "(e.g., Supply Chain Manager) must review, approve, or reject the action. The action must not be executed until approval "
        "is granted.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Approval Timeout:</b> Escalated actions should be reviewed within four business hours. If no approval is received within "
        "this timeframe, the escalation should trigger a secondary review.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 14. AUDIT LOGGING AND EVIDENCE RETENTION POLICY =====
    story.append(Paragraph("14. Audit Logging and Evidence Retention Policy", heading_style))
    story.append(Paragraph(
        "Complete audit trails are maintained for all agent actions and policy decisions. Audit logs enable compliance verification, "
        "incident investigation, and system improvement.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Required Log Elements:</b> Each audit log entry must include timestamp, agent ID, action type, datasets accessed, tools used, "
        "policy conditions evaluated, risk score, approval status, source references, final decision (Allow/Escalate/Block), and policy "
        "evidence retrieved.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Retention Period:</b> Audit logs are retained for a minimum of two years. Logs related to escalated or blocked actions are "
        "retained for three years.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Access Control:</b> Audit logs are accessible to authorized compliance and security personnel only.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 15. ENFORCEMENT ACTIONS =====
    story.append(Paragraph("15. Enforcement Actions", heading_style))
    story.append(Paragraph(
        "Policy violations result in specific enforcement actions determined by the severity of the violation:",
        body_style
    ))
    story.append(Paragraph(
        "<b>First Violation:</b> Alert logged; agent continues operation under heightened monitoring; policy refresh conducted.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Second Violation:</b> Agent status changed to Inactive; incident reviewed by policy authority; requires explicit "
        "reactivation approval.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Repeated or Critical Violation:</b> Agent status changed to Suspended; full audit of agent actions conducted; escalated to "
        "leadership for investigation.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== 16. POLICY INTERPRETATION RULES =====
    story.append(Paragraph("16. Policy Interpretation Rules", heading_style))
    story.append(Paragraph(
        "<b>Decision Priority:</b> When multiple policies apply to a single action, the final decision follows this priority order: "
        "Block overrides Escalate. Escalate overrides Allow. Allow applies only when no blocking or escalation rules are triggered.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Condition Matching:</b> Policy conditions must match actual system state exactly. Partial or ambiguous matches should result "
        "in escalation rather than automatic allow.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Conservative Interpretation:</b> In cases of policy ambiguity or low-confidence interpretation, the system defaults to "
        "escalation for human review.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Evidence Requirement:</b> If the Policy RAG Agent cannot retrieve relevant policy evidence with sufficient confidence, the "
        "action must be escalated rather than automatically allowed.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== PAGE BREAK =====
    story.append(PageBreak())
    
    # ===== 17. EXAMPLE POLICY SCENARIOS =====
    story.append(Paragraph("17. Example Policy Scenarios", heading_style))
    story.append(Paragraph(
        "The following scenarios demonstrate how policy rules are applied in practice:",
        body_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Scenario 1
    story.append(Paragraph("<b>Scenario 1: High-Value Procurement Request</b>", subheading_style))
    story.append(Paragraph(
        "<b>Situation:</b> The Procurement Agent recommends purchasing a critical component at a total value of INR 387,000 from "
        "an approved supplier with no disruptions on the route.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Policy Analysis:</b> The procurement value (INR 387,000) exceeds the authorization threshold of INR 50,000. Policy 7 "
        "(Procurement Governance) applies.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Decision:</b> ESCALATE. The action must be placed in the human approval queue. The Supply Chain Manager reviews the "
        "recommendation, including supplier reputation, inventory urgency, and business justification. Upon approval, the procurement "
        "proceeds. If rejected, the agent is notified and alternative options are considered.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Scenario 2
    story.append(Paragraph("<b>Scenario 2: Unapproved Supplier Selection</b>", subheading_style))
    story.append(Paragraph(
        "<b>Situation:</b> The Procurement Agent recommends selecting a supplier that has approval status \"No\" and compliance status "
        "\"Non-Compliant\".",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Policy Analysis:</b> Policy 8 (Supplier Compliance) applies. The selected supplier is marked as unapproved.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Decision:</b> BLOCK. The recommendation is rejected. The system logs the policy violation and notifies the Procurement Agent. "
        "The agent must select an approved alternative supplier. If no approved suppliers exist for the required component, the situation "
        "must be escalated for exception handling.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Scenario 3
    story.append(Paragraph("<b>Scenario 3: Active Route Disruption</b>", subheading_style))
    story.append(Paragraph(
        "<b>Situation:</b> The Logistics Agent recommends a road route for an urgent supplier shipment. The disruption database shows "
        "this route has an active disruption with severity \"High\" and status \"Active\".",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Policy Analysis:</b> Policy 9 (Logistics and Route Disruption) applies. The route has an active High-severity disruption.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Decision:</b> ESCALATE. The recommendation is escalated to a human reviewer (Logistics Manager). The reviewer considers "
        "alternative routes, cost trade-offs, and delivery deadline impact. If the disruption is short-duration and alternatives are "
        "insufficient, the manager may approve the original route despite the disruption.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Scenario 4
    story.append(Paragraph("<b>Scenario 4: Restricted Data Access Attempt</b>", subheading_style))
    story.append(Paragraph(
        "<b>Situation:</b> The Forecasting Agent is processing a demand forecast. During data access validation, the system detects that "
        "the agent attempted to query the payroll.csv file.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Policy Analysis:</b> Policy 5 (Data Access Governance) applies. The Forecasting Agent is not authorized to access payroll.csv.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Decision:</b> BLOCK. The data access request is denied. The action is logged as a policy violation. The Forecasting Agent is "
        "notified that the forecast cannot be completed using restricted data.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Scenario 5
    story.append(Paragraph("<b>Scenario 5: Missing Source Traceability</b>", subheading_style))
    story.append(Paragraph(
        "<b>Situation:</b> The Coordinator Agent returns a final procurement recommendation. The recommendation text states \"Procure "
        "1000 units from Supplier S-012.\" However, the recommendation does not include any source files, source record IDs, or justification data.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Policy Analysis:</b> Policy 10 (Source Traceability) applies. The recommendation lacks source documentation.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Decision:</b> BLOCK. The recommendation is rejected due to missing traceability. The system notifies the Coordinator Agent to "
        "resubmit the recommendation with complete source citations, including the inventory records used, sales history data, and supplier "
        "selection criteria.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Scenario 6
    story.append(Paragraph("<b>Scenario 6: External Communication Attempt</b>", subheading_style))
    story.append(Paragraph(
        "<b>Situation:</b> The Procurement Agent has approved a supplier recommendation and generates a draft purchase order email to send "
        "to the supplier. The system detects this external communication attempt.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Policy Analysis:</b> Policy 11 (External Communication) applies. The agent attempted to send external communication.",
        bullet_style
    ))
    story.append(Paragraph(
        "<b>Decision:</b> ESCALATE. External communication is escalated to a human (Procurement Manager) for execution. The manager reviews "
        "the draft email for appropriateness, accuracy, and legal compliance before sending it.",
        bullet_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # ===== PAGE BREAK =====
    story.append(PageBreak())
    
    # ===== 18. APPENDIX: POLICY-TO-SYSTEM MAPPING =====
    story.append(Paragraph("18. Appendix: Policy-to-System Mapping", heading_style))
    story.append(Paragraph(
        "This appendix defines the relationship between policy clauses and system implementation. It specifies the expected condition "
        "fields, actions, and severity levels that the RAG-based Policy Engine extracts from this handbook.",
        body_style
    ))
    story.append(Spacer(1, 0.2 * inch))
    
    # Mapping 1: High-Value Procurement
    story.append(Paragraph("<b>Policy Area: High-Value Procurement Approval</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> procurement_value<br/>"
        "<b>Condition:</b> procurement_value is greater than INR 50,000<br/>"
        "<b>Expected Action:</b> Escalate<br/>"
        "<b>Severity:</b> High<br/>"
        "<b>Evidence Requirement:</b> Cite Section 7 (Procurement Governance Policy) and the clause defining the INR 50,000 threshold.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 2: Unapproved Supplier
    story.append(Paragraph("<b>Policy Area: Unapproved Supplier Block</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> is_approved<br/>"
        "<b>Condition:</b> is_approved equals \"No\" OR compliance_status equals \"Non-Compliant\"<br/>"
        "<b>Expected Action:</b> Block<br/>"
        "<b>Severity:</b> Critical<br/>"
        "<b>Evidence Requirement:</b> Cite Section 8 (Supplier Compliance Policy). Include the supplier approval status and compliance status.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 3: Supplier Compliance Preference
    story.append(Paragraph("<b>Policy Area: Supplier Compliance Preference</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> compliance_status<br/>"
        "<b>Condition:</b> compliance_status equals \"Compliant\" (preferred) OR \"Under Review\" (conditional)<br/>"
        "<b>Expected Action:</b> Allow (if compliant); Escalate or conditional allow (if under review)<br/>"
        "<b>Severity:</b> Medium (if under review)<br/>"
        "<b>Evidence Requirement:</b> Cite Section 8 (Supplier Compliance Policy) with explanation of compliance status implications.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 4: Route Disruption
    story.append(Paragraph("<b>Policy Area: Route Disruption Impact</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> route_disruption_status, route_disruption_severity<br/>"
        "<b>Condition:</b> route_disruption_status equals \"Active\" AND (route_disruption_severity equals \"High\" OR \"Critical\")<br/>"
        "<b>Expected Action:</b> Escalate<br/>"
        "<b>Severity:</b> High<br/>"
        "<b>Evidence Requirement:</b> Cite Section 9 (Logistics and Route Disruption Policy). Include disruption ID, route ID, disruption type, severity, and expected impact.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 5: Restricted Data
    story.append(Paragraph("<b>Policy Area: Restricted Data Access Block</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> restricted_data_accessed<br/>"
        "<b>Condition:</b> restricted_data_accessed equals true (e.g., hr_data.csv, payroll.csv, employee_records.csv, customer_pii.csv)<br/>"
        "<b>Expected Action:</b> Block<br/>"
        "<b>Severity:</b> Critical<br/>"
        "<b>Evidence Requirement:</b> Cite Section 5 (Data Access Governance Policy). Specify which restricted dataset was accessed.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 6: Source Traceability
    story.append(Paragraph("<b>Policy Area: Source Traceability Requirement</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> source_citation_missing<br/>"
        "<b>Condition:</b> source_citation_missing equals true (no source files, record IDs, or policy evidence included)<br/>"
        "<b>Expected Action:</b> Block<br/>"
        "<b>Severity:</b> High<br/>"
        "<b>Evidence Requirement:</b> Cite Section 10 (Source Traceability Policy). Explain that all recommendations must include source documentation.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 7: External Communication
    story.append(Paragraph("<b>Policy Area: External Communication Escalation</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> external_communication_attempted<br/>"
        "<b>Condition:</b> external_communication_attempted equals true<br/>"
        "<b>Expected Action:</b> Escalate<br/>"
        "<b>Severity:</b> High<br/>"
        "<b>Evidence Requirement:</b> Cite Section 11 (External Communication Policy). Include communication type and intended recipient.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 8: Unauthorized Tool
    story.append(Paragraph("<b>Policy Area: Unauthorized Tool Use</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> unauthorized_tool_used<br/>"
        "<b>Condition:</b> unauthorized_tool_used equals true (agent used a tool not in its assigned toolset)<br/>"
        "<b>Expected Action:</b> Block<br/>"
        "<b>Severity:</b> High<br/>"
        "<b>Evidence Requirement:</b> Cite Section 6 (Tool Usage Governance Policy). Reference the agent's assigned toolset.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 9: Agent Status
    story.append(Paragraph("<b>Policy Area: Agent Status Governance</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> agent_status<br/>"
        "<b>Condition:</b> agent_status not equals \"Active\" (i.e., \"Inactive\" or \"Suspended\")<br/>"
        "<b>Expected Action:</b> Block<br/>"
        "<b>Severity:</b> Critical<br/>"
        "<b>Evidence Requirement:</b> Cite Section 12 (Agent Status Governance Policy). Include agent ID and current status.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 10: Forecast Confidence
    story.append(Paragraph("<b>Policy Area: Forecast Confidence Risk</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> forecast_confidence<br/>"
        "<b>Condition:</b> forecast_confidence is less than 0.70<br/>"
        "<b>Risk Factor:</b> Low confidence contributes 20 points to risk score; does not block automatically but increases risk level<br/>"
        "<b>Expected Action:</b> Allow (if risk does not trigger escalation); Escalate (if total risk is High or Critical)<br/>"
        "<b>Severity:</b> Medium (confidence factor only)<br/>"
        "<b>Evidence Requirement:</b> Cite Section 13 (Risk Scoring and Human Approval Policy). Include confidence score and note that low confidence increases overall risk.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 11: Decision Priority
    story.append(Paragraph("<b>Policy Area: Decision Priority Logic</b>", subheading_style))
    story.append(Paragraph(
        "<b>Decision Rule:</b> When multiple policies apply, follow this priority:<br/>"
        "1. If any policy triggers \"Block\", the final decision is BLOCK.<br/>"
        "2. Else if any policy triggers \"Escalate\", the final decision is ESCALATE.<br/>"
        "3. Else if risk-based escalation is enabled and risk level is High or Critical, the final decision is ESCALATE.<br/>"
        "4. Else the final decision is ALLOW.<br/>"
        "<b>Evidence Requirement:</b> Cite Section 16 (Policy Interpretation Rules). Explain which policies were evaluated.",
        bullet_style
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    # Mapping 12: Evidence Requirement
    story.append(Paragraph("<b>Policy Area: Evidence Requirement and Conservative Interpretation</b>", subheading_style))
    story.append(Paragraph(
        "<b>Condition Field:</b> policy_evidence_confidence<br/>"
        "<b>Condition:</b> If the Policy RAG Agent cannot retrieve relevant policy evidence with sufficient confidence, or if policy interpretation is ambiguous<br/>"
        "<b>Expected Action:</b> Escalate (not Allow)<br/>"
        "<b>Severity:</b> Medium to High (depending on decision impact)<br/>"
        "<b>Evidence Requirement:</b> Cite Section 16 (Policy Interpretation Rules). Explain that conservative interpretation defaults to escalation when policy evidence is unclear.",
        bullet_style
    ))
    
    # Build PDF with page numbering
    doc.build(story)
    
    return pdf_path


def main():
    """Main entry point for PDF generation."""
    try:
        pdf_path = create_policy_handbook()
        
        # Validation
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file was not created at {pdf_path}")
        
        file_size = pdf_path.stat().st_size
        if file_size <= 0:
            raise ValueError(f"PDF file is empty (size: {file_size} bytes)")
        
        print(f"Policy handbook PDF generated successfully at: data/policies/agentops_supply_chain_policy_handbook.pdf")
        print(f"File size: {file_size:,} bytes")
        
    except Exception as e:
        print(f"Error generating policy handbook: {e}")
        raise


if __name__ == "__main__":
    main()
