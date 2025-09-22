from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from shared.base_agent import BaseAgent
from shared.models import Intent
from .mcp_tools import ConsumerMCPTools
import json
import asyncio
import logging
from langchain.agents import create_tool_calling_agent, AgentExecutor

logger = logging.getLogger(__name__)


class ConsumerAgent(BaseAgent):
    def __init__(self, company_id: str = "company_x", model_name: str = "llama3.2"):
        super().__init__("consumer", model_name, temperature=0.3)
        self.company_id = company_id

        # Setup MCP tools
        self.mcp_tools = ConsumerMCPTools()
        self.setup_agent()

    def setup_agent(self):
        system_prompt = """
        You are a Consumer AI Agent acting as a CFO for {company_id}.
        Your role is to negotiate the best line of credit terms from banks.

        Follow WFAP protocol strictly. Always use MCP tools for:
        - Identity verification
        - Protocol validation
        - Trace logging
        - Offer selection and decision reasoning

        Decision criteria (in order of priority):
        1. Lowest carbon-adjusted interest rate (most important)
        2. Best financial terms (amount approved, repayment period)
        3. Highest ESG compliance and clear ESG summary

        INSTRUCTIONS:
        1. First, get the loan offer from all three banks using the get_bank_loan_offer tool.
        2. Next, validate each of the received offers using the validate_offer tool.
        3. Once all offers are gathered and validated, use the select_best_offer tool to choose the optimal offer, providing it with the complete list of offers.
        4. Log your final decision process using the log_consumer_trace tool.
        5. Present the final, reasoned decision from the select_best_offer tool to the user.

        You are communicating with three different banks:
        - Bank 1: EcoGreen Financial (ESG-focused, green projects)
        - Bank 2: Traditional Trust Bank (conservative, risk-averse)
        - Bank 3: InnovateTech Financial (tech-focused, innovation)
        """

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{task}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        agent = create_tool_calling_agent(self.llm, self.mcp_tools.get_tools(), prompt)
        agent_executor = AgentExecutor(agent=agent, tools=self.mcp_tools.get_tools(), verbose=True)
        return agent_executor

    async def process_loan_request(self, amount: float, duration: int, purpose: str):
        """Main method to handle loan request from user"""
        # Check Ollama connection first
        if not self.check_ollama_connection():
            raise ConnectionError("Ollama is not running. Please start Ollama service.")

        # Create intent using our utils
        from shared.utils import create_signed_intent
        intent_data = create_signed_intent(self.company_id, amount, duration, purpose)

        # Use MCP tools via LLM orchestration with Ollama
        agent_executor = self.setup_agent()
        result = await agent_executor.ainvoke({
            "task": f"Process loan request: ${amount:,.0f} for {duration} months, purpose: {purpose}",
            "company_id": self.company_id,
            "tools": self.mcp_tools.get_tools_descriptions()
        })

        return result

    async def evaluate_offers(self, offers: list) -> dict:
        """
        Direct method to evaluate offers using the MCP tool (robustified).
        - Accepts offers as dicts, JSON strings, or free text containing a JSON object.
        - Sanitizes numeric fields and applies safe defaults/penalties.
        - Calls the 'select_best_offer' tool and returns parsed JSON results.
        """
        import re

        logger.info(f"ConsumerAgent: Starting offer evaluation with {len(offers)} offers")
        if not self.check_ollama_connection():
            logger.error("ConsumerAgent: Ollama connection failed")
            raise ConnectionError("Ollama is not running. Please start Ollama service.")

        # Prepare decision criteria
        decision_criteria = {
            "carbon_adjusted_rate_weight": 0.4,
            "amount_approved_weight": 0.3,
            "esg_score_weight": 0.2,
            "interest_rate_weight": 0.1,
            # you can pass "accept_threshold" here if you want to tune acceptance
        }

        # Find the select_best_offer tool
        select_tool = None
        for tool in self.mcp_tools.get_tools():
            # .name should match the decorated function name in ConsumerMCPTools
            if getattr(tool, "name", "") == "select_best_offer":
                select_tool = tool
                break

        if not select_tool:
            raise ValueError("select_best_offer tool not found")

        # Helper: try to parse strings or find the first JSON object
        def try_parse_offer(raw):
            if isinstance(raw, dict):
                return raw
            if not isinstance(raw, str):
                return None
            try:
                return json.loads(raw)
            except Exception:
                m = re.search(r'\{.*\}', raw, flags=re.DOTALL)
                if m:
                    try:
                        return json.loads(m.group(0))
                    except Exception:
                        return None
                return None

        # Sanitize offers
        sanitized = []
        parse_errors = []
        for idx, o in enumerate(offers or []):
            parsed = try_parse_offer(o)
            if parsed is None:
                # if it's a string that isn't json, keep original string for diagnostics
                parse_errors.append({"index": idx, "raw": o, "reason": "couldn't parse into JSON/dict"})
                continue

            # Normalise expected fields with safe defaults
            try:
                bank_id = parsed.get("bank_id")
                offer_id = parsed.get("offer_id")
                carbon_adj = parsed.get("carbon_adjusted_rate", parsed.get("carbon_rate", 1.0))
                amount = parsed.get("amount_approved", parsed.get("amount", 0.0))
                interest = parsed.get("interest_rate", parsed.get("rate", 100.0))
                esg_summary = parsed.get("esg_summary", parsed.get("esg", "")) or ""
                repayment_period = parsed.get("repayment_period", parsed.get("duration", 0))

                # safe casting
                carbon_adj = float(carbon_adj) if carbon_adj is not None else 1.0
                amount = float(amount) if amount is not None else 0.0
                interest = float(interest) if interest is not None else 100.0
                repayment_period = int(repayment_period) if repayment_period is not None else 0

                # apply simple bounds / penalties (keeps values valid for scoring)
                if carbon_adj <= 0:
                    carbon_adj = 1.0
                if interest <= 0:
                    interest = 100.0
                if amount < 0:
                    amount = 0.0

                sanitized.append({
                    "offer_id": offer_id,
                    "bank_id": bank_id,
                    "carbon_adjusted_rate": carbon_adj,
                    "amount_approved": amount,
                    "interest_rate": interest,
                    "esg_summary": esg_summary,
                    "repayment_period": repayment_period,
                    # keep original raw for traceability
                    "_raw": parsed
                })
            except Exception as e:
                parse_errors.append({"index": idx, "raw": o, "reason": f"sanitization error: {e}"})
                continue

        if not sanitized:
            return {"error": "No valid offers after sanitization", "parse_errors": parse_errors}

        # Call the tool; the tool may return a JSON string or a dict
        try:
            tool_input = {"offers": sanitized, "decision_criteria": decision_criteria}
            raw_result = await select_tool.ainvoke(tool_input)
        except Exception as e:
            # try calling synchronous invoke if async fails
            try:
                raw_result = select_tool.invoke(tool_input)
            except Exception as e2:
                return {"error": f"Tool invocation failed: {e}", "invoke_error": str(e2), "parse_errors": parse_errors}

        # Parse tool response safely
        if isinstance(raw_result, str):
            try:
                parsed_result = json.loads(raw_result)
            except Exception:
                # tool returned non-json text: return raw plus diagnostics
                parsed_result = {"raw_text": raw_result}
        elif isinstance(raw_result, dict):
            parsed_result = raw_result
        else:
            # unknown type
            parsed_result = {"result": str(raw_result)}

        # Attach sanitization diagnostics for debugging
        parsed_result.setdefault("parse_errors", parse_errors)
        parsed_result.setdefault("sanitized_offers_count", len(sanitized))

        selected_offer = parsed_result.get('selected_offer', {})
        logger.info(f"ConsumerAgent: Offer evaluation completed - selected bank: {selected_offer.get('bank_id')}, total_score: {parsed_result.get('total_score')}")

        return parsed_result
