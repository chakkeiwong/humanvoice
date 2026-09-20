#!/usr/bin/env python3
"""
Monitor ZLB inventory progress and estimate completion time.

Usage:
    python scripts/monitor_inventory.py <task_output_file>
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta


def get_progress(output_file: Path) -> tuple:
    """
    Parse output file to get current window number.

    Returns: (current_window, total_windows, last_line)
    """
    if not output_file.exists():
        return None, None, None

    with open(output_file) as f:
        lines = f.readlines()

    # Find last "Extracting window X/Y" line
    for line in reversed(lines):
        if "Extracting window" in line:
            # Extract numbers: "  Extracting window 23/146 (15 spans)..."
            parts = line.split("Extracting window")[1].split("(")[0].strip()
            current, total = parts.split("/")
            return int(current), int(total), line.strip()

    return None, None, None


def format_time_remaining(seconds: float) -> str:
    """Format seconds as human-readable time."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m {int(seconds % 60)}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"


def monitor_progress(output_file: Path, interval: int = 30):
    """Monitor progress and display estimates."""

    print("ZLB Inventory Progress Monitor")
    print("=" * 70)
    print()

    start_time = time.time()
    last_window = None

    while True:
        current, total, last_line = get_progress(output_file)

        if current is None:
            print("Waiting for extraction to start...")
            time.sleep(interval)
            continue

        # Calculate progress
        percent = (current / total) * 100
        remaining = total - current

        # Calculate rate
        elapsed = time.time() - start_time
        if elapsed > 0:
            windows_per_second = current / elapsed
            seconds_remaining = remaining / windows_per_second if windows_per_second > 0 else 0
            eta = datetime.now() + timedelta(seconds=seconds_remaining)
        else:
            windows_per_second = 0
            seconds_remaining = 0
            eta = None

        # Display
        print(f"\r[{datetime.now().strftime('%H:%M:%S')}] ", end="")
        print(f"Window {current}/{total} ({percent:.1f}%) | ", end="")
        print(f"Rate: {windows_per_second * 60:.1f} win/min | ", end="")

        if eta:
            print(f"ETA: {eta.strftime('%H:%M:%S')} ({format_time_remaining(seconds_remaining)} remaining)", end="")

        sys.stdout.flush()

        # Check if complete
        if current >= total:
            print()
            print()
            print("=" * 70)
            print("✅ Inventory extraction complete!")
            print(f"Total time: {format_time_remaining(elapsed)}")
            print(f"Average rate: {(total / elapsed) * 60:.1f} windows/minute")
            break

        time.sleep(interval)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python monitor_inventory.py <task_output_file>")
        sys.exit(1)

    output_file = Path(sys.argv[1])
    if not output_file.exists():
        print(f"Error: File not found: {output_file}")
        sys.exit(1)

    try:
        monitor_progress(output_file)
    except KeyboardInterrupt:
        print()
        print("Monitoring interrupted")
        sys.exit(0)
