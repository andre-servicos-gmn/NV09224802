"""Brand voice helpers."""


def build_brand_voice_block(brand_voice: str | None) -> str:
    """Return brand voice instructions for prompts."""
    voice = (brand_voice or "").strip()
    if not voice:
        return ""
    if voice == "curto_humano":
        return (
            "TOM DE VOZ DA MARCA: curto e humano. "
            "Use frases curtas, diretas e amigaveis."
        )
    return (
        f"TOM DE VOZ DA MARCA: {voice}. "
        "Aplique esse tom mantendo as regras acima."
    )
