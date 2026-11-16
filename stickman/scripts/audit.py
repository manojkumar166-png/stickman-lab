#!/usr/bin/env python3
"""Audits rendered frames against film rules and contact tolerances."""
import json
import sys
from pathlib import Path


def main():
    folder = Path(sys.argv[1])
    parts = folder / "shots"
    st_files = sorted(parts.glob("st_*.json"))
    if not st_files:
        print("Audit: No frame reports found.")
        return

    total_contacts = 0
    broken_contacts = 0

    for f in st_files:
        with open(f) as stream:
            frames = json.load(stream)
        for fr in frames:
            for name, a, b in fr.get("contacts", []):
                total_contacts += 1
                # Simple Euclidean distance check between reported points.
                # Contact tolerance is 3px as per engine specs.
                dist = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                if dist > 3.0:
                    broken_contacts += 1

    print(f"Audit Complete: Checked {total_contacts} contact constraints.")
    if broken_contacts > 0:
        print(f"Warning: {broken_contacts} contact constraints exceeded 3px tolerance.")
    else:
        print("All contact constraints passed within tolerance.")


if __name__ == "__main__":
    main()
