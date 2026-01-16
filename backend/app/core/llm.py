import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "gpt-5-mini"


def get_model_name() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


def generate_response(system_prompt: str, user_prompt: str) -> str:
    model = get_model_name()
    llm = ChatOpenAI(model=model, temperature=0.4)
    result = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    return (result.content or "").strip()
