"""Sparkline widget for mini rate charts."""

from typing import List, Optional

from rich.text import Text
from textual.widgets import Static


class Sparkline(Static):
    """
    ASCII sparkline chart widget for displaying rate trends.

    Uses block characters to create mini charts showing rate evolution.
    """

    # Block characters for different heights (0-7)
    BLOCKS = " ▁▂▃▄▅▆▇█"

    def __init__(
        self,
        data: Optional[List[float]] = None,
        width: int = 30,
        label: str = "",
        color: str = "green",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._data: List[float] = data or []
        self._width = width
        self._label = label
        self._color = color

    def update_data(self, data: List[float]) -> None:
        """Update sparkline data and re-render."""
        self._data = data
        self._render()

    def set_label(self, label: str) -> None:
        """Update the label."""
        self._label = label
        self._render()

    def set_color(self, color: str) -> None:
        """Update the color."""
        self._color = color
        self._render()

    def on_mount(self) -> None:
        """Initial render."""
        self._render()

    def _render(self) -> None:
        """Render the sparkline."""
        if not self._data:
            self.update(Text("No data", style="dim"))
            return

        # Resample data to fit width
        resampled = self._resample(self._data, self._width)

        # Normalize to 0-8 range
        normalized = self._normalize(resampled)

        # Build sparkline
        sparkline = Text()

        if self._label:
            sparkline.append(f"{self._label}: ", style="dim")

        # Add min value
        min_val = min(self._data) * 100
        sparkline.append(f"{min_val:.1f}% ", style="dim")

        # Add sparkline characters
        for val in normalized:
            idx = min(int(val), len(self.BLOCKS) - 1)
            sparkline.append(self.BLOCKS[idx], style=self._color)

        # Add max value
        max_val = max(self._data) * 100
        sparkline.append(f" {max_val:.1f}%", style="dim")

        # Add current value
        current = self._data[-1] * 100
        sparkline.append(f" (now: {current:.2f}%)", style=f"bold {self._color}")

        self.update(sparkline)

    def _resample(self, data: List[float], target_len: int) -> List[float]:
        """Resample data to target length."""
        if len(data) <= target_len:
            return data

        step = len(data) / target_len
        result = []

        for i in range(target_len):
            start_idx = int(i * step)
            end_idx = int((i + 1) * step)
            segment = data[start_idx:end_idx]
            if segment:
                result.append(sum(segment) / len(segment))

        return result

    def _normalize(self, data: List[float]) -> List[float]:
        """Normalize data to 0-8 range."""
        if not data:
            return []

        min_val = min(data)
        max_val = max(data)
        range_val = max_val - min_val

        if range_val == 0:
            return [4.0] * len(data)  # Middle value

        return [((v - min_val) / range_val) * 8 for v in data]


class RateSparklines(Static):
    """
    Compound widget showing multiple sparklines for a market.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._supply_data: List[float] = []
        self._borrow_data: List[float] = []
        self._util_data: List[float] = []

    def update_rates(
        self,
        supply_apys: List[float],
        borrow_apys: List[float],
        utilizations: List[float],
    ) -> None:
        """Update all rate data."""
        self._supply_data = supply_apys
        self._borrow_data = borrow_apys
        self._util_data = utilizations
        self._render()

    def _render(self) -> None:
        """Render all sparklines."""
        content = Text()

        # Supply APY sparkline
        content.append("Supply APY  ", style="green dim")
        content.append(self._build_sparkline(self._supply_data, "green"))
        content.append("\n")

        # Borrow APY sparkline
        content.append("Borrow APY  ", style="red dim")
        content.append(self._build_sparkline(self._borrow_data, "red"))
        content.append("\n")

        # Utilization sparkline
        content.append("Utilization ", style="yellow dim")
        content.append(self._build_sparkline(self._util_data, "yellow"))

        self.update(content)

    def _build_sparkline(self, data: List[float], color: str, width: int = 30) -> Text:
        """Build a single sparkline."""
        if not data:
            return Text("No data", style="dim")

        # Resample
        if len(data) > width:
            step = len(data) / width
            resampled = []
            for i in range(width):
                start_idx = int(i * step)
                end_idx = int((i + 1) * step)
                segment = data[start_idx:end_idx]
                if segment:
                    resampled.append(sum(segment) / len(segment))
            data = resampled

        # Normalize
        min_val = min(data) if data else 0
        max_val = max(data) if data else 0
        range_val = max_val - min_val or 1

        blocks = " ▁▂▃▄▅▆▇█"
        result = Text()

        # Min value
        result.append(f"{min_val*100:5.1f}% ", style="dim")

        # Sparkline
        for v in data:
            normalized = ((v - min_val) / range_val) * 8
            idx = min(int(normalized), len(blocks) - 1)
            result.append(blocks[idx], style=color)

        # Max and current
        result.append(f" {max_val*100:5.1f}%", style="dim")
        if data:
            current = data[-1] * 100
            result.append(f" [{current:.2f}%]", style=f"bold {color}")

        return result
