import asyncio
from reaktiv import Signal, ComputeSignal, Effect

async def main():
    # Define input cells (cells you can edit)
    A1 = Signal(10)  # Cell A1
    B1 = Signal(20)  # Cell B1
    C1 = Signal(30)  # Cell C1

    # Define computed (formula) cells:
    # D1 simulates "=SUM(A1, B1, C1)"
    D1 = ComputeSignal(lambda: A1.get() + B1.get() + C1.get())
    # E1 simulates "=AVERAGE(A1, B1, C1)"
    E1 = ComputeSignal(lambda: (A1.get() + B1.get() + C1.get()) / 3)
    # F1 simulates "=PRODUCT(A1, B1, C1)"
    F1 = ComputeSignal(lambda: A1.get() * B1.get() * C1.get())

    # Effect to print a simple spreadsheet view whenever any cell changes.
    async def print_spreadsheet():
        print("\n📊 Reactive Excel Simulation")
        print("+------+------+------+-------+----------+------------+")
        print("| Cell |   A  |   B  |   C   |    D     |    E       |")
        print("+------+------+------+-------+----------+------------+")
        print(f"|  1   | {A1.get():^4} | {B1.get():^4} | {C1.get():^4} | {D1.get():^6} | {E1.get():^8.2f} |")
        print("+------+------+------+-------+----------+------------+")
        print(f"| F1 (Product) = {F1.get()}")
        print("+-----------------------------------------+\n")

    # Schedule the spreadsheet printing effect.
    # (Assigning it to a variable ensures it won't be garbage collected.)
    sheet_effect = Effect(print_spreadsheet)
    sheet_effect.schedule()

    # Simulate editing cells with delays so the editing messages are visible.
    await asyncio.sleep(2)
    print("✏️  Editing A1 → 15")
    A1.set(15)

    await asyncio.sleep(2)
    print("✏️  Editing B1 → 25")
    B1.set(25)

    await asyncio.sleep(2)
    print("✏️  Editing C1 → 35")
    C1.set(35)

    await asyncio.sleep(2)
    print("✏️  Editing A1 → 50")
    A1.set(50)

    await asyncio.sleep(2)
    print("✏️  Editing B1 → 5")
    B1.set(5)

    await asyncio.sleep(2)
    print("✏️  Editing C1 → 10")
    C1.set(10)

    # Allow a moment for the final effect updates.
    await asyncio.sleep(2)

if __name__ == '__main__':
    asyncio.run(main())
