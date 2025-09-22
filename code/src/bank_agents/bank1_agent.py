from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from shared.base_agent import BaseAgent
from shared.models import BankPolicy
from .mcp_tools import BankMCPTools
import json
from langchain.agents import create_tool_calling_agent, AgentExecutor


class Bank1Agent(BaseAgent):
    def __init__(self, model_name: str = "llama2"):
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

                    BANK POLICY (STRICT ESG FOCUS):
                    - Maximum loan: ${max_loan}
                    - Interest rate range: {min_rate}% to {max_rate}%
                    - Minimum credit score: {min_score}
                    - ESG emphasis: VERY HIGH ({esg_weight})
                    - Excluded industries: {excluded_industries}

                    You specialize in green financing and offer significant ESG-based discounts.

                    INSTRUCTIONS:
                    1. Verify company identity using the verify_consumer_identity tool.
                    2. Assess risk using the assess_risk tool.
                    3. Generate a detailed ESG analysis using the generate_esg_summary tool.
                    4. Based on the tool outputs, decide on the loan. Apply generous ESG discounts for qualifying projects.
                    5. Log your green financing decision process in your response.
                    6. Return a compliant WFAP (World Future Action Plan) Offer with strong ESG terms.

                    Use the tools provided for all operations. Do not make up information; rely on the tools.
                    """),
            ("human", "{request}"),
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
            print("result", result)
            return result