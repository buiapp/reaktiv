from reaktiv import signal, computed, effect
from time import sleep


# Define input cells (cells you can edit)
A1 = signal(10)  # Cell A1
B1 = signal(20)  # Cell B1
C1 = signal(30)  # Cell C1

# Define computed (formula) cells:
# D1 simulates "=SUM(A1, B1, C1)"
@computed
def D1():
    return A1() + B1() + C1()


# E1 simulates "=AVERAGE(A1, B1, C1)"
@computed
def E1():
    return (A1() + B1() + C1()) / 3


# F1 simulates "=PRODUCT(A1, B1, C1)"
@computed
def F1():
    return A1() * B1() * C1()


# Effect to print a simple spreadsheet view whenever any cell changes.
def print_spreadsheet():
    print("\n📊 Reactive Excel Simulation")
    print("+------+------+------+-------+----------+------------+")
    print("| Cell |   A  |   B  |   C   |    D     |    E       |")
    print("+------+------+------+-------+----------+------------+")
    print(f"|  1   | {A1():^4} | {B1():^4} | {C1():^4} | {D1():^6} | {E1():^8.2f} |")
    print("+------+------+------+-------+----------+------------+")
    print(f"| F1 (Product) = {F1()}")
    print("+-----------------------------------------+\n")


# Schedule the spreadsheet printing effect.
# (Assigning it to a variable ensures it won't be garbage collected.)
_sheet_effect = effect(print_spreadsheet)

# Simulate editing cells with delays so the editing messages are visible.
sleep(2)
print("✏️  Editing A1 → 15")
A1.set(15)

sleep(2)
print("✏️  Editing B1 → 25")
B1.set(25)

sleep(2)
print("✏️  Editing C1 → 35")
C1.set(35)

sleep(2)
print("✏️  Editing A1 → 50")
A1.set(50)

sleep(2)
print("✏️  Editing B1 → 5")
B1.set(5)

sleep(2)
print("✏️  Editing C1 → 10")
C1.set(10)
