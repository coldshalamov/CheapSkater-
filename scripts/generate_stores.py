import requests
import yaml
from urllib.parse import quote

ZIP_OVERRIDES = {
    ("WA", "Mill Creek"): "98012",
    ("WA", "Bonney Lake"): "98391",
    ("WA", "Federal Way"): "98003",
    ("WA", "Lakewood"): "98499",
    ("WA", "Port Orchard"): "98366",
    ("WA", "Puyallup"): "98373",
    ("WA", "Monroe"): "98272",
    ("WA", "Kennewick"): "99336",
    ("WA", "Pasco"): "99301",
    ("WA", "Spokane"): "99208",
    ("WA", "Wenatchee"): "98801",
    ("WA", "Yakima"): "98902",
    ("WA", "Tukwila"): "98188",
    ("OR", "Wood Village"): "97060",
    ("OR", "Tigard"): "97223",
    ("OR", "Milwaukie"): "97222",
    ("OR", "Keizer"): "97303",
    ("OR", "Hillsboro"): "97124",
    ("OR", "McMinnville"): "97128",
}

WA_STORES = [
    {"city": "Arlington", "state": "WA", "store_name": "Smokey Point Lowe's"},
    {"city": "Auburn", "state": "WA"},
    {"city": "Bellingham", "state": "WA"},
    {"city": "Bonney Lake", "state": "WA"},
    {"city": "Bremerton", "state": "WA"},
    {"city": "Everett", "state": "WA"},
    {"city": "Federal Way", "state": "WA"},
    {"city": "Issaquah", "state": "WA"},
    {"city": "Kennewick", "state": "WA"},
    {"city": "Kent", "state": "WA"},
    {"city": "Lacey", "state": "WA"},
    {"city": "Lakewood", "state": "WA"},
    {"city": "Longview", "state": "WA"},
    {"city": "Lynnwood", "state": "WA"},
    {"city": "Mill Creek", "state": "WA"},
    {"city": "Monroe", "state": "WA"},
    {"city": "Moses Lake", "state": "WA"},
    {"city": "Mount Vernon", "state": "WA"},
    {"city": "Olympia", "state": "WA"},
    {"city": "Pasco", "state": "WA"},
    {"city": "Port Orchard", "state": "WA"},
    {"city": "Puyallup", "state": "WA"},
    {"city": "Renton", "state": "WA"},
    {"city": "Seattle", "state": "WA", "store_name": "Rainier Lowe's", "zip": "98144"},
    {"city": "Seattle", "state": "WA", "store_name": "N. Seattle Lowe's", "zip": "98133"},
    {"city": "Silverdale", "state": "WA"},
    {"city": "Spokane", "state": "WA"},
    {"city": "Spokane Valley", "state": "WA", "store_name": "Spokane Valley Lowe's", "zip": "99216"},
    {"city": "Spokane Valley", "state": "WA", "store_name": "Liberty Lake Lowe's", "zip": "99206"},
    {"city": "Tacoma", "state": "WA"},
    {"city": "Tukwila", "state": "WA"},
    {"city": "Vancouver", "state": "WA", "store_name": "E. Vancouver Lowe's", "zip": "98662"},
    {"city": "Vancouver", "state": "WA", "store_name": "Lacamas Lake Lowe's", "zip": "98683"},
    {"city": "Wenatchee", "state": "WA"},
    {"city": "Yakima", "state": "WA"},
]

OR_STORES = [
    {"city": "Albany", "state": "OR"},
    {"city": "Bend", "state": "OR"},
    {"city": "Eugene", "state": "OR"},
    {"city": "Hillsboro", "state": "OR"},
    {"city": "Keizer", "state": "OR"},
    {"city": "McMinnville", "state": "OR"},
    {"city": "Medford", "state": "OR"},
    {"city": "Milwaukie", "state": "OR"},
    {"city": "Portland", "state": "OR"},
    {"city": "Redmond", "state": "OR"},
    {"city": "Roseburg", "state": "OR"},
    {"city": "Salem", "state": "OR"},
    {"city": "Tigard", "state": "OR"},
    {"city": "Wood Village", "state": "OR"},
]

ENTRIES = WA_STORES + OR_STORES


def lookup_zip(state: str, city: str) -> str:
    override = ZIP_OVERRIDES.get((state, city))
    if override:
        return override
    url = f"https://api.zippopotam.us/us/{state.lower()}/{quote(city.lower())}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    places = resp.json().get("places") or []
    if not places:
        raise RuntimeError(f"No zip for {city}, {state}")
    exact = next((p for p in places if p.get("place name", "").lower() == city.lower()), None)
    if exact:
        return exact["post code"]
    partial = next((p for p in places if city.lower() in p.get("place name", "").lower()), None)
    if partial:
        return partial["post code"]
    return places[0]["post code"]

records = []
for entry in ENTRIES:
    zip_code = entry.get("zip") or lookup_zip(entry["state"], entry["city"])
    store_name = entry.get("store_name") or f"{entry['city']} Lowe's"
    records.append({"zip": zip_code, "store_name": store_name, "state": entry["state"]})

unique_zips = sorted({r["zip"] for r in records})
records_sorted = sorted(records, key=lambda r: (r["state"], r["store_name"]))

yaml_payload = {"zips": unique_zips, "stores": records_sorted}

with open("catalog/wa_or_stores.yml", "w", encoding="utf-8") as fh:
    yaml.safe_dump(yaml_payload, fh, sort_keys=False, allow_unicode=True)

print(f"Wrote {len(records_sorted)} stores and {len(unique_zips)} zips")
