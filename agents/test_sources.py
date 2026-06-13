"""Quick test to see what each source actually returns"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.scraper import (
    fetch_federal_register, fetch_sec, fetch_occ,
    fetch_fincen, fetch_naic, fetch_california_doi, fetch_nydfs
)

print("\n" + "="*70)
print("SOURCE DIAGNOSIS — What are we actually getting?")
print("="*70)

sources = [
    ("Federal Register", fetch_federal_register),
    ("SEC", fetch_sec),
    ("OCC", fetch_occ),
    ("FinCEN", fetch_fincen),
    ("NAIC", fetch_naic),
    ("CA DOI", fetch_california_doi),
    ("NYDFS", fetch_nydfs),
]

total = 0
for name, fn in sources:
    print(f"\n{'─'*50}")
    print(f"📡 {name}")
    print(f"{'─'*50}")
    items = fn()
    total += len(items)
    if items:
        for i, item in enumerate(items, 1):
            print(f"  {i}. {item['title'][:80]}")
            print(f"     URL: {item['url'][:80]}")
            print(f"     Date: {item.get('date', 'NO DATE')}")
            print()
    else:
        print("  ❌ ZERO items returned")
        print("  Possible reasons:")
        print("  - RSS feed URL changed or is down")
        print("  - Website structure changed")
        print("  - Date filter too strict (CUTOFF_DAYS = 3)")
        print()

print(f"\n{'='*70}")
print(f"TOTAL: {total} items across all sources")
print(f"{'='*70}")