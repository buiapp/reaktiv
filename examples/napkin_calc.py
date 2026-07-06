#!/usr/bin/env python3
"""Reactive napkin calculator using reaktiv"""

from reaktiv import computed, effect, signal

# Input values
salary = signal(50000)
bonus = signal(5000)
tax_rate = signal(0.22)
expenses = signal(2500)
months = signal(12)

# Derived calculations
@computed
def income():
    return salary() + bonus()


@computed
def taxes():
    return income() * tax_rate()


@computed
def net():
    return income() - taxes()


@computed
def annual_expenses():
    return expenses() * months()


@computed
def savings():
    return net() - annual_expenses()


@computed
def savings_rate():
    return savings() / net() * 100


def display():
    print("\n📊 Financial Summary:")
    print(f"{'Item':<20} {'Value':>10}")
    print(f"{'-' * 20} {'-' * 10}")
    print(f"{'Income':<20} {'$' + str(income()):>10}")
    print(f"{'Taxes':<20} {'$' + str(taxes()):>10}")
    print(f"{'Net Income':<20} {'$' + str(net()):>10}")
    print(f"{'Annual Expenses':<20} {'$' + str(annual_expenses()):>10}")
    print(f"{'Savings':<20} {'$' + str(savings()):>10}")
    print(f"{'Savings Rate':<20} {f'{savings_rate():.1f}%':>10}")


table = effect(display)

print("\n--- Initial Values ---")

print("\n--- After Salary Increase ---")
salary.set(55000)

print("\n--- After Bonus and Tax Changes ---")
bonus.set(7500)
tax_rate.set(0.24)

print("\n--- Expense Reduction Strategy ---")
expenses.set(2200)

if __name__ == "__main__":
    print("\nTry it yourself! Change any input value to see calculations update.")
    print("Example: salary.set(60000)")
