"""
Example demonstrating how to integrate reaktiv with NiceGUI to build reactive UIs.

This example creates a simple todo application that lets you add tasks,
mark them as complete, filter them by status, and automatically updates
all UI components when the underlying data changes.

To run this example:
1. pip install reaktiv nicegui
2. python nicegui_todo_app.py
"""

from reaktiv import Signal, Computed, Effect
from nicegui import ui

# State module - completely independent from UI
class TodoState:
    def __init__(self):
        self.todos = Signal([])
        self.filter = Signal("all")  # all, active, completed
        
        # These can be used by both UI and API endpoints
        self.filtered_todos = Computed(lambda: [
            todo for todo in self.todos()
            if self.filter() == "all" 
            or (self.filter() == "active" and not todo["completed"])
            or (self.filter() == "completed" and todo["completed"])
        ])
        self.active_count = Computed(lambda: 
            sum(1 for todo in self.todos() if not todo["completed"])
        )
        self.completed_count = Computed(lambda: 
            sum(1 for todo in self.todos() if todo["completed"])
        )
    
    def add_todo(self, text):
        self.todos.update(lambda todos: todos + [{"text": text, "completed": False}])
    
    def toggle_todo(self, index):
        self.todos.update(lambda todos: [
            {**todo, "completed": not todo["completed"]} if i == index else todo
            for i, todo in enumerate(todos)
        ])
    
    def clear_completed(self):
        self.todos.update(lambda todos: [todo for todo in todos if not todo["completed"]])

# Create a state instance
state = TodoState()

# UI layer can now use the state
with ui.card():
    ui.label("Todo App").classes("text-xl")
    
    # Input for new todos
    with ui.row():
        new_todo = ui.input("New task")
        ui.button("Add", on_click=lambda: [state.add_todo(new_todo.value), new_todo.set_value("")])
    
    # Todo list - connected to state via Effect
    todo_container = ui.column()
    
    def render_todos():
        todo_container.clear()
        for i, todo in enumerate(state.filtered_todos()):
            with todo_container:
                with ui.row():
                    ui.checkbox(value=todo["completed"], on_change=lambda e, idx=i: state.toggle_todo(idx))
                    ui.label(todo["text"]).classes("line-through" if todo["completed"] else "")
    
    # Effect connects state to UI
    render_effect = Effect(render_todos)
    
    # Filter controls
    with ui.row():
        ui.button("All", on_click=lambda: state.filter.set("all"))
        ui.button("Active", on_click=lambda: state.filter.set("active"))
        ui.button("Completed", on_click=lambda: state.filter.set("completed"))
        ui.button("Clear completed", on_click=lambda: state.clear_completed())
    
    # Status display - automatically updates
    status_label = ui.label()
    status_effect = Effect(lambda: status_label.set_text(
        f"{state.active_count()} active, {state.completed_count()} completed"
    ))

ui.run()