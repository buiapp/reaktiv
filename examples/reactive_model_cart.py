"""
ReactiveModel example: class-based reactive state.
"""

from reaktiv import ReactiveModel, batch, computed, effect, field, linked


def same_cent(left: float, right: float) -> bool:
    return round(left, 2) == round(right, 2)


def same_quantity_bucket(left: int, right: int) -> bool:
    return min(left, 10) == min(right, 10)


class ShoppingCart(ReactiveModel):
    item_name = field("Notebook")
    unit_price = field(12.50)
    quantity = field(2)
    coupon_percent = field(0.0)

    def __init__(self) -> None:
        self.audit_log: list[str] = []
        self.cleanup_log: list[str] = []
        super().__init__()

    @computed[float](equal=same_cent)
    def subtotal(self):
        return self.unit_price() * self.quantity()

    @computed[float](equal=same_cent)
    def discount(self):
        return self.subtotal() * self.coupon_percent()

    @computed[float](equal=same_cent)
    def total(self):
        return self.subtotal() - self.discount()

    @linked[int](equal=same_quantity_bucket)
    def selected_quantity(self):
        return self.quantity()

    @effect
    def audit_total(self):
        total = self.total()
        message = (
            f"{self.item_name()}: quantity={self.quantity()}, "
            f"selected={self.selected_quantity()}, total=${total:.2f}"
        )
        self.audit_log.append(message)
        print(message)

        return lambda: self.cleanup_log.append(f"closed audit view for ${total:.2f}")


def main() -> None:
    cart = ShoppingCart()

    print("\nUpdate a source signal:")
    cart.unit_price.set(15.00)

    print("\nBatch several related updates:")
    with batch():
        cart.quantity.set(3)
        cart.coupon_percent.set(0.10)

    print("\nOverride a linked signal manually:")
    cart.selected_quantity.set(10)
    cart.selected_quantity.set(12)
    print("quantity equality buckets 10 and 12 together, so no extra audit entry")

    print("\nChanging the source resets the linked signal:")
    cart.quantity.set(4)

    print("\nDispose model-owned effects:")
    cart.dispose()
    cart.unit_price.set(20.00)
    print(f"audit entries after dispose: {len(cart.audit_log)}")
    print(f"cleanup entries after dispose: {cart.cleanup_log}")


if __name__ == "__main__":
    main()
