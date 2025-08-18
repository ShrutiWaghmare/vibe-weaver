# recommender.py
import random
from retailers_provider import search_links_for_query, load_user_prefs

def complement_colors(color):
    table = {
        "black": ["white","beige"], "white": ["black","navy"],
        "gray": ["white","blue"], "navy": ["white","tan"],
        "blue": ["white","beige"], "sky blue": ["white","navy"],
        "teal": ["white","beige"], "green": ["white","cream"],
        "olive": ["white","tan"], "lime": ["white","black"],
        "yellow": ["black","navy"], "beige": ["black","navy"],
        "tan": ["white","navy"], "orange": ["white","black"],
        "brown": ["white","cream"], "red": ["white","black"],
        "maroon": ["white","cream"], "pink": ["white","gray"],
        "magenta": ["white","black"], "purple": ["white","black"],
        "lavender": ["white","navy"], "cream": ["brown","navy"],
        "aqua": ["white","navy"]
    }
    return table.get((color or "").lower(), ["white","black"])

def _compose_query(base, color=None, vibe=None, pattern=None):
    """General items (tops/bottoms). Keep pattern when not 'solid'."""
    parts = [base]
    if color: parts.append(color)
    if pattern and pattern != "solid": parts.append(pattern)
    if vibe: parts.append(vibe)
    parts.append("India")
    parts.append("buy online")
    return " ".join(p for p in parts if p).strip()

def _compose_query_acc(base, color=None, vibe=None):
    """Accessories/bags: ignore pattern, keep buy intent."""
    parts = [base]
    if color: parts.append(color)
    if vibe: parts.append(vibe)
    parts.append("India")
    parts.append("buy online")
    return " ".join(p for p in parts if p).strip()

def _title_and_tags(item: str, title_words: int = 3):
    STOP = {"india","buy","online"}
    words = [w for w in (item or "").split() if w.lower() not in STOP]
    title = " ".join(words[:title_words]).title() if words else item
    tags = words[title_words:]
    return title, tags


TOP_LIKE = {
    "top","shirt","t-shirt","tee","blouse","kurta","saree blouse",
    "hoodie","sweatshirt","sweater","cardigan","tank","camisole","crop","crop top"
}
BOTTOM_LIKE = {"bottom","jeans","trousers","pants","skirt","shorts","lehenga","palazzos"}
ACCESSORY_LIKE = {"scarf","dupatta","stole","shawl","belt","tie","earrings","necklace","jewelry","jewellery"}
ONE_PIECE = {"dress","gown","saree","jumpsuit","co-ord","co-ords","co-ord set"}

# Footwear specifically recommended when the uploaded item is a saree
SAREE_FOOTWEAR = [
    "kolhapuri sandals",
    "juttis",
    "mojari",
    "block heels",
    "strappy heels",
    "golden sandals"
]


def _pack(items, vibe, username, total_k=6):
    prefs = load_user_prefs(username or "")
    packed = []
    for it in items:
        links = search_links_for_query(it, vibe=vibe, user_prefs=prefs, total_k=total_k)
        if not links:
            continue
        title, tags = _title_and_tags(it, title_words=3)
        packed.append({"item": it, "title": title, "tags": tags, "links": links})
    return packed


def build_queries(pred_type, color, vibe, pattern, username):
    """Return 4 sections: tops, bottoms, accessories, purses (each a list of card dicts)."""
    ptype = (pred_type or "").lower()
    comps = complement_colors(color)
    c1 = comps[0]
    c2 = comps[-1] if len(comps) > 1 else comps[0]

    tops = []
    bottoms = []

    if ptype in TOP_LIKE:
        # uploaded a top -> suggest bottoms
        bottoms = [
            _compose_query("high waist jeans", c1, vibe, pattern),
            _compose_query("straight trousers", c2, vibe, pattern),
            _compose_query("midi skirt", c1, vibe, pattern),
        ]
    elif ptype in BOTTOM_LIKE:
        # uploaded a bottom -> suggest tops
        tops = [
            _compose_query("linen shirt", c1, vibe, pattern),
            _compose_query("satin camisole", c2, vibe, pattern),
            _compose_query("fitted t-shirt", c1, vibe, pattern),
        ]
    elif ptype in ACCESSORY_LIKE:
        # scarf/dupatta/etc. -> suggest both tops and bottoms
        tops = [
            _compose_query("solid blouse", c1, vibe, pattern),
            _compose_query("linen kurta", c2, vibe, pattern),
            _compose_query("basic tee", c1, vibe, pattern),
        ]
        bottoms = [
            _compose_query("high waist jeans", c2, vibe, pattern),
            _compose_query("wide leg trousers", c1, vibe, pattern),
            _compose_query("a-line skirt", c2, vibe, pattern),
        ]
    elif ptype in ONE_PIECE:
        # dress/saree/jumpsuit -> accessories focus
        pass
    else:
        # unknown -> safe mix
        tops = [
            _compose_query("linen shirt", c1, vibe, pattern),
            _compose_query("fitted t-shirt", c2, vibe, pattern),
        ]
        bottoms = [
            _compose_query("straight trousers", c1, vibe, pattern),
            _compose_query("midi skirt", c2, vibe, pattern),
        ]

    # accessories/bags: do NOT pass pattern (handled inside _compose_query_acc)
    accessories = [
        _compose_query_acc("minimal necklace", None, vibe),
        _compose_query_acc("hoop earrings", None, vibe),
        _compose_query_acc("slim belt", None, vibe),
    ]
    ## __SAREE_FOOTWEAR_OVERRIDE__
    if ptype == "saree":
        # For saree: don't push tops/bottoms; prefer footwear instead of general accessories
        tops = []
        bottoms = []
        accessories = [ _compose_query_acc(name, None, vibe) for name in SAREE_FOOTWEAR ]

    purses = [
        _compose_query_acc("tote bag", c2, vibe),
        _compose_query_acc("crossbody bag", c1, vibe),
    ]

    return (
        _pack(tops, vibe, username),
        _pack(bottoms, vibe, username),
        _pack(accessories, vibe, username),
        _pack(purses, vibe, username),
    )

def get_recommendations_dynamic(pred_type, color_name, vibe, pattern=None, username=None):
    tops, bottoms, accessories, purses = build_queries(
        pred_type=pred_type, color=color_name, vibe=vibe, pattern=pattern, username=username
    )
    for section in (tops, bottoms, accessories, purses):
        random.shuffle(section)
    note = f"{(vibe or 'style').title()} • color: {color_name}"
    if pattern: note += f" • pattern: {pattern}"
    return {
        "tops": tops,
        "bottoms": bottoms,
        "accessories": accessories,
        "purse": purses,
        "vibe": note
    }
