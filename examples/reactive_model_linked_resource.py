"""
ReactiveModel example: editable state with Linked and async Resource.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Optional, Union

from reaktiv import (
    ReactiveModel,
    ResourceLoaderParams,
    ResourceStatus,
    computed,
    effect,
    field,
    linked,
    resource,
)

Product = dict[str, object]
ProductRequest = dict[str, Union[int, str]]

CATALOG: list[Product] = [
    {"id": 1, "name": "Notebook", "category": "office", "price": 12.50},
    {"id": 2, "name": "Desk lamp", "category": "office", "price": 39.00},
    {"id": 3, "name": "Trail backpack", "category": "outdoor", "price": 89.00},
    {"id": 4, "name": "Water bottle", "category": "outdoor", "price": 18.00},
    {"id": 5, "name": "Noise-canceling headphones", "category": "electronics", "price": 149.00},
]


def same_query_text(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()


def same_product_request(left: ProductRequest, right: ProductRequest) -> bool:
    return (
        str(left["query"]).strip().casefold()
        == str(right["query"]).strip().casefold()
        and left["category"] == right["category"]
        and int(left["limit"]) == int(right["limit"])
    )


async def fetch_products(
    query: str,
    category: str,
    limit: int,
    cancellation: asyncio.Event,
) -> list[Product]:
    print(f"fetch query={query!r} category={category!r} limit={limit}")
    await asyncio.sleep(0.2)

    if cancellation.is_set():
        return []

    matches = [
        product
        for product in CATALOG
        if query in str(product["name"]).lower()
        and (category == "all" or product["category"] == category)
    ]
    return matches[:limit]


class ProductSearch(ReactiveModel):
    committed_query = field("notebook")
    category = field("all")
    limit = field(3)

    def __init__(self) -> None:
        self.events: list[str] = []
        super().__init__()

    @linked[str](equal=same_query_text)
    def draft_query(self):
        return self.committed_query()

    @computed[str](equal=same_query_text)
    def normalized_query(self):
        return self.committed_query().strip().lower()

    @computed[ProductRequest](equal=same_product_request)
    def product_request(self):
        return {
            "query": self.normalized_query(),
            "category": self.category(),
            "limit": self.limit(),
        }

    @resource[ProductRequest, list[Product]]
    def products(self):
        return self.product_request()

    @products.loader
    async def load_products(
        self,
        params: ResourceLoaderParams[ProductRequest],
    ) -> list[Product]:
        request = params.params
        return await fetch_products(
            query=str(request["query"]),
            category=str(request["category"]),
            limit=int(request["limit"]),
            cancellation=params.cancellation,
        )

    @computed[str]
    def result_label(self):
        status = self.products.status()
        if status in {ResourceStatus.LOADING, ResourceStatus.RELOADING}:
            return "loading"
        if self.products.has_value():
            products = self.products.value() or []
            return f"{len(products)} result(s)"
        return status.value

    @effect
    def log_status(self, on_cleanup: Callable[[Callable[[], None]], None]) -> None:
        summary = self.result_label()
        line = (
            f"status={self.products.status().value} "
            f"draft={self.draft_query()!r} "
            f"committed={self.committed_query()!r} "
            f"summary={summary}"
        )
        self.events.append(line)
        print(line)

        on_cleanup(lambda: self.events.append(f"cleanup {summary}"))

    def submit_search(self) -> None:
        self.committed_query.set(self.draft_query())


def add_local_result(products: Optional[list[Product]]) -> list[Product]:
    current = list(products or [])
    current.append(
        {
            "id": 99,
            "name": "Local draft product",
            "category": "office",
            "price": 0.0,
        }
    )
    return current


async def wait_for_resolved(search: ProductSearch) -> None:
    while search.products.status() in {
        ResourceStatus.IDLE,
        ResourceStatus.LOADING,
        ResourceStatus.RELOADING,
    }:
        await asyncio.sleep(0.01)


async def main() -> None:
    search = ProductSearch()

    try:
        await wait_for_resolved(search)
        print(f"initial: {search.products.value()}")

        print("\nEdit the linked draft without reloading the resource:")
        search.draft_query.set("desk")
        search.draft_query.set("  DESK  ")
        await asyncio.sleep(0)
        print(f"draft={search.draft_query()!r}, committed={search.committed_query()!r}")

        print("\nCommit the draft, which updates Resource params:")
        search.submit_search()
        await wait_for_resolved(search)
        print(f"committed results: {search.products.value()}")

        print("\nChange another source signal:")
        search.category.set("office")
        await wait_for_resolved(search)
        print(f"office results: {search.products.value()}")

        print("\nSet a local optimistic Resource value:")
        search.products.update(add_local_result)
        print(f"local results: {search.products.value()}")

        print("\nReload from the async source:")
        search.products.reload()
        await wait_for_resolved(search)
        print(f"reloaded results: {search.products.value()}")
    finally:
        search.dispose()


if __name__ == "__main__":
    asyncio.run(main())
