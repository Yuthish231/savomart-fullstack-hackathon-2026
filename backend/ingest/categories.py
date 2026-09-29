"""OSM tag → SiteScout category, footfall weight and competitor tier.

Footfall weights express how many daily trips a feature typically generates relative to a
bus stop (=1). They are judgement calls, documented here so they can be challenged.
Competitor tiers: 3 = organised grocery chain, 2 = independent supermarket,
1 = convenience / kirana / greengrocer.
"""

import re
from dataclasses import dataclass

# Organised grocery chains operating in Chennai (matched on brand/name, case-insensitive).
ORGANISED_CHAINS = re.compile(
    r"reliance\s*(fresh|smart|retail|market)|smart\s*(bazaar|point)|jio\s*mart|"
    r"\bmore\b.*(super|market|retail|megastore)|^more$|more\s*megastore|"
    # OSM names are hand-typed: tolerate common misspellings (Niligiris, Nilgris, ...).
    r"nili?gi?ri|(?<!marks & )(?<!marks and )spencer|d[\s-]?mart|avenue supermart|"
    r"star\s*bazaar|big\s*bazaar|"
    r"ratnadeep|heritage\s*fresh|nature'?s\s*basket|foodhall|lulu|kannan\s*departmental|"
    r"grace\s*super\s*market|daily\s*needs|easyday|vishal\s*mega\s*mart|zepto|blinkit|"
    r"swiggy\s*instamart|bb\s*daily|bigbasket|pazhamudir\s*nilayam|kovai\s*pazhamudir",
    re.I,
)
OWN_BRAND = re.compile(r"savo\s*mart|savomart", re.I)

CONVENIENCE_SHOPS = {"convenience", "grocery", "greengrocer", "general", "dairy", "variety_store", "health_food", "frozen_food"}

AMENITY = {
    "school": ("education", 3.0),
    "kindergarten": ("education", 1.0),
    "college": ("education", 4.0),
    "university": ("education", 4.0),
    "hospital": ("health", 4.0),
    "clinic": ("health", 1.0),
    "doctors": ("health", 1.0),
    "pharmacy": ("health", 0.5),
    "bus_station": ("transit", 3.0),
    "place_of_worship": ("worship", 1.0),
    "marketplace": ("market", 3.0),
    "bank": ("finance", 0.5),
    "restaurant": ("food", 0.3),
    "cafe": ("food", 0.3),
    "fast_food": ("food", 0.3),
    "cinema": ("leisure", 2.0),
}


@dataclass(frozen=True)
class Classified:
    category: str
    subcategory: str
    footfall_weight: float
    competitor_tier: int = 0


def classify(tags: dict[str, str]) -> Classified | None:
    name = tags.get("name") or tags.get("name:en") or ""
    brand = tags.get("brand") or tags.get("operator") or ""
    shop = tags.get("shop")
    amenity = tags.get("amenity")

    if shop:
        if OWN_BRAND.search(name) or OWN_BRAND.search(brand):
            return Classified("own_store", shop, 1.0)
        if ORGANISED_CHAINS.search(brand) or ORGANISED_CHAINS.search(name):
            if shop in CONVENIENCE_SHOPS | {"supermarket", "department_store", "wholesale", "hypermarket"}:
                return Classified("grocery", f"organised_{shop}", 2.0, 3)
        if shop in ("supermarket", "hypermarket"):
            return Classified("grocery", shop, 1.0, 2)
        if shop in CONVENIENCE_SHOPS:
            return Classified("grocery", shop, 0.3, 1)
        if shop == "mall":
            return Classified("market", "mall", 4.0)
        return Classified("retail", shop, 0.3)

    if amenity in AMENITY:
        cat, w = AMENITY[amenity]
        return Classified(cat, amenity, w)

    if tags.get("railway") in ("station", "halt") or tags.get("public_transport") == "station":
        sub = "metro" if tags.get("station") == "subway" or "metro" in name.lower() else "rail"
        w = 3.0 if tags.get("railway") == "halt" else 6.0
        return Classified("transit", sub, w)
    if tags.get("highway") == "bus_stop":
        return Classified("transit", "bus_stop", 1.0)
    if "office" in tags:
        return Classified("office", tags["office"] or "office", 1.0)
    if tags.get("leisure") == "park":
        return Classified("leisure", "park", 1.0)
    return None


# --- Buildings --------------------------------------------------------------------------

RESIDENTIAL = {
    "house", "residential", "apartments", "detached", "semidetached_house", "terrace",
    "dormitory", "bungalow", "hut", "flats", "villa", "row_house",
}
NON_RESIDENTIAL = {
    "commercial", "retail", "industrial", "warehouse", "office", "school", "hospital",
    "church", "temple", "mosque", "chapel", "shrine", "religious", "public", "government",
    "garage", "garages", "shed", "roof", "construction", "university", "college",
    "kindergarten", "train_station", "transportation", "hotel", "service", "supermarket",
    "factory", "parking", "hangar", "stadium", "sports_hall", "civic", "fire_station",
    "toilets", "water_tower", "kiosk", "bridge", "ruins", "greenhouse", "farm_auxiliary",
}
# Share of an untagged ("building=yes") structure's floor area assumed residential.
UNKNOWN_RES_SHARE = 0.6


def classify_building(tags: dict[str, str]) -> tuple[str, str, int, float]:
    """Returns (kind, use_class, levels, residential weight)."""
    kind = (tags.get("building") or "yes").lower()[:30]
    raw_levels = tags.get("building:levels", "")
    try:
        levels = max(1, min(30, int(float(raw_levels.split(";")[0]))))
    except ValueError:
        levels = 4 if kind == "apartments" else 1
    if kind in RESIDENTIAL:
        use = "residential"
        share = 1.0
    elif kind in NON_RESIDENTIAL or tags.get("shop") or tags.get("amenity") or tags.get("office"):
        use = "non_res"
        share = 0.0
    else:
        use = "unknown"
        share = UNKNOWN_RES_SHARE
    return kind, use, levels, levels * share


# --- Roads ------------------------------------------------------------------------------

MAJOR_ROADS = {
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}
# Lanes a surveyor walks door to door. Arterials are excluded: they are measured, not surveyed.
SURVEYABLE = {"residential", "living_street", "unclassified", "service", "pedestrian", "road", "tertiary"}
