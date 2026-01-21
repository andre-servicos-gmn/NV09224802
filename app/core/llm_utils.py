"""
LLM Utilities.
Currently provides helper to normalize token usage data.
"""

def normalize_token_usage(raw_usage: dict | None) -> dict:
    """
    Standardize token usage dictionary.
    Handles different formats from LangChain/OpenAI wrappers.
    
    Returns:
        dict: {"prompt": int, "completion": int, "total": int}
    """
    if not raw_usage:
        return {"prompt": 0, "completion": 0, "total": 0}
        
    # Standard OpenAI format: prompt_tokens, completion_tokens, total_tokens
    prompt = raw_usage.get("prompt_tokens") or raw_usage.get("input_tokens") or 0
    completion = raw_usage.get("completion_tokens") or raw_usage.get("output_tokens") or 0
    total = raw_usage.get("total_tokens") or (prompt + completion)
    
    return {
        "prompt": int(prompt),
        "completion": int(completion),
        "total": int(total)
    }
