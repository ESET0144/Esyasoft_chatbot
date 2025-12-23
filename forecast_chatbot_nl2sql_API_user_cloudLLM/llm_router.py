import os
from ollama import chat

# Optional: cloud example (OpenAI-style)
try:
    from openai import OpenAI
    openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    default_headers={
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Forecast-NL2SQL-Chatbot"
    }
)
except Exception:
    openai_client = None


MODEL_OLLAMA = "gpt-oss:20b"
MODEL_CLOUD = "gpt-4o-mini"   # example


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
        if openai_client is None:
            raise RuntimeError("Cloud LLM not configured")

        completion = openai_client.chat.completions.create(
            model=model or MODEL_CLOUD,
            messages=messages
        )
        return completion.choices[0].message.content.strip()

    raise ValueError(f"Unknown llm_mode: {llm_mode}")
