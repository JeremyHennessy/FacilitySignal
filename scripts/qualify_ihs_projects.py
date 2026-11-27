"""Aggregate-only qualifier for the public IHS DFPC rendered project cards."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata

SOURCE="https://www.ihs.gov/DFPC/projects/"
TITLE="# Projects Under Construction and Recently Completed"
STATUSES={"completed":"completed","in construction":"in_construction"}


def clean(text):
    return " ".join(unicodedata.normalize("NFC",text).split()).casefold()


def qualify(raw):
    if not raw or len(raw)>1000000:
        raise ValueError("unexpected rendered excerpt length")
    lines=raw.decode("utf-8",errors="strict").splitlines()
    if lines.count(TITLE)!=1:
        raise ValueError("expected official rendered page title")
    cards=[]
    for line in lines[lines.index(TITLE)+1:]:
        if line.startswith("#### "):
            cards.append([clean(line[5:]),[],[]])
        elif cards and line.startswith("Status:"):
            cards[-1][1].append(clean(line.split(":",1)[1]))
        elif cards and line.startswith("Photo Date:"):
            photo=line.split(":",1)[1].strip()
            if photo!="TBD" and not re.fullmatch(r"(?:19|20)[0-9]{2}",photo):
                raise ValueError("unexpected publisher photo year shape")
            cards[-1][2].append(None if photo=="TBD" else int(photo))
    if not cards:raise ValueError("no rendered cards")
    by_title={};photos=[]
    for title,status,photo in cards:
        if not title or len(status)!=1 or status[0] not in STATUSES or len(photo)>1:
            raise ValueError("missing or unsupported rendered card evidence")
        if title in by_title and by_title[title]!=status[0]:
            raise ValueError("conflicting display statuses for one title")
        by_title[title]=status[0]; photos.extend(photo)
    years=[year for year in photos if year is not None]
    status_count=Counter(STATUSES[x] for x in by_title.values())
    return {"source":SOURCE,"scope":"rendered public project cards, not original publisher bytes",
            "rendered_input_sha256":sha256(raw).hexdigest(),"rendered_input_bytes":len(raw),
            "display_cards":len(cards),"normalized_distinct_display_titles":len(by_title),
            "repeated_titles":len(cards)-len(by_title),
            "deduplicated_display_statuses":dict(sorted(status_count.items())),
            "cards_with_photo_year":len(years),"cards_with_tbd_photo_year":len(photos)-len(years),"photo_year_range":[min(years),max(years)] if years else None,
            "facility_links_qualified":0,"public_promotion":False,
            "limits":"Publisher display statuses, not current construction verification, facility IDs, operations, contracts, awards, or expenditure. Photo years are not project dates."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rendered_excerpt")
    args=parser.parse_args()
    print(json.dumps(qualify(Path(args.rendered_excerpt).read_bytes()),indent=2,sort_keys=True))


if __name__=="__main__":
    main()
