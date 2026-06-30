#!/usr/bin/env python3
"""
build_recipes.py — generate the complete, exact recipes.json for EVE Forge.

It pulls the EVE Static Data Export (SDE) industry tables, hosted as CSV by
Fuzzwork, and writes ../data/recipes.json with every manufacturable item, its
output quantity, and its ME0 material requirements.

Usage:
    python build_recipes.py                # all manufacturable items
    python build_recipes.py --only-ships   # restrict to ships
    python build_recipes.py --published    # only published (live) items (default on)

No EVE account or API key needed. Just internet access.
"""

import argparse
import csv
import io
import json
import os
import sys
import urllib.request

BASE = "https://www.fuzzwork.co.uk/dump/latest"
FILES = {
    "types":     f"{BASE}/invTypes.csv",                 # typeID, typeName, published, marketGroupID, groupID
    "groups":    f"{BASE}/invGroups.csv",                # groupID, categoryID, groupName
    "products":  f"{BASE}/industryActivityProducts.csv", # typeID(bp), activityID, productTypeID, quantity
    "materials": f"{BASE}/industryActivityMaterials.csv", # typeID(bp), activityID, materialTypeID, quantity
}
MANUFACTURING = "1"  # activityID 1 = manufacturing
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "recipes.json")


def fetch_csv(url):
    print(f"  downloading {url} ...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "eve-forge-recipe-builder"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-ships", action="store_true", help="restrict output to ships (category 6)")
    ap.add_argument("--include-unpublished", action="store_true", help="include unpublished items")
    args = ap.parse_args()

    print("Fetching SDE tables...")
    try:
        types = fetch_csv(FILES["types"])
        groups = fetch_csv(FILES["groups"])
        products = fetch_csv(FILES["products"])
        materials = fetch_csv(FILES["materials"])
    except Exception as e:
        print(f"\nFAILED to download SDE data: {e}", file=sys.stderr)
        print("Check your internet connection and that fuzzwork.co.uk is reachable.", file=sys.stderr)
        sys.exit(1)

    # type metadata
    name_of, published_of, group_of = {}, {}, {}
    for t in types:
        tid = t["typeID"]
        name_of[tid] = t["typeName"]
        published_of[tid] = t.get("published", "1") in ("1", "True", "true")
        group_of[tid] = t.get("groupID", "")

    # group -> category and friendly group name
    cat_of_group, gname_of_group = {}, {}
    for g in groups:
        cat_of_group[g["groupID"]] = g.get("categoryID", "")
        gname_of_group[g["groupID"]] = g.get("groupName", "")

    # blueprint -> product (manufacturing only)
    bp_to_product = {}   # bpTypeID -> (productTypeID, productQty)
    for p in products:
        if p["activityID"] != MANUFACTURING:
            continue
        bp_to_product[p["typeID"]] = (p["productTypeID"], int(p["quantity"]))

    # blueprint -> materials (manufacturing only)
    bp_materials = {}    # bpTypeID -> [(materialTypeID, qty)]
    for m in materials:
        if m["activityID"] != MANUFACTURING:
            continue
        bp_materials.setdefault(m["typeID"], []).append((m["materialTypeID"], int(m["quantity"])))

    recipes = {}
    for bp, (prod, pqty) in bp_to_product.items():
        mats = bp_materials.get(bp)
        if not mats:
            continue
        if not args.include_unpublished and not published_of.get(prod, False):
            continue
        gid = group_of.get(prod, "")
        if args.only_ships and cat_of_group.get(gid, "") != "6":
            continue

        recipes[prod] = {
            "name": name_of.get(prod, f"Type {prod}"),
            "cat": gname_of_group.get(gid, ""),
            "productQty": pqty,
            "materials": [
                {"id": int(mid), "name": name_of.get(mid, f"Type {mid}"), "qty": q}
                for mid, q in mats
            ],
        }

    payload = {
        "_generated": "full-sde",
        "recipes": dict(sorted(recipes.items(), key=lambda kv: recipes[kv[0]]["name"])),
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\nWrote {len(recipes):,} recipes to {os.path.relpath(OUT)}")
    print("Reload the site — the sample banner will disappear and all items are now exact.")


if __name__ == "__main__":
    main()
