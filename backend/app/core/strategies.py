STRATEGIES = ["permalink", "add_to_cart", "checkout_direct", "human_handoff"]


def next_strategy(current: str | None) -> str:
    if not current or current not in STRATEGIES:
        return STRATEGIES[0]
    index = STRATEGIES.index(current)
    if index >= len(STRATEGIES) - 1:
        return STRATEGIES[-1]
    return STRATEGIES[index + 1]
