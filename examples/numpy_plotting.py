"""
Numpy calculation and plotting example with reaktiv.

This example demonstrates using reaktiv for efficient computation
with numpy matrices and matplotlib visualization. The expensive
calculations only run when their input parameters change, while
visualization settings can change without triggering recalculation.

To run this example:
    pip install reaktiv numpy matplotlib ipywidgets
    python examples/numpy_plotting.py
"""

import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
from matplotlib.patches import Rectangle

from reaktiv import Signal, Computed, Effect, batch


class ReactiveMatrixVisualizer:
    def __init__(self):
        # Input parameters - changing these triggers recalculation
        self.matrix_size = Signal(100)
        self.seed = Signal(42)
        self.noise_scale = Signal(0.5)
        self.filter_size = Signal(5)

        # Visualization parameters - changing these doesn't trigger recalculation
        self.colormap_name = Signal("viridis")
        self.show_contour = Signal(False)
        self.contour_levels = Signal(10)
        self.title_text = Signal("Reactive Matrix Visualization")

        # Add status signals for UI feedback
        self.status_message = Signal("")
        self.is_computing = Signal(False)

        # Setup the figure with a fixed layout
        self.fig = plt.figure(figsize=(10, 8))

        # Create a more stable layout with dedicated areas
        from matplotlib import gridspec

        self.gs = gridspec.GridSpec(
            2,
            2,
            height_ratios=[6, 1],
            width_ratios=[20, 1],
            figure=self.fig,
            hspace=0.05,
            wspace=0.05,
        )

        # Create the axes for the plot, colorbar and controls
        self.ax = self.fig.add_subplot(self.gs[0, 0])  # Main plot in top-left
        self.cbar_ax = self.fig.add_subplot(self.gs[0, 1])  # Colorbar in top-right

        # Control area at the bottom spanning both columns
        self.controls_area = self.fig.add_subplot(self.gs[1, :])
        self.controls_area.axis("off")  # Hide the axes for the controls area

        # Status text for feedback
        self.status_text = self.fig.text(
            0.05, 0.25, "", fontsize=10, bbox=dict(facecolor="yellow", alpha=0.2)
        )

        # Rectangle for highlighting updates
        self.highlight_rect = Rectangle(
            (0, 0), 1, 1, fill=False, edgecolor="red", linewidth=3, visible=False
        )
        self.ax.add_patch(self.highlight_rect)

        # Add computation state signals
        self.computing_matrix = Signal(False)
        self.computing_filter = Signal(False)
        self.computation_status = Signal("")

        # Combine all input parameters into a single computed value
        self.input_parameters = Computed(
            lambda: {
                "size": self.matrix_size(),
                "seed": self.seed(),
                "noise": self.noise_scale(),
                "filter_size": self.filter_size(),
            }
        )

        # Computation time tracking
        self.matrix_computation_time = Signal(0.0)
        self.filter_computation_time = Signal(0.0)
        self.last_computation_time = Signal(0.0)  # Combined time

        # Now the expensive computations are TRULY pure functions (no signal setting)
        self.random_matrix_with_time = Computed(self._generate_random_matrix_pure)
        self.filtered_matrix_with_time = Computed(self._apply_filter_pure)

        # Computed signals for just the matrix data
        self.random_matrix = Computed(lambda: self.random_matrix_with_time()["matrix"])
        self.filtered_matrix = Computed(
            lambda: self.filtered_matrix_with_time()["filtered"]
        )

        # Effects to handle UI updates and status messages
        self._status_effect = Effect(self._update_status_display)

        # Effects to handle setting time signals
        self._matrix_time_effect = Effect(self._update_matrix_time)
        self._filter_time_effect = Effect(self._update_filter_time)
        self._total_time_effect = Effect(self._update_total_time)

        # Add effects to track computation status
        self._matrix_status_effect = Effect(self._track_matrix_computation)
        self._filter_status_effect = Effect(self._track_filter_computation)

        # Add UI controls
        self._setup_controls()

        # Effect to update the plot when computed values or visualization params change
        self._plot_effect = Effect(self._update_plot)

    def _generate_random_matrix_pure(self):
        """Generate a random matrix - TRULY PURE function (no signal setting)"""
        # Get all parameters from the combined input
        params = self.input_parameters()
        size = params["size"]
        seed = params["seed"]
        noise = params["noise"]

        # Log to console only (no signal setting)
        print(f"Matrix generation with size={size}, seed={seed}, noise={noise}")
        print(f"Generating new {size}×{size} matrix with seed {seed}...")
        start_time = time.time()

        # Set the seed for reproducibility
        np.random.seed(seed)

        # Generate matrix
        matrix = np.random.randn(size, size) * noise

        # Add patterns
        x = np.linspace(-5, 5, size)
        y = np.linspace(-5, 5, size)
        X, Y = np.meshgrid(x, y)

        frequency = max(1, 50 / size)
        pattern = np.sin(X * frequency) * np.cos(Y * frequency) * noise * 3
        matrix += pattern

        seed_effect = np.sin(X * (seed % 10 + 1) / 5) * np.cos(Y * (seed % 10 + 1) / 5)
        matrix += seed_effect * noise * 2

        computation_time = time.time() - start_time
        print(f"Matrix generation completed in {computation_time:.3f} seconds")

        # Return matrix, computation time, and parameters used
        return {
            "matrix": matrix,
            "time": computation_time,
            "params": {"size": size, "seed": seed},
        }

    def _apply_filter_pure(self):
        """Apply filter - TRULY PURE function (no signal setting)"""
        # Get parameters from the combined input
        params = self.input_parameters()
        filter_size = params["filter_size"]

        # Log to console only (no signal setting)
        print(f"Filter application with filter_size={filter_size}")
        print("Applying filter to matrix...")
        start_time = time.time()

        # Get matrix result
        matrix_result = self.random_matrix_with_time()
        matrix = matrix_result["matrix"]

        # Apply filter
        if filter_size <= 1:
            filtered = matrix
        else:
            filtered = np.zeros_like(matrix)
            m, n = matrix.shape
            effect_strength = filter_size / 3.0

            for i in range(m):
                for j in range(n):
                    i_start = max(0, i - filter_size)
                    i_end = min(m, i + filter_size + 1)
                    j_start = max(0, j - filter_size)
                    j_end = min(n, j + filter_size + 1)
                    window = matrix[i_start:i_end, j_start:j_end]
                    center_val = matrix[i, j]
                    filtered[i, j] = (
                        center_val * (1 - effect_strength)
                        + np.mean(window) * effect_strength
                    )

        computation_time = time.time() - start_time
        print(f"Filter application completed in {computation_time:.3f} seconds")

        # Return result with metadata
        return {
            "filtered": filtered,
            "time": computation_time,
            "params": {"filter_size": filter_size},
        }

    # Effect to update the status display based on status signals
    def _update_status_display(self):
        """Effect to update the status text UI element based on status signals"""
        message = self.status_message()
        if message:
            self.status_text.set_text(message)
            self.status_text.set_visible(True)
        else:
            self.status_text.set_visible(False)
        self.fig.canvas.draw_idle()

    # New methods to handle the side effects via Effects
    def _update_matrix_time(self):
        """Effect that updates the matrix computation time signal"""
        time_value = self.random_matrix_with_time()["time"]
        self.matrix_computation_time.set(time_value)

    def _update_filter_time(self):
        """Effect that updates the filter computation time signal"""
        time_value = self.filtered_matrix_with_time()["time"]
        self.filter_computation_time.set(time_value)

    def _update_total_time(self):
        """Effect that updates the total computation time signal"""
        matrix_time = self.matrix_computation_time()
        filter_time = self.filter_computation_time()
        self.last_computation_time.set(matrix_time + filter_time)

    # Effect functions to track computation status
    def _track_matrix_computation(self):
        """Track matrix computation and update status signals"""
        # Access result to check current status
        matrix_result = self.random_matrix_with_time()
        params = matrix_result["params"]

        # Update status message
        self.status_message.set(
            f"Matrix {params['size']}×{params['size']} with seed {params['seed']}"
        )

    def _track_filter_computation(self):
        """Track filter computation and update status signals"""
        # Access result to check current status
        filter_result = self.filtered_matrix_with_time()
        filter_size = filter_result["params"]["filter_size"]

        # Update status message
        if filter_size > 0:
            self.status_message.set(f"Applied filter (size {filter_size})")

    # These methods are now simplified - no more direct UI manipulation from here
    def _show_status(self, message):
        """Set the status message signal"""
        self.status_message.set(message)

    def _clear_status(self):
        """Clear the status message signal"""
        self.status_message.set("")

    def _flash_highlight(self):
        """Flash a highlight around the plot to indicate an update"""
        self.highlight_rect.set_visible(True)
        self.fig.canvas.draw_idle()

        # Use a timer to hide the highlight after a short delay
        timer = self.fig.canvas.new_timer(interval=500)  # 500ms
        timer.add_callback(self._hide_highlight)
        timer.start()

    def _hide_highlight(self):
        """Hide the highlight rectangle"""
        self.highlight_rect.set_visible(False)
        self.fig.canvas.draw_idle()
        return False  # Stop the timer

    def _update_plot(self):
        """Update the plot with current data and visualization settings"""
        print("Updating plot...")

        # Get current data and visualization parameters
        matrix = self.filtered_matrix()
        cmap_name = self.colormap_name()
        show_contours = self.show_contour()
        contour_levels = self.contour_levels()
        title = self.title_text()

        # Clear only the main plot axis, not the whole figure
        self.ax.clear()
        self.cbar_ax.clear()

        # Re-add the highlight rectangle after clearing
        self.highlight_rect = Rectangle(
            (0, 0), 1, 1, fill=False, edgecolor="red", linewidth=3, visible=False
        )
        self.ax.add_patch(self.highlight_rect)

        # Create the heatmap with enhanced contrast
        im = self.ax.imshow(
            matrix,
            cmap=cmap_name,
            interpolation="nearest",
            vmin=np.min(matrix) - 0.2 * np.std(matrix),  # Enhance contrast
            vmax=np.max(matrix) + 0.2 * np.std(matrix),
        )

        # Add contours if enabled - make them more prominent
        if show_contours:
            contours = self.ax.contour(
                matrix, levels=contour_levels, colors="k", alpha=0.7, linewidths=1.5
            )
            self.ax.clabel(contours, inline=True, fontsize=8)

        # Add colorbar to the dedicated axis
        cbar = self.fig.colorbar(im, cax=self.cbar_ax)
        cbar.set_label(f"Colormap: {cmap_name}")

        # Set title with computation info
        comp_time = self.last_computation_time()
        matrix_size = self.matrix_size()
        filter_size = self.filter_size()
        self.ax.set_title(
            f"{title}\n{matrix_size}×{matrix_size} matrix, filter size {filter_size}, computed in {comp_time:.3f}s"
        )

        # Add grid for better visual reference
        self.ax.grid(alpha=0.3, linestyle="--")

        # Clear status text
        self._clear_status()

        # Flash highlight to indicate update
        self._flash_highlight()

        # Draw the updated figure
        self.fig.canvas.draw_idle()
        print("Plot updated!")

    def _setup_controls(self):
        """Set up interactive controls"""
        # Add sliders for parameters
        axcolor = "lightgoldenrodyellow"

        # Computation parameter controls - sliders
        ax_size = plt.axes([0.25, 0.20, 0.65, 0.03], facecolor=axcolor)
        ax_noise = plt.axes([0.25, 0.15, 0.65, 0.03], facecolor=axcolor)
        ax_filter = plt.axes([0.25, 0.10, 0.65, 0.03], facecolor=axcolor)
        ax_seed = plt.axes(
            [0.25, 0.05, 0.65, 0.03], facecolor=axcolor
        )  # Fixed: added missing height parameter

        # Store sliders as instance variables
        self.size_slider = Slider(
            ax_size, "Matrix Size", 50, 500, valinit=self.matrix_size(), valstep=10
        )
        self.noise_slider = Slider(
            ax_noise, "Noise Scale", 0.1, 2.0, valinit=self.noise_scale()
        )
        self.filter_slider = Slider(
            ax_filter, "Filter Size", 0, 10, valinit=self.filter_size(), valstep=1
        )
        self.seed_slider = Slider(
            ax_seed, "Random Seed", 0, 100, valinit=self.seed(), valstep=1
        )

        # Visualization controls - MOVED UNDER SLIDERS
        # Position buttons on a row below the sliders
        button_y = 0.01  # Positioned below the lowest slider
        button_width = 0.15
        button_spacing = 0.02

        ax_cmap = plt.axes([0.15, button_y, button_width, 0.03], facecolor=axcolor)
        ax_contour = plt.axes(
            [0.15 + button_width + button_spacing, button_y, button_width, 0.03],
            facecolor=axcolor,
        )
        ax_contour_levels = plt.axes(
            [0.15 + 2 * (button_width + button_spacing), button_y, button_width, 0.03],
            facecolor=axcolor,
        )
        ax_reset = plt.axes(
            [0.15 + 3 * (button_width + button_spacing), button_y, button_width, 0.03],
            facecolor=axcolor,
        )

        # Store buttons as instance variables
        self.cmap_button = Button(ax_cmap, "Change Colormap")
        self.contour_button = Button(ax_contour, "Toggle Contours")
        self.contour_levels_button = Button(ax_contour_levels, "Contour Levels")
        self.reset_button = Button(ax_reset, "Reset")

        # Define update functions with enhanced feedback
        def update_size(val):
            size_val = int(val)
            print(f"SLIDER: Changing matrix size to {size_val}...")
            self._show_status(f"Changing matrix size to {size_val}...")
            self.matrix_size.set(size_val)

        def update_noise(val):
            print(f"SLIDER: Changing noise to {val:.2f}...")
            self._show_status(f"Adjusting noise scale to {val:.2f}...")
            self.noise_scale.set(val)

        def update_filter(val):
            filter_val = int(val)
            print(f"SLIDER: Changing filter to {filter_val}...")
            self._show_status(f"Setting filter size to {filter_val}...")
            self.filter_size.set(filter_val)

        def update_seed(val):
            seed_val = int(val)
            print(f"SLIDER: Changing seed to {seed_val}...")
            self._show_status(f"Changing random seed to {seed_val}...")
            self.seed.set(seed_val)

        def cycle_colormap(val):
            cmaps = ["viridis", "plasma", "inferno", "magma", "cividis", "hot", "cool"]
            current = self.colormap_name()
            idx = (cmaps.index(current) + 1) % len(cmaps) if current in cmaps else 0
            new_cmap = cmaps[idx]
            self._show_status(f"Changing colormap to {new_cmap}...")
            self.colormap_name.set(new_cmap)

        def toggle_contour(val):
            new_state = not self.show_contour()
            state_text = "ON" if new_state else "OFF"
            self._show_status(f"Toggling contours {state_text}...")
            self.show_contour.set(new_state)

        def cycle_contour_levels(val):
            levels = [5, 10, 15, 20, 30]
            current = self.contour_levels()
            idx = (levels.index(current) + 1) % len(levels) if current in levels else 0
            new_levels = levels[idx]
            self._show_status(f"Setting contour levels to {new_levels}...")
            self.contour_levels.set(new_levels)

        def reset(val):
            self._show_status("Resetting all parameters...")
            with batch():
                self.size_slider.set_val(100)
                self.noise_slider.set_val(0.5)
                self.filter_slider.set_val(5)
                self.seed_slider.set_val(42)
                self.colormap_name.set("viridis")
                self.show_contour.set(False)
                self.contour_levels.set(10)

        # Connect callbacks
        self.size_slider.on_changed(update_size)
        self.noise_slider.on_changed(update_noise)
        self.filter_slider.on_changed(update_filter)
        self.seed_slider.on_changed(update_seed)

        self.cmap_button.on_clicked(cycle_colormap)
        self.contour_button.on_clicked(toggle_contour)
        self.contour_levels_button.on_clicked(cycle_contour_levels)
        self.reset_button.on_clicked(reset)

    def show(self):
        """Display the interactive visualization"""
        # Make sure we use blocking mode to keep the window open
        plt.ioff()  # Turn off interactive mode to ensure window stays open
        plt.show(block=True)  # Explicitly use blocking mode


if __name__ == "__main__":
    print("Starting Reactive Matrix Visualizer...")
    print(
        "Notice how expensive computations only run when computation parameters change,"
    )
    print(
        "while visualization settings can be changed without triggering recalculation."
    )
    visualizer = ReactiveMatrixVisualizer()
    visualizer.show()
