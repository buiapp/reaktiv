from reaktiv import Signal, Computed
x = Signal(10)
safe_compute = Computed(
    lambda: 100 / x(),  # Will throw ZeroDivisionError if x is 0
    default=9  # Default value to use in case of error
)

print(safe_compute())  # 10 (100 / 10)

# Set x to 0, which would cause a division by zero
x.set(0)

# Instead of crashing, it returns the default value
print(safe_compute())  # 0 (the default value)