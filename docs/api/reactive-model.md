# ReactiveModel API

`ReactiveModel` groups related reactive state and behavior into a normal Python
class. Every instance owns an independent graph of writable fields, computed
values, linked state, effects, and resources.

Use it when a graph represents an application concept such as a form, store,
view model, workflow, or service.

## Complete Example

```pyodide install="reaktiv" height="30" theme="github_light_default,github_dark"
from reaktiv import ReactiveModel, computed, effect, field


class ShoppingCart(ReactiveModel):
    unit_price = field(12.50)
    quantity = field(1)
    discount = field(0.0)

    @computed
    def subtotal(self) -> float:
        return self.unit_price() * self.quantity()

    @computed
    def total(self) -> float:
        return self.subtotal() * (1 - self.discount())

    @effect
    def show_total(self) -> None:
        print(f"{self.quantity()} item(s): ${self.total():.2f}")


cart = ShoppingCart()      # Prints: 1 item(s): $12.50
cart.quantity.set(3)       # Prints: 3 item(s): $37.50
cart.discount.set(0.10)    # Prints: 3 item(s): $33.75

cart.dispose()
```

The fields, formulas, and side effects stay together, while every
`ShoppingCart` instance receives an independent reactive graph.

## Fields

`field(default)` declares a writable `Signal` owned by each model instance:

```pyodide install="reaktiv" assets="no" height="22" theme="github_light_default,github_dark"
from reaktiv import ReactiveModel, field


class Cart(ReactiveModel):
    quantity = field(1)
    coupon = field("")


left = Cart(quantity=2)
right = Cart()

left.quantity.set(5)

print(left.quantity())   # 5
print(right.quantity())  # 1
```

Every field requires exactly one default value or a factory. Use a factory for
mutable defaults so each instance receives a new object:

```pyodide install="reaktiv" assets="no" height="18" theme="github_light_default,github_dark"
from reaktiv import ReactiveModel, field


class TodoModel(ReactiveModel):
    items = field[list[str]](factory=list)


left = TodoModel()
right = TodoModel()
left.items.update(lambda items: items + ["first"])

print(left.items())   # ["first"]
print(right.items())  # []
```

Types are inferred from defaults and annotated factories. Use `field[T]` when
the intended type is wider than the default:

```pyodide install="reaktiv" assets="no" height="18" theme="github_light_default,github_dark"
from typing import Optional
from reaktiv import ReactiveModel, field


class SearchModel(ReactiveModel):
    query = field("")
    selected_id = field[Optional[str]](None)
    history = field[list[str]](factory=list)
```

Constructor keyword values override defaults before eager effects and resources
start. Unknown field names raise `TypeError` instead of silently creating an
ordinary attribute.

## Constructors And Type Checking

The inherited constructor accepts declared fields by keyword:

```python
search = SearchModel(query="python")
```

Static type checkers cannot derive a precise constructor signature from class
descriptors. Add an explicit constructor when callers should get parameter
autocomplete and validation:

```python
class UserModel(ReactiveModel):
    name = field("")
    age = field(0)

    def __init__(self, name: str, age: int = 0) -> None:
        super().__init__(name=name, age=age)
```

Model effects and resources start during `ReactiveModel.__init__`. Set any
ordinary attributes they read before calling `super().__init__()`.

## Computed Values

Decorated methods become per-instance computed signals. Pyright infers the
computed value type from the method implementation:

```pyodide install="reaktiv" assets="no" height="18" theme="github_light_default,github_dark"
from reaktiv import ReactiveModel, computed, field


class Cart(ReactiveModel):
    price = field(10.0)
    quantity = field(2)

    @computed
    def total(self):
        return self.price() * self.quantity()


cart = Cart()
print(cart.total())  # 20.0
```

Use `computed[T]` when you want to provide the result type explicitly:

```pyodide install="reaktiv" assets="no" height="15" theme="github_light_default,github_dark"
from reaktiv import ReactiveModel, computed, field


class SearchModel(ReactiveModel):
    query = field(" Notebook ")

    @computed[str]
    def normalized_query(self):
        return self.query().strip().lower()


search = SearchModel()
print(search.normalized_query())  # notebook
```

Concrete types such as `computed[str]` and `computed[list[int]]` are supported.
Custom equality functions are supported with
`@computed(equal=...)` or `@computed[T](equal=...)`.

## Linked State

Use `linked` for state that starts from another signal, can be edited locally,
and resets when the source changes.

```pyodide install="reaktiv" assets="no" height="24" theme="github_light_default,github_dark"
from reaktiv import ReactiveModel, field, linked


class ProfileForm(ReactiveModel):
    server_name = field("Ada")

    @linked[str]
    def draft_name(self):
        return self.server_name()


form = ProfileForm()
form.draft_name.set("Grace")

print(form.draft_name())  # Grace

form.server_name.set("Linus")
print(form.draft_name())  # Linus
form.dispose()
```

`linked` also supports custom equality through `@linked(equal=...)` and
`@linked[T](equal=...)`.

## Effects And Cleanup

Model effects start eagerly and are retained by the model. Unlike standalone
effects, they do not need to be assigned to a separate variable. Return a
callable when the effect needs cleanup:

```pyodide install="reaktiv" assets="no" height="18" theme="github_light_default,github_dark"
from reaktiv import ReactiveModel, effect, field


class SessionModel(ReactiveModel):
    user_id = field("ada")

    @effect
    def subscribe(self):
        user_id = self.user_id()
        print(f"subscribe {user_id}")
        return lambda: print(f"unsubscribe {user_id}")


session = SessionModel()
session.user_id.set("grace")
session.dispose()
```

Cleanup runs before the effect reruns and when the model is disposed. An effect
can accept an `on_cleanup` registrar when it needs to register multiple cleanup
callbacks, but returning one callable is the simpler default.

## Async Resources

Use `resource` when data should reload automatically from reactive parameters.
A model with resources must be created while an asyncio event loop is running.

The first type argument describes the parameter value and the second describes
the loaded value.

```pyodide install="reaktiv" assets="no" height="40" theme="github_light_default,github_dark"
import asyncio

from reaktiv import (
    ReactiveModel,
    ResourceLoaderParams,
    ResourceStatus,
    effect,
    field,
    resource,
)


class UserStore(ReactiveModel):
    user_id = field("ada")

    @resource[dict[str, str], dict[str, str]]
    def user(self):
        return {"id": self.user_id()}

    @user.loader
    async def load_user(
        self,
        params: ResourceLoaderParams[dict[str, str]],
    ) -> dict[str, str]:
        await asyncio.sleep(0.1)
        user_id = params.params["id"]
        return {"id": user_id, "name": user_id.title()}


async def main() -> None:
    store = UserStore()
    finished = asyncio.Event()

    @effect
    def show_user() -> None:
        status = store.user.status()
        print(f"status: {status.value}")

        if status == ResourceStatus.RESOLVED:
            print(store.user.value())
            finished.set()
        elif status == ResourceStatus.ERROR:
            print(store.user.error())
            finished.set()

    try:
        await finished.wait()
    finally:
        show_user.dispose()
        store.dispose()


await main()
```

Changing `user_id` starts a new load. `dispose()` destroys model-owned resources
and cancels pending work.

## Lifecycle And Disposal

`ReactiveModel.dispose()`:

- disposes model-owned effects;
- runs their pending cleanup functions;
- destroys model-owned resources and cancels pending loads;
- leaves ordinary fields, computed values, and linked signals readable.

Disposal is idempotent. Prefer explicit disposal when a model has effects or
resources instead of relying on garbage collection.

```pyodide install="reaktiv" assets="no" height="12" theme="github_light_default,github_dark"
from reaktiv import ReactiveModel, field


class Counter(ReactiveModel):
    count = field(0)


model = Counter()
try:
    model.count.set(10)
    print(model.count())
finally:
    model.dispose()
```

## Inheritance And Mixins

With cooperative multiple inheritance, use `super()` normally. When another
base class does not call `super()`, initialize both bases explicitly and call
`ReactiveModel.__init__` last:

```pyodide install="reaktiv" assets="no" height="25" theme="github_light_default,github_dark"
from reaktiv import ReactiveModel, effect, field


class NamedService:
    def __init__(self, name: str) -> None:
        self.name = name


class CounterService(NamedService, ReactiveModel):
    count = field(0)

    def __init__(self, name: str, count: int = 0) -> None:
        NamedService.__init__(self, name)
        ReactiveModel.__init__(self, count=count)

    @effect
    def log_count(self) -> None:
        print(f"{self.name}: {self.count()}")


service = CounterService("worker", count=1)
service.count.set(2)
service.dispose()
```

Calling `ReactiveModel.__init__` last ensures ordinary attributes such as
`name` exist before eager effects and resources run.

## Further Examples

See `examples/reactive_model_linked_resource.py` for a complete example that
combines `linked`, `computed`, `effect`, `resource`, local resource updates, and
manual reloads. See `examples/reactive_model_cart.py` for batching, equality
functions, linked overrides, effect cleanup, and disposal.

::: reaktiv.ReactiveModel
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false
      members_order: source

::: reaktiv.field
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false
      members_order: source
