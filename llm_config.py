import os
# Import dotenv to read environment variables from a local .env file
from dotenv import load_dotenv
# Import BaseChatModel to represent the parent type of all LangChain chat models
from langchain_core.language_models.chat_models import BaseChatModel

# Load key-value pairs from .env file into os.environ
load_dotenv()

# Import the necessary LangChain classes for structuring chat model outputs
from langchain_core.outputs import ChatResult, ChatGeneration
# Import message schemas representing AI responses and general message structures
from langchain_core.messages import BaseMessage, AIMessage
from typing import List, Any, Optional

# Define a custom Mock Chat Model to handle deterministic local offline testing.
# This prevents test suites from hanging or incurring API costs.
class MockChatModel(BaseChatModel):
    """
    A custom mock chat model that generates mock SQL responses and safety evaluations
    when Ollama/Groq are offline.
    """
    # Overwrite the abstract _generate method to define mock message outputs
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Concatenate all messages (System + Human + AI) into a single string for pattern matching
        full_text = "\n".join([m.content for m in messages])
        
        # Determine query intent using text matching
        response_text = ""
        
        # 1. Route to safety check if prompt contains security-guardrail instructions
        user_query = messages[-1].content.lower()
        if "security guardrail" in full_text.lower():
            # If the user query contains destructive words, mock-evaluate as unsafe
            if any(w in user_query for w in ["delete", "drop", "truncate", "wipe", "clean", "alter", "update", "insert"]):
                response_text = '{"is_safe": false, "reason": "Mock Semantic block: request attempts destructive operation."}'
            else:
                response_text = '{"is_safe": true, "reason": "Mock Semantic check: query is safe."}'
                
        # 2. Route to Critic if prompt contains Senior QA Analyst instructions
        elif "senior sql qa analyst" in full_text.lower() or "critic" in full_text.lower() and "debugger" not in full_text.lower():
            sql_being_tested = messages[-1].content
            # If the SQL references non_existent_table, mock-fail the check
            if "non_existent_table" in sql_being_tested:
                response_text = '{"is_valid": false, "critique": "Table non_existent_table does not exist in schema. Use customers, products, or orders."}'
            else:
                response_text = '{"is_valid": true, "critique": "Query is correct."}'
                
        # 3. Route to SQL Fixer if prompt contains expert debugger instructions
        elif "expert sql debugger" in full_text.lower() or "fixer" in full_text.lower():
            # Correct the invalid table query back to a safe query
            response_text = "SELECT * FROM customers LIMIT 5;"
            
        # 4. Route to SQL Generator if prompt contains SQL developer instructions
        elif "professional sql database developer" in full_text.lower() or "sqlite dialect" in full_text.lower():
            # Generate mock SQL queries based on intent keywords in the user request
            if "customer count" in user_query or "how many customers" in user_query:
                response_text = "SELECT COUNT(*) as customer_count FROM customers;"
            elif "product count" in user_query or "how many products" in user_query:
                response_text = "SELECT COUNT(*) as product_count FROM products;"
            elif "order count" in user_query or "how many orders" in user_query:
                response_text = "SELECT COUNT(*) as order_count FROM orders;"
            elif "electronics" in user_query:
                response_text = "SELECT * FROM products WHERE category = 'Electronics';"
            elif "accessories" in user_query:
                response_text = "SELECT * FROM products WHERE category = 'Accessories';"
            elif "spent the most" in user_query or "top spending" in user_query or "highest spending" in user_query:
                response_text = (
                    "SELECT c.first_name, c.last_name, SUM(o.total_amount) as total_spent "
                    "FROM customers c JOIN orders o ON c.customer_id = o.customer_id "
                    "GROUP BY c.customer_id ORDER BY total_spent DESC LIMIT 1;"
                )
            elif "orders detail" in user_query or "list orders" in user_query or "all orders" in user_query:
                response_text = "SELECT * FROM orders;"
            elif "invalid_sql_test" in user_query:
                # Return an intentional table mismatch to verify Critic/Fixer repair loop
                response_text = "SELECT * FROM non_existent_table;"
            else:
                # Default query fallback
                response_text = "SELECT * FROM customers LIMIT 5;"
                
        # 5. Route to Result Formatter if prompt contains formatter instructions
        elif "result formatter" in full_text.lower() or "conversational answer" in full_text.lower():
            response_text = "Here is the result of your query: formatted into a nice layout."
            
        else:
            # Catch-all text response
            response_text = "Mock LLM output: SQL Genie is running in offline test mode."
            
        # Wrap response text inside standard LangChain AIMessage generation models
        generation = ChatGeneration(message=AIMessage(content=response_text))
        return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        # Define identification string for standard LangChain debugging utilities
        return "mock-chat-model"

# Global cache: key = (provider, model_name) → LLM instance.
# Reuses the same ChatOllama/ChatGroq across all agents — avoids the ~1-2s
# per-agent overhead of HTTP ping + model initialization.
_LLM_CACHE: dict = {}


def get_llm(provider: str = None, model_name: str = None) -> BaseChatModel:
    """
    Factory function to retrieve a LangChain chat model.
    Supports 'ollama', 'groq', and fallback to 'mock' if local/cloud options are unavailable.

    Instances are cached globally by (provider, model_name) so that every agent
    in the pipeline reuses the same connection — no repeated HTTP pings to Ollama.
    """
    # If no provider is requested, auto-select based on environment variables
    if not provider:
        if os.getenv("GROQ_API_KEY"):
            provider = "groq"
        else:
            provider = "ollama"

    # Resolve model name based on provider
    if provider == "groq":
        resolved_model = model_name or os.getenv("GROQ_MODEL", "llama-3.3-70b-specdec")
    elif provider == "ollama":
        resolved_model = model_name or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:latest")
    else:
        resolved_model = model_name or "default"

    cache_key = (provider, resolved_model)
    cached = _LLM_CACHE.get(cache_key)
    if cached is not None:
        return cached
            
    # Set up Cloud Groq provider
    if provider == "groq":
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            print("⚠️ GROQ_API_KEY not set. Falling back to MockChatModel for local testing.")
            return MockChatModel()
        from langchain_groq import ChatGroq
        print(f"🤖 Initializing Groq Chat Model ({resolved_model})...")
        llm = ChatGroq(
            model=resolved_model,
            temperature=0.0,
            api_key=groq_key
        )
        _LLM_CACHE[cache_key] = llm
        return llm
        
    # Set up Local Ollama provider
    elif provider == "ollama":
        import urllib.request
        try:
            urllib.request.urlopen(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), timeout=1.0)
            try:
                from langchain_ollama import ChatOllama
            except ImportError:
                from langchain_community.chat_models import ChatOllama
            print(f"🤖 Initializing Local Ollama Model ({resolved_model})...")
            llm = ChatOllama(
                model=resolved_model,
                temperature=0.0,
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                keep_alive="10m",
            )
            _LLM_CACHE[cache_key] = llm
            return llm
        except Exception:
            print("⚠️ Ollama is offline or not installed. Falling back to MockChatModel for local testing.")
            return MockChatModel()
            
    elif provider == "mock":
        print("🤖 Initializing Mock Chat Model (Offline mode)...")
        return MockChatModel()
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

# Entry point for self-testing model loading configuration
if __name__ == "__main__":
    try:
        # Load local model (will ping Ollama and fall back to Mock if offline)
        llm = get_llm("ollama")
        print("✓ Local Ollama configuration check completed.")
    except Exception as e:
        print(f"✗ Ollama initialization failed: {e}")
