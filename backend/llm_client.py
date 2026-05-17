"""
LLM client abstraction layer.
Swap between Ollama (local/free), Groq (free tier), or OpenAI
by changing LLM_PROVIDER in your .env file.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def get_client() -> tuple[OpenAI, str]:
    """Return (client, model_name) based on LLM_PROVIDER env var."""
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    if provider == "ollama":
        client = OpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",  # required by SDK but unused by Ollama
        )
        model = os.getenv("OLLAMA_MODEL", "llama3.2")

    elif provider == "groq":
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
        )
        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    elif provider == "openai":
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}. Choose ollama, groq, or openai.")

    return client, model


def chat(
    messages: list[dict],
    system: str = "",
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str:
    """
    Send a chat request to the configured LLM provider.

    Args:
        messages:    List of {"role": "user"|"assistant", "content": "..."} dicts
        system:      Optional system prompt string
        temperature: 0.0 = deterministic, 1.0 = creative
        max_tokens:  Optional cap on response length. Pass a generous value
                     (e.g. 4096) when you want long-form output like a textbook
                     section; leave None to use the provider's default.

    Returns:
        The assistant's response as a plain string
    """
    client, model = get_client()

    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    kwargs: dict = {
        "model": model,
        "messages": full_messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content


def chat_json(
    messages: list[dict],
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str:
    """
    Like chat(), but requests JSON output.
    Lower temperature default for more consistent structured output.
    Always append JSON instruction to system prompt.
    """
    json_system = (system + "\n\nRespond ONLY with valid JSON. No markdown, no explanation.").strip()
    return chat(messages, system=json_system, temperature=temperature, max_tokens=max_tokens)
