"""
FastAPI WebSocket example with reaktiv.

This example shows how to use reaktiv with FastAPI to create a reactive
websocket that automatically reflects state changes.

To run this example:
    pip install fastapi uvicorn websockets

    # Run directly with uvicorn:
    uvicorn examples.fastapi_websocket:app --reload

    # Or if using uv:
    uv run uvicorn examples.fastapi_websocket:app --reload

    # NOT like this:
    # uv run python uvicorn examples.fastapi_websocket:app --reload

Then:
- Connect to the WebSocket at ws://localhost:8000/ws
- Use the REST endpoints to modify the state
- Watch the WebSocket update in real-time
"""

import asyncio
import json
from typing import AsyncIterator, Dict, Optional, Set, TypedDict
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from reaktiv import Effect, ReactiveModel, computed, effect, field


class AppSnapshot(TypedDict):
    counter: int
    messages: list[str]
    active_users: int
    last_message: Optional[str]


class MessagePayload(TypedDict):
    text: str


# Create a lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    # Setup code - runs before the application starts receiving requests
    print("Starting up: Setting up reactive effects...")
    manager.setup_effect()

    yield  # This is where FastAPI serves requests

    # Cleanup code - runs when the application is shutting down
    print("Shutting down: Cleaning up resources...")


# Initialize FastAPI app with lifespan
app = FastAPI(title="Reaktiv FastAPI WebSocket Example", lifespan=lifespan)

# State management with Reaktiv
class AppState(ReactiveModel):
    counter = field(0)
    messages = field[list[str]](factory=list)
    active_users = field(0)

    @computed
    def snapshot(self) -> AppSnapshot:
        messages = self.messages()
        return {
            "counter": self.counter(),
            "messages": messages,
            "active_users": self.active_users(),
            "last_message": messages[-1] if messages else None,
        }


app_state = AppState()


# WebSocket connection manager
class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self._broadcast_effect: Optional[Effect] = None  # Don't create Effect at import time

    def setup_effect(self) -> None:
        """Create the Effect when we're in an asyncio context"""
        if self._broadcast_effect is None:
            self._broadcast_effect = effect(self._broadcast_state)

    async def connect(self, websocket: WebSocket) -> None:
        # Create the Effect when we have a websocket connection (inside asyncio context)
        self.setup_effect()

        await websocket.accept()
        self.active_connections.add(websocket)
        app_state.active_users.set(len(self.active_connections))

        # Send initial state
        await self._send_state(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)
        app_state.active_users.set(len(self.active_connections))

    def _broadcast_state(self) -> None:
        """Effect that broadcasts state when it changes"""
        current_state = app_state.snapshot()

        async def _broadcast_state() -> None:
            if self.active_connections:
                data = json.dumps(current_state)
                # Create tasks for each connection to avoid blocking
                await asyncio.gather(
                    *[ws.send_text(data) for ws in self.active_connections],
                    return_exceptions=True,
                )

        asyncio.create_task(_broadcast_state())

    async def _send_state(self, websocket: WebSocket) -> None:
        """Send current state to a specific client"""
        current_state = app_state.snapshot()
        await websocket.send_text(json.dumps(current_state))


manager = ConnectionManager()

# HTML for a simple test client
html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Reaktiv WebSocket Demo</title>
        <style>
            body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            #output { background: #f4f4f4; border: 1px solid #ddd; padding: 10px; height: 300px; overflow: auto; }
            button { margin: 10px 5px; padding: 5px 10px; }
            #message { width: 300px; padding: 5px; }
        </style>
    </head>
    <body>
        <h1>Reaktiv WebSocket Demo</h1>
        <div id="output"></div>
        <div>
            <h3>Control Panel</h3>
            <div>
                <button onclick="callApi('/increment')">Increment Counter</button>
                <button onclick="callApi('/decrement')">Decrement Counter</button>
                <button onclick="callApi('/reset')">Reset Counter</button>
            </div>
            <div style="margin-top: 10px;">
                <input id="message" placeholder="Enter a message">
                <button onclick="sendMessage()">Send Message</button>
            </div>
        </div>
        <script>
            const output = document.getElementById('output');
            const ws = new WebSocket(`ws://${window.location.host}/ws`);
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                output.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            };
            
            ws.onclose = () => {
                output.innerHTML += '<p><strong>Connection closed</strong></p>';
            };
            
            async function callApi(endpoint) {
                try {
                    await fetch(endpoint);
                } catch (error) {
                    console.error('API call failed', error);
                }
            }
            
            async function sendMessage() {
                const messageInput = document.getElementById('message');
                const message = messageInput.value.trim();
                if (message) {
                    try {
                        await fetch('/message', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({text: message})
                        });
                        messageInput.value = '';
                    } catch (error) {
                        console.error('Failed to send message', error);
                    }
                }
            }
        </script>
    </body>
</html>
"""


@app.get("/")
async def get() -> HTMLResponse:
    """Serve a simple HTML client for testing"""
    return HTMLResponse(html)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint that reflects reaktiv state"""
    await manager.connect(websocket)
    try:
        while True:
            # Just keep the connection open
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/increment")
async def increment() -> Dict[str, object]:
    """Increment the counter"""
    app_state.counter.update(lambda c: c + 1)
    return {"status": "incremented", "value": app_state.counter()}


@app.get("/decrement")
async def decrement() -> Dict[str, object]:
    """Decrement the counter"""
    app_state.counter.update(lambda c: c - 1)
    return {"status": "decremented", "value": app_state.counter()}


@app.get("/reset")
async def reset() -> Dict[str, object]:
    """Reset the counter to zero"""
    app_state.counter.set(0)
    return {"status": "reset", "value": app_state.counter()}


@app.post("/message")
async def add_message(message: MessagePayload) -> Dict[str, str]:
    """Add a message to the list"""
    text = message.get("text", "").strip()
    if text:
        app_state.messages.update(lambda msgs: msgs + [text])
    return {"status": "message added"}


if __name__ == "__main__":
    # Make sure app runs with appropriate host and port
    print("Starting the FastAPI app with uvicorn...")
    print("Access the demo at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8001)
