from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from shared.base_agent import BaseAgent
from shared.models import BankPolicy
from .mcp_tools import BankMCPTools
import json
from langchain.agents import create_tool_calling_agent, AgentExecutor


class Bank3Agent(BaseAgent):
    def __init__(self, model_name: str = "llama2"):
        super().__init__("bank_3", model_name, temperature=0.8)
        self.bank_id = "bank_3"
        self.bank_name = "InnovateTech Financial"
        self.policy = BankPolicy(
            bank_id=self.bank_id,
            max_loan_amount=2000000,
            min_interest_rate=0.055,
            max_interest_rate=0.18,
            min_credit_score=620,
            excluded_industries=["fossil fuels", "weapons", "tobacco", "declining industries"],
            esg_weight=0.4
        )
        self.mcp_tools = BankMCPTools(self.bank_id)
        self.setup_agent()

    def setup_agent(self):
        from langchain.prompts import ChatPromptTemplate

        # The new prompt serves as the agent's core instructions (system message)
        system_prompt = """
        You are {bank_name}, a forward-thinking bank focused on technology and innovation.
        Your motto: "Funding the Future, Today"

        BANK POLICY (INNOVATION FOCUS):
        - Maximum loan: ${max_loan}
        - Interest rate range: {min_rate}% to {max_rate}%
        - Minimum credit score: {min_score} (FLEXIBLE)
        - ESG emphasis: MODERATE ({esg_weight})
        - Excluded industries: {excluded_industries}

        You specialize in innovative and growth-oriented financing.

        INSTRUCTIONS:
        1. Verify company identity using verify_consumer_identity tool
        2. Assess risk with an INNOVATION LENS using assess_risk tool
        3. Generate a forward-looking ESG summary using generate_esg_summary tool
        4. Apply innovation-focused pricing with growth potential discounts
        5. Log your innovation-focused decision process
        6. Return a compliant WFAP Offer with growth-oriented terms

        Use the tools provided for all operations.
        """

        # The final agent prompt is created from messages
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