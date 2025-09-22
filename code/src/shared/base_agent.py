from langchain.agents import AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from shared.config import OllamaConfig


class BaseAgent:
    def __init__(self, agent_type: str, model_name: str = None, temperature: float = 0.7):
        self.agent_type = agent_type
        self.model_name = model_name
        self.temperature = temperature
        self.llm = OllamaConfig.get_llm(model_name, temperature)
        self.chat_model = OllamaConfig.get_chat_model(model_name, temperature)

    def check_ollama_connection(self):
        """Check if Ollama is running and available"""
        try:
            import requests
            response = requests.get(f"{OllamaConfig.OLLAMA_BASE_URL}/api/tags")
            return response.status_code == 200
        except:
            return False

    def get_available_models(self):
        """Get list of available Ollama models"""
        try:
            import requests
            response = requests.get(f"{OllamaConfig.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                return [model['name'] for model in response.json().get('models', [])]
            return []
        except:
            return []