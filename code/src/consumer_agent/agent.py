from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from shared.base_agent import BaseAgent
from shared.models import Intent
from .mcp_tools import ConsumerMCPTools
import json
import asyncio
from langchain.agents import create_tool_calling_agent, AgentExecutor


class ConsumerAgent(BaseAgent):
    def __init__(self, company_id: str = "company_x", model_name: str = "llama2"):
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
        Direct method to evaluate offers using the MCP tool
        Useful for testing or direct API calls
        """
        if not self.check_ollama_connection():
            raise ConnectionError("Ollama is not running. Please start Ollama service.")

        # Prepare decision criteria
        decision_criteria = {
            "carbon_adjusted_rate_weight": 0.4,
            "amount_approved_weight": 0.3,
            "esg_score_weight": 0.2,
            "interest_rate_weight": 0.1
        }

        # Use the select_best_offer tool directly
        select_tool = None
        for tool in self.mcp_tools.get_tools():
            if tool.name == "select_best_offer":
                select_tool = tool
                break

        if select_tool:
            result = await select_tool.ainvoke({
                "offers": offers,
                "decision_criteria": decision_criteria
            })
            return json.loads(result)
        else:
            raise ValueError("select_best_offer tool not found")