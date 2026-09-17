from functools import lru_cache


@lru_cache(maxsize=4096)
def format_quantity(value: int | float, unit: str) -> str:
    from quantiphy import Quantity

    return Quantity(value, unit).render(prec=4)
