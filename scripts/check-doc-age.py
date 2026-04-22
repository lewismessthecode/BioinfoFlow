#!/usr/bin/env python3
"""Check documentation file age and identify obsolete files."""

import os
from datetime import datetime, timedelta
from pathlib import Path

docs_dir = Path("docs")
now = datetime.now()
ninety_days_ago = now - timedelta(days=90)

obsolete_files = []
recent_files = []

for md_file in docs_dir.glob("*.md"):
    mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
    age_days = (now - mtime).days

    file_info = {
        "name": md_file.name,
        "age_days": age_days,
        "last_modified": mtime.strftime("%Y-%m-%d")
    }

    if mtime < ninety_days_ago:
        obsolete_files.append(file_info)
    else:
        recent_files.append(file_info)

print("=" * 70)
print("OBSOLETE DOCUMENTATION (>90 days old)")
print("=" * 70)

if obsolete_files:
    for f in sorted(obsolete_files, key=lambda x: x["age_days"], reverse=True):
        print(f"{f['age_days']:3d} days - {f['name']:40s} (modified: {f['last_modified']})")
    print(f"\n⚠️  {len(obsolete_files)} files require review")
else:
    print("✅ No obsolete files found.")

print("\n" + "=" * 70)
print("RECENT DOCUMENTATION (<90 days old)")
print("=" * 70)

for f in sorted(recent_files, key=lambda x: x["age_days"], reverse=True):
    print(f"{f['age_days']:3d} days - {f['name']:40s} (modified: {f['last_modified']})")

print("\n" + "=" * 70)
print(f"Summary: {len(obsolete_files)} obsolete, {len(recent_files)} recent, {len(obsolete_files) + len(recent_files)} total")
print("=" * 70)
