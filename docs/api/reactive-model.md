# ReactiveModel API

`ReactiveModel` lets decorator-based primitives become per-instance reactive
state. This is useful when a model owns a small graph of fields, computed values,
editable linked values, effects, and async resources.

## Linked Example

Use `linked` for state that starts from another signal, can be edited locally,
and resets when the source changes.

```python
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
```

## Typed Computed Decorator

When a method has no return annotation, Python type checkers usually cannot infer
the result type through a decorator. Use `computed[T]` to keep the method concise
while preserving the typed signal.

```python
from reaktiv import ReactiveModel, computed, field


class Search(ReactiveModel):
    query = field(" Notebook ")

    @computed[str]
    def normalized_query(self):
        return self.query().strip().lower()


search = Search()
print(search.normalized_query())  # notebook
```

## Resource Example

Use `resource` when async data should reload from reactive parameters. A model
with resources must be created while an asyncio event loop is running.

```python
import asyncio

from reaktiv import ReactiveModel, ResourceLoaderParams, field, resource


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
    await asyncio.sleep(0.2)

    if store.user.has_value():
        print(store.user.value())

    store.dispose()


asyncio.run(main())
```

See `examples/reactive_model_linked_resource.py` for a complete example that
combines `linked`, `computed`, `effect`, `resource`, local resource updates, and
manual reloads.

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
