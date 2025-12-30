import os
from ollama import chat
from openai import OpenAI


MODEL_OLLAMA = "gpt-oss:20b"
MODEL_CLOUD = "google/gemma-3-27b-it:free"   # example

def get_openai_client():
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        default_headers={
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Forecast-NL2SQL-Chatbot"
        }
    )

def run_llm(messages, llm_mode="ollama", model=None) -> str:
    """
    Unified LLM runner.
    Returns ONLY text content (string).
    """

    if llm_mode == "ollama":
        resp = chat(
            model=model or MODEL_OLLAMA,
            messages=messages,
            stream=False
        )

        # Ollama SDK response handling
        if isinstance(resp, dict):
            return resp.get("message", {}).get("content", "").strip()

        return str(resp)

    # ---------- CLOUD ----------
    if llm_mode == "cloud":
        client = get_openai_client()

        try:
            completion = client.chat.completions.create(
                model=model or MODEL_CLOUD,
                messages=messages
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            return f"Cloud LLM Error: {str(e)}"

    raise ValueError(f"Unknown llm_mode: {llm_mode}")
