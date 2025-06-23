"""
Reactive Data Pipeline with NumPy and Pandas

Simple example showing automatic recalculation when data or parameters change.
Demonstrates lazy evaluation, memoization, and fine-grained reactive dependencies.

Run with:
1. pip install reaktiv numpy pandas
2. python examples/data_pipeline_numpy_pandas.py
"""

import numpy as np
import pandas as pd
from reaktiv import Signal, Computed, Effect


def create_data() -> pd.DataFrame:
    """Generate sample sensor data."""
    np.random.seed(42)
    return pd.DataFrame(
        {
            "temperature": np.random.normal(20, 5, 1000),
            "humidity": np.random.normal(60, 10, 1000),
            "sensor": np.random.choice(["A", "B", "C"], 1000),
        }
    )


def main():
    print("Reactive Data Pipeline Example")

    # Reactive data sources
    data = Signal(create_data())
    window_size = Signal(10)
    threshold = Signal(2.0)

    # Stage 1: Basic preprocessing - LAZY: not computed until accessed
    basic_stats = Computed(
        lambda: data().assign(
            temp_mean=data()["temperature"].mean(),
            temp_std=data()["temperature"].std(),
            temp_smooth=data()["temperature"].rolling(window_size()).mean(),
        )
    )

    # Stage 2: Z-score calculation - depends only on basic_stats
    with_zscore = Computed(
        lambda: basic_stats().assign(
            temp_zscore=(basic_stats()["temperature"] - basic_stats()["temp_mean"])
            / basic_stats()["temp_std"]
        )
    )

    # Stage 3: Outlier detection - depends on with_zscore AND threshold
    with_outliers = Computed(
        lambda: with_zscore().assign(
            is_outlier=np.abs(with_zscore()["temp_zscore"]) > threshold()
        )
    )

    # Stage 4: Summary analysis - MEMOIZED: result cached until dependencies change
    def calculate_summary():
        df = with_outliers()
        return {
            "mean_temp": df["temperature"].mean(),
            "outliers": df["is_outlier"].sum(),
            "sensor_counts": df.groupby("sensor").size().to_dict(),
        }

    summary = Computed(calculate_summary)

    # Auto-updating report - triggers initial computation
    def print_summary():
        s = summary()  # First access: computes entire pipeline
        print(
            f"Mean: {s['mean_temp']:.1f}°C, Outliers: {s['outliers']}, Sensors: {s['sensor_counts']}"
        )

    _report = Effect(print_summary)

    # Demonstrate fine-grained reactive updates
    print(
        "Changing window size (affects basic_stats, with_zscore, with_outliers, summary)..."
    )
    window_size.set(20)

    print("Changing threshold (affects ONLY with_outliers and summary)...")
    threshold.set(1.5)  # FINE-GRAINED: only outlier detection and summary recalculate

    # Add new data - entire pipeline recalculates due to root dependency
    print("Adding new data (affects entire pipeline)...")
    new_data = pd.DataFrame(
        {
            "temperature": np.random.normal(25, 3, 100),
            "humidity": np.random.normal(50, 8, 100),
            "sensor": np.random.choice(["A", "B", "C"], 100),
        }
    )
    data.set(pd.concat([data(), new_data], ignore_index=True))


if __name__ == "__main__":
    main()
