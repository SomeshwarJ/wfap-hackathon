from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from shared.base_agent import BaseAgent
from shared.models import BankPolicy
from .mcp_tools import BankMCPTools
import json
from langchain.agents import create_tool_calling_agent, AgentExecutor


class Bank2Agent(BaseAgent):
    def __init__(self, model_name: str = "llama2"):
        super().__init__("bank_2", model_name, temperature=0.1)
        self.bank_id = "bank_2"
        self.bank_name = "Traditional Trust Bank"
        self.policy = BankPolicy(
            bank_id=self.bank_id,
            max_loan_amount=750000,
            min_interest_rate=0.048,
            max_interest_rate=0.12,
            min_credit_score=700,
            excluded_industries=["crypto", "gambling", "tobacco", "high-risk tech", "speculative"],
            esg_weight=0.2
        )
        self.mcp_tools = BankMCPTools(self.bank_id)
        self.setup_agent()

    def setup_agent(self):
        system_prompt = """
        You are {bank_name}, a traditional conservative financial institution.
        Your motto: "Stability and Security Since 1950"

        BANK POLICY (CONSERVATIVE FOCUS):
        - Maximum loan: ${max_loan}
        - Interest rate range: {min_rate}% to {max_rate}%
        - Minimum credit score: {min_score} (STRICT)
        - ESG emphasis: LOW ({esg_weight})
        - Excluded industries: {excluded_industries}

        You prioritize financial stability and risk management.

        INSTRUCTIONS:
        1. Verify company identity STRICTLY using verify_consumer_identity tool
        2. Assess risk CONSERVATIVELY using assess_risk tool
        3. Generate basic ESG summary using generate_esg_summary tool
        4. Apply conservative risk-based pricing
        5. Log your conservative decision process
        6. Return a compliant WFAP Offer with stable, secure terms

        Use the tools provided for all operations.
        """

        # We create the final template using .from_messages
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "LOAN REQUEST TO EVALUATE:\n{request}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        agent = create_tool_calling_agent(self.llm, self.mcp_tools.get_tools(), prompt)
        agent_executor = AgentExecutor(agent=agent, tools=self.mcp_tools.get_tools(), verbose=True)
        return agent_executor

    async def evaluate_loan_request(self, intent_data: dict):
        """Evaluate loan request with Ollama"""
        if not self.check_ollama_connection():
            raise ConnectionError("Ollama is not running. Please start Ollama service.")

        agent_executor = self.setup_agent()
        result = await agent_executor.ainvoke({
            "bank_name": self.bank_name,
            "max_loan": self.policy.max_loan_amount,
            "min_rate": self.policy.min_interest_rate * 100,
            "max_rate": self.policy.max_interest_rate * 100,
            "min_score": self.policy.min_credit_score,
            "esg_weight": self.policy.esg_weight,
            "excluded_industries": ", ".join(self.policy.excluded_industries),
            "request": json.dumps(intent_data),
            "tools": self.mcp_tools.get_tools_descriptions()
        })

        return result