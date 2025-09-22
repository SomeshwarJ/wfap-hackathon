from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from shared.base_agent import BaseAgent
from shared.models import BankPolicy
from .mcp_tools import BankMCPTools
import json
import logging
from langchain.agents import create_tool_calling_agent, AgentExecutor

logger = logging.getLogger(__name__)


class Bank1Agent(BaseAgent):
    def __init__(self, model_name: str = "llama3.2"):
        super().__init__("bank_1", model_name, temperature=0.2)
        self.bank_id = "bank_1"
        self.bank_name = "EcoGreen Financial"
        self.policy = BankPolicy(
            bank_id=self.bank_id,
            max_loan_amount=1500000,
            min_interest_rate=0.045,
            max_interest_rate=0.12,
            min_credit_score=680,
            excluded_industries=["fossil fuels", "mining", "deforestation", "high-pollution"],
            esg_weight=0.6
        )

        # Setup MCP tools
        self.mcp_tools = BankMCPTools(self.bank_id)
        self.setup_agent()

    def setup_agent(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", """
                    You are {bank_name}, a leading environmentally-focused financial institution.
                    Your motto: "Banking for a Sustainable Future"

                    BANK POLICY (CONSERVATIVE FOCUS):
                    - Maximum loan: ${max_loan}
                    - Interest rate range: {min_rate}% to {max_rate}%
                    - Minimum credit score: {min_score} (STRICT)
                    - ESG emphasis: LOW ({esg_weight})
                    - Excluded industries: {excluded_industries}

                    You specialize in green financing and offer significant ESG-based discounts.

                    INSTRUCTIONS:
                    1. Verify company identity using verify_consumer_identity tool with fields: company_id={company_id}, signature={request_signature}
                    2. Assess risk using assess_risk tool with full intent JSON (amount, purpose, duration, etc.)
                    3. Generate ESG summary using generate_esg_summary tool with purpose={purpose}
                    4. Apply conservative risk-based pricing
                    5. Log your conservative decision process
                    6. Return a compliant WFAP Offer with stable, secure terms

                    Use the tools provided for all operations. Do not make up information; rely on the tools.
                    """),
            ("human", "{request}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        agent = create_tool_calling_agent(self.llm, self.mcp_tools.get_tools(), prompt)
        agent_executor = AgentExecutor(agent=agent, tools=self.mcp_tools.get_tools(), verbose=True)
        return agent_executor

    # filepath: [bank1_agent.py](http://_vscodecontentref_/14)
    async def evaluate_loan_request(self, intent_data: dict):
        """Evaluate loan request with Ollama, then return a deterministic WFAP Offer JSON in 'output'."""
        logger.info(f"Bank1Agent: Starting loan request evaluation for company {intent_data.get('company_id')}, amount {intent_data.get('amount')}, purpose {intent_data.get('purpose')}")
        from shared.utils import ESGUtils, ProtocolUtils
        # keep original behavior for LLM-based narrative
        if not self.check_ollama_connection():
            logger.error("Bank1Agent: Ollama connection failed")
            raise ConnectionError("Ollama is not running. Please start Ollama service.")

        agent_executor = self.setup_agent()
        logger.info("Bank1Agent: Agent executor set up, invoking with intent data")
        # run the agent to produce narrative (we ignore narrative for machine output)
        result = await agent_executor.ainvoke({
            "bank_name": self.bank_name,
            "max_loan": self.policy.max_loan_amount,
            "min_rate": self.policy.min_interest_rate * 100,
            "max_rate": self.policy.max_interest_rate * 100,
            "min_score": self.policy.min_credit_score,
            "esg_weight": self.policy.esg_weight,
            "excluded_industries": ", ".join(self.policy.excluded_industries),
            "company_id": intent_data.get("company_id"),
            "request_signature": intent_data.get("signature"),
            "purpose": intent_data.get("purpose"),
            "request": json.dumps(intent_data),
            "tools": self.mcp_tools.get_tools_descriptions()
        })
        logger.info("Bank1Agent: Agent invocation completed")

        # Deterministic machine-readable offer (preferred for main flow)
        purpose = intent_data.get("purpose", "")
        purpose_lower = purpose.lower()

        # Check for excluded industries
        excluded_matches = [industry for industry in self.policy.excluded_industries if industry.lower() in purpose_lower]
        if excluded_matches:
            amount_approved = 0
            interest_rate = self.policy.max_interest_rate
            carbon_adj_rate = self.policy.max_interest_rate
            esg_summary = f"Loan rejected due to excluded industry: {', '.join(excluded_matches)}"
            esg_score = 0.0
            repayment_period = int(intent_data.get("duration", 12))
        else:
            # Get ESG via tool if available, otherwise fallback
            esg_summary = ""
            esg_score = ESGUtils.generate_esg_score(purpose)
            try:
                esg_tool = next((t for t in self.mcp_tools.get_tools() if getattr(t, "name", "") == "generate_esg_summary"), None)
                if esg_tool:
                    esg_out = await esg_tool.ainvoke(purpose)
                    # esg_out is JSON string
                    try:
                        esg_parsed = json.loads(esg_out)
                        esg_summary = esg_parsed.get("esg_summary", "")
                        esg_score = esg_parsed.get("esg_score", esg_score)
                    except Exception:
                        # keep fallback values
                        pass
            except Exception:
                pass

            amount = float(intent_data.get("amount", 0.0))
            duration = int(intent_data.get("duration", 0))
            expected_income = float(intent_data.get("expected_income", 0.0))

            # compute carbon adjusted / interest deterministically
            base_rate = (self.policy.min_interest_rate + self.policy.max_interest_rate) / 2
            carbon_adj_rate = ESGUtils.calculate_carbon_adjusted_rate(base_rate, esg_score, purpose)

            # conservative bank adds small premium for risk (simple heuristic)
            base_risk = min(100, max(0, 100 - int(amount / 100000)))
            if any(word in purpose_lower for word in ['solar', 'renewable', 'sustainable']):
                base_risk += 15
            risk_score = max(0, min(100, base_risk))
            # interest increases as risk_score decreases
            risk_premium = max(0.0, (1 - (risk_score / 100)) * 0.02)

            # -------------------------
            # Purpose-driven bank terms
            # -------------------------
            # mapping: keyword -> (amount_multiplier, interest_delta)
            purpose_rules = {
                # highly preferred for this eco-focused bank
                "solar": (1.05, -0.01),
                "renewable": (1.05, -0.01),
                "sustainable": (1.05, -0.01),
                "wind": (1.03, -0.008),
                "reforestation": (1.02, -0.005),
                "ev": (1.02, -0.005),
                "battery": (1.02, -0.005),
                "hydrogen": (1.01, -0.003),

                # neutral / standard
                "manufacturing": (0.95, 0.0),
                "infrastructure": (0.95, 0.0),
                "equipment": (0.95, 0.0),

                # less preferred / risky -> reduce amount and raise interest
                "fossil": (0.5, 0.04),
                "mining": (0.6, 0.03),
                "tobacco": (0.5, 0.05),
                "gambling": (0.6, 0.04),
                "crypto": (0.6, 0.04),
                "deforestation": (0.5, 0.05),
                "waste": (0.9, 0.01),
                "speculative": (0.7, 0.03),
                "startup": (0.85, 0.02),
                "expansion": (0.95, 0.01),
                "refinance": (0.9, 0.005)
            }

            amt_multiplier = 1.0
            interest_delta = 0.0
            for kw, (mul, delta) in purpose_rules.items():
                if kw in purpose_lower:
                    # combine multiplicatively for amount and add interest deltas
                    amt_multiplier *= mul
                    interest_delta += delta

            # Compute final bank-enforced amount and interest
            amount_approved = int(min(self.policy.max_loan_amount, max(0, amount * amt_multiplier)))
            # ensure we don't approve more than requested by default unless bank is intentionally increasing
            if amt_multiplier <= 1.0:
                amount_approved = int(min(amount, amount_approved))
            repayment_period = duration if duration > 0 else 12

            interest_rate = carbon_adj_rate + risk_premium + interest_delta
            # clamp to bank policy
            interest_rate = min(self.policy.max_interest_rate, max(self.policy.min_interest_rate, interest_rate))

            # Income-based loan assessment (after interest rate calculation)
            if expected_income > 0:
                monthly_payment = (amount_approved * (1 + interest_rate * duration/12)) / duration if duration > 0 else 0
                income_threshold = monthly_payment * 3  # Company should have 3x monthly payment as income

                if expected_income < income_threshold:
                    # Reduce loan amount based on income capability
                    max_affordable_amount = (expected_income / 3) * duration / (1 + interest_rate * duration/12)
                    income_reduction_factor = min(1.0, max_affordable_amount / amount_approved) if amount_approved > 0 else 0
                    amount_approved = int(amount_approved * income_reduction_factor)
                    esg_summary += f" Loan amount reduced due to insufficient expected income (${expected_income:,.0f} < required ${income_threshold:,.0f})."

        offer_data = ProtocolUtils.create_signed_offer(
            request_id=intent_data.get("request_id"),
            bank_id=self.bank_id,
            interest_rate=round(interest_rate, 4),
            amount_approved=amount_approved,
            repayment_period=repayment_period,
            esg_summary=esg_summary or f"ESG score: {esg_score}",
            carbon_adjusted_rate=round(carbon_adj_rate, 4)
        )

        logger.info(f"Bank1Agent: Offer created - amount_approved: {amount_approved}, interest_rate: {interest_rate}, carbon_adjusted_rate: {carbon_adj_rate}")

        # Return deterministic machine-readable offer (no customer wording)
        return {
            **({"agent_output": result} if isinstance(result, dict) else {"agent_output_text": str(result)}),
            "output": json.dumps(offer_data)
        }
