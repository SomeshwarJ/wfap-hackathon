from langchain_ollama import OllamaLLM
from langchain_ollama import ChatOllama
from langchain.chat_models import init_chat_model


class OllamaConfig:
    # Available Ollama models - user can choose or system can auto-select
    MODELS = {
        "llama3.1:latest": "llama3.1:latest",
        "llama3.2": "llama3.2"
    }

    DEFAULT_MODEL = "phi:latest"
    OLLAMA_BASE_URL = "http://localhost:11434"

    @staticmethod
    def get_llm(model_name: str = None, temperature: float = 0.7):
        """Get Ollama LLM instance"""
        model = model_name or OllamaConfig.DEFAULT_MODEL
        return ChatOllama(model=model)


    @staticmethod
    def get_chat_model(model_name: str = None, temperature: float = 0.7):
        """Get Ollama chat model instance"""
        model = model_name or OllamaConfig.DEFAULT_MODEL
        return ChatOllama(model=model)