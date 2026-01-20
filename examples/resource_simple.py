"""Simple Resource Example - Fetch user data reactively.

This example demonstrates the basics of Resource in the simplest way possible:
- Creating a Resource that fetches data based on reactive parameters
- Automatic reloading when parameters change
- Safe value access with has_value()
"""

import asyncio
from reaktiv import Signal, Resource


# Simulated API function
async def fetch_user_from_api(user_id: int):
    """Simulate fetching user data from an API."""
    print(f"  Fetching user {user_id}...")
    await asyncio.sleep(0.5)  # Simulate network delay
    
    return {
        "id": user_id,
        "name": f"User {user_id}",
        "email": f"user{user_id}@example.com"
    }


async def main():
    print("=== Simple Resource Example ===\n")
    
    # Step 1: Create a reactive parameter
    user_id = Signal(1)
    
    # Step 2: Create a Resource that fetches data
    user_resource = Resource(
        # Params: what data to fetch (reactive - reloads when user_id changes)
        params=lambda: {"id": user_id()},
        
        # Loader: how to fetch the data (async function)
        loader=lambda p: fetch_user_from_api(p.params["id"])
    )
    
    # Wait for initial load
    print("Step 1: Initial load")
    await asyncio.sleep(0.6)
    
    # Step 3: Access the data safely
    if user_resource.has_value():
        user = user_resource.value()
        print(f"  Loaded: {user['name']} ({user['email']})")
    
    # Step 4: Change the parameter - Resource automatically reloads!
    print("\nStep 2: Change user_id to 2")
    user_id.set(2)
    
    # Show loading status
    if user_resource.is_loading():
        print("  Loading...")
    
    await asyncio.sleep(0.6)
    
    if user_resource.has_value():
        user = user_resource.value()
        print(f"  Loaded: {user['name']} ({user['email']})")
    
    # Step 5: Manual reload (same data)
    print("\nStep 3: Manual reload")
    user_resource.reload()
    await asyncio.sleep(0.6)
    
    if user_resource.has_value():
        user = user_resource.value()
        print(f"  Reloaded: {user['name']} ({user['email']})")
    
    # Step 6: Optimistic update (set value locally)
    print("\nStep 4: Optimistic update")
    user_resource.set({"id": 999, "name": "Edited User", "email": "edited@example.com"})
    
    user = user_resource.value()
    status = user_resource.status()
    print(f"  Local value: {user['name']} (status: {status})")
    
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
