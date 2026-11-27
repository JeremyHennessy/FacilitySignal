# National Hospice and IRF public pack QA

Exact main: `3d9871cbe52ce8f561e79beff6985de0925af293`. Audited all existing public projection bytes, not new publisher downloads; byte lengths and Git object IDs matched the pinned main tree, and SHA-256s were computed separately.

| Projection | CMS edition | Bytes | SHA-256 | Distinct string CCNs | Blank capacity |
|---|---|---:|---|---:|---:|
| Hospice | [Nov 20](https://data.cms.gov/provider-data/dataset/yc9t-dgbk) | 992670 | `3e1cf8b371d40e78ad387a76da5487115c455279087b7672a21bfdc3847b1bb4` | 6470 | 6470 |
| Inpatient rehabilitation | [Sep 23](https://data.cms.gov/provider-data/dataset/7t8x-u3ir) | 189656 | `65bbd35e32ff5a1379c30c53c316ebcdee5d1712ee3192df01f9b210aef4f28d` | 1222 | 1222 |

Both publisher totals and edition labels agree with the published packs. In both packs the capacity value is the literal empty string on every record; this is unavailable capacity, not zero or reported bed counts. Neither linked General Information table lists a capacity field.

The intersection of exact CCN strings is empty, while the intersection of literal projected `(address, city, state, zip)` tuples has three candidates; each references exactly one record per pack. All projected tuples have four nonempty string fields. These are different dated editions; an identical address is not property identity, co-located service confirmation, or justification to join provider records. No row details emitted and no source/app/Azure writes.

Reproduce at the pinned commit using Python stand-alone:

```python
import json
from pathlib import Path

base = Path("web/public-directory")
a, b = (json.loads((base / f"{name}.json").read_bytes())["records"] for name in ("hospice", "rehabilitation"))
def counts(rows, fields):
    from collections import Counter
    return Counter(tuple(row[field] for field in fields) for row in rows)
assert (len(a), len(b)) == (6470, 1222)
for rows in (a, b):
    assert len(counts(rows, ("ccn",))) == len(rows)
    assert all(type(r["ccn"]) is str and r["ccn"] and r["capacity"] == "" for r in rows)
assert not counts(a, ("ccn",)).keys() & counts(b, ("ccn",)).keys()
site = ("address", "city", "state", "zip")
assert all(type(r[k]) is str and r[k] for rows in (a, b) for r in rows for k in site)
x, y = counts(a, site), counts(b, site)
shared = x.keys() & y.keys()
assert len(shared) == 3 and all(x[k] == y[k] == 1 for k in shared)
```
