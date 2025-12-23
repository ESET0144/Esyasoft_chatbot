import ollama
from typing import Generator


# Map common or external model names to local ollama model IDs
MODEL_ALIASES = {
    "claude haiku 4.5": "gemma3",
    "claude:haiku-4.5": "gemma3",
    "claude": "gemma3",
    "haiku": "gemma3",
}


def _resolve_model_name(model: str) -> str:
    if not model:
        return "gemma3"
    key = model.strip().lower()
    return MODEL_ALIASES.get(key, model)


# Non-stream LLM call with alias resolution and fallback to gemma3
def call_llm(prompt: str, model: str = "gemma3") -> str:
    resolved = _resolve_model_name(model)
    try:
        response = ollama.generate(model=resolved, prompt=prompt)
        return response["response"].strip()
    except Exception as e:
        err = str(e)
        # If model not found, attempt fallback to gemma3 once
        if "not found" in err.lower() and resolved != "gemma3":
            try:
                response = ollama.generate(model="gemma3", prompt=prompt)
                return response["response"].strip()
            except Exception as e2:
                return f"LLM Error after fallback: {str(e2)}"
        return f"LLM Error: {err}"


# Streaming token output with alias resolution
def call_llm_stream(prompt: str, model: str = "gemma3") -> Generator[str, None, None]:
    resolved = _resolve_model_name(model)
    try:
        stream = ollama.generate(model=resolved, prompt=prompt, stream=True)
    except Exception as e:
        err = str(e)
        if "not found" in err.lower() and resolved != "gemma3":
            stream = ollama.generate(model="gemma3", prompt=prompt, stream=True)
        else:
            raise

    for chunk in stream:
        if "response" in chunk:
            yield chunk["response"]
