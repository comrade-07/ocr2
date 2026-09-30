from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewCategory:
    key: str
    label: str
    record_label: str


REVIEW_CATEGORIES = (
    ReviewCategory("scope1", "Scope 1", "Record"),
    ReviewCategory("scope2", "Scope 2", "Invoice"),
    ReviewCategory("water", "Water", "Record"),
    ReviewCategory("waste", "Waste", "Record"),
)

REVIEW_CATEGORY_BY_KEY = {category.key: category for category in REVIEW_CATEGORIES}


def category_label(category_key: str) -> str:
    category = REVIEW_CATEGORY_BY_KEY.get(category_key)
    return category.label if category else category_key.replace("_", " ").title()


def valid_category_keys() -> tuple[str, ...]:
    return tuple(category.key for category in REVIEW_CATEGORIES)
