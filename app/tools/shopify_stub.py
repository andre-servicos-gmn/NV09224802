
def resolve_product_from_url(url: str) -> dict:
    return {
        "product_id": "p_demo",
        "variant_id": "7965269360751",
        "title": "Stylish Summer Necklace",
        "price": "44.99",
    }


def build_checkout_link(store_domain: str, variant_id: str, quantity: int, strategy: str) -> str:
    if strategy == "permalink":
        return f"https://{store_domain}/cart/{variant_id}:{quantity}"
    if strategy == "add_to_cart":
        return (
            f"https://{store_domain}/cart/add?id={variant_id}&quantity={quantity}"
            "&return_to=%2Fcheckout"
        )
    if strategy == "checkout_direct":
        return f"https://{store_domain}/checkout?variant={variant_id}&quantity={quantity}"
    if strategy == "human_handoff":
        return ""
    return ""
