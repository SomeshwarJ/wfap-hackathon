from langchain.tools import tool
from langchain.tools.base import BaseTool
from typing import List, Type
import json
from shared.utils import validate_signature, calculate_carbon_adjusted_rate
from shared.models import Intent
import random


class BaseMCPTools:
    """Base class for MCP tools that creates proper LangChain tools"""

    def __init__(self):
        self.tools = self._create_tools()

    def _create_tools(self) -> List[BaseTool]:
        """Create LangChain tools - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement _create_tools")

    def get_tools(self) -> List[BaseTool]:
        """Get the tools for LangGraph agent"""
        return self.tools

    def get_tools_descriptions(self) -> str:
        """Get tool descriptions for the prompt"""
        return "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])