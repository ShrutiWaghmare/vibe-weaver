# retailers_provider.py — live retailer discovery for India-first + niche mix
import os, re, json, random
from time import time
from urllib.parse import urlparse, quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

try:
    import tldextract
except Exception:
    tldextract = None

try:
    from duckduckgo_search import DDGS
except Exception:
    DDGS = None

# ---------------- Cache (in-memory) ----------------
CACHE = {}
CACHE_TTL = int(os.getenv("LINKS_CACHE_TTL", "1800"))  # 30 min

def _ck(query, vibe, prefs_key, total_k):
    return f"{query}|{vibe}|{prefs_key}|{total_k}"

def _cache_get(key):
    ent = CACHE.get(key)
    if not ent: return None
    if time() - ent["ts"] > CACHE_TTL:
        CACHE.pop(key, None)
        return None
    return ent["val"]

def _cache_set(key, val):
    CACHE[key] = {"val": val, "ts": time()}

# ---------------- Core domain sets ----------------
MAINSTREAM_DOMAINS = {
    "amazon.in","flipkart.com","myntra.com","ajio.com","nykaafashion.com",
    "tatacliq.com","tatacliq.in","zara.com","hm.com","asos.com"
}
BLOCK_DOMAINS = {
    "pinterest.com","instagram.com","facebook.com","twitter.com","x.com",
    "youtube.com","reddit.com","quora.com","medium.com"
}

INDIAN_BRAND_DOMAINS = {
    # marketplaces
    "myntra.com","ajio.com","nykaafashion.com","tatacliq.com","tatacliq.in",
    "flipkart.com","amazon.in",
    # apparel
    "fablestreet.com","thelabellife.com","globaldesi.in","andindia.com",
    "fabindia.com","wforwoman.com","soch.com","aurelia.com","houseofindya.com",
    "bunaai.com","kharakapas.com","rawmango.com","goodearth.in","nicobar.com",
    "jaypore.com","tjori.com","suta.in","okhai.org","the-souled-store.com",
    # footwear / street
    "vegnonveg.com","superkicks.in",
    # bags
    "capresebags.com","baggit.com","lavieworld.com","hidesign.com",
    "damilano.com","linoperros.com","zouk.co.in",
    # jewellery
    "caratlane.com","bluestone.com","tribeamrapali.com","amama.in","voylla.com",
}

SITE_SEARCH_TEMPLATES = {
    "myntra.com":        "https://www.myntra.com/{q}",
    "ajio.com":          "https://www.ajio.com/search/?text={q}",
    "nykaafashion.com":  "https://www.nykaafashion.com/search?q={q}",
    "tatacliq.com":      "https://www.tatacliq.com/search/?text={q}",
    "flipkart.com":      "https://www.flipkart.com/search?q={q}",
    "amazon.in":         "https://www.amazon.in/s?k={q}",
    "zara.com":          "https://www.zara.com/in/en/search?searchTerm={q}",
    "hm.com":            "https://www2.hm.com/en_in/search-results.html?q={q}",
    "fablestreet.com":   "https://www.fablestreet.com/search?q={q}",
    "thelabellife.com":  "https://www.thelabellife.com/search?q={q}",
    "globaldesi.in":     "https://globaldesi.in/catalogsearch/result/?q={q}",
    "andindia.com":      "https://www.andindia.com/search?q={q}",
    "fabindia.com":      "https://www.fabindia.com/search?q={q}",
    "wforwoman.com":     "https://wforwoman.com/search?q={q}",
    "soch.com":          "https://www.soch.com/catalogsearch/result/?q={q}",
    "aurelia.com":       "https://shopforaurelia.com/search?q={q}",
    "houseofindya.com":  "https://www.houseofindya.com/search?q={q}",
    "bunaai.com":        "https://bunaai.com/search?q={q}",
    "kharakapas.com":    "https://kharakapas.com/search?q={q}",
    "rawmango.com":      "https://www.rawmango.com/search?q={q}",
    "goodearth.in":      "https://www.goodearth.in/search?q={q}",
    "nicobar.com":       "https://www.nicobar.com/search?q={q}",
    "jaypore.com":       "https://www.jaypore.com/search?q={q}",
    "tjori.com":         "https://www.tjori.com/search?q={q}",
    "suta.in":           "https://www.suta.in/search?q={q}",
    "okhai.org":         "https://okhai.org/search?q={q}",
    "the-souled-store.com":"https://www.thesouledstore.com/search?q={q}",
    "vegnonveg.com":     "https://www.vegnonveg.com/search?q={q}",
    "superkicks.in":     "https://superkicks.in/pages/search-results?q={q}",
    # bags
    "capresebags.com":   "https://www.capresebags.com/search?type=product&q={q}",
    "baggit.com":        "https://baggit.com/search?q={q}",
    "lavieworld.com":    "https://www.lavieworld.com/search?q={q}",
    "hidesign.com":      "https://www.hidesign.com/catalogsearch/result/?q={q}",
    "damilano.com":      "https://www.damilano.com/catalogsearch/result/?q={q}",
    "linoperros.com":    "https://www.lino-perros.com/search?q={q}",
    "zouk.co.in":        "https://zouk.co.in/search?q={q}",
    # jewellery
    "caratlane.com":     "https://www.caratlane.com/search?q={q}",
    "bluestone.com":     "https://www.bluestone.com/search?q={q}",
    "tribeamrapali.com": "https://www.tribeamrapali.com/search?q={q}",
    "amama.in":          "https://www.amama.in/search?q={q}",
    "voylla.com":        "https://www.voylla.com/search?type=product&q={q}",
}

ECOMMERCE_HINTS = (
    "product","products","/p/","/dp/","/item","/catalog","/shop","/store",
    "/collections","/search","/category","?q=","/products/"
)

CATEGORY_KEYWORDS = {
    "bag": {"bag","handbag","crossbody","sling","tote","satchel"},
    "earrings": {"earring","earrings","jhumka","studs","hoops"},
    "necklace": {"necklace","pendant","choker","jewellery","jewelry"},
    "belt": {"belt","waist belt","skinny belt"},
    "jeans": {"jeans","denim"},
    "trousers": {"trousers","pants","chinos"},
    "skirt": {"skirt","midi skirt","mini skirt","a-line"},
    "shirt": {"shirt"},
    "tshirt": {"tshirt","t-shirt","tee"},
    "kurta": {"kurta"},
    "dress": {"dress","gown"},
    "saree": {"saree","sari"},
}

CATEGORY_ALLOWED_DOMAINS = {
    "belt": {
        "myntra.com","ajio.com","nykaafashion.com","tatacliq.com",
        "hm.com","zara.com","thelabellife.com","fablestreet.com"
    },
    "bag": {
        "myntra.com","ajio.com","nykaafashion.com","tatacliq.com",
        "zara.com","hm.com","thelabellife.com",
        "capresebags.com","baggit.com","lavieworld.com","hidesign.com",
        "damilano.com","linoperros.com","zouk.co.in"
    },
    "earrings": {
        "nykaafashion.com","ajio.com","myntra.com","tatacliq.com",
        "jaypore.com","tjori.com","caratlane.com","bluestone.com",
        "tribeamrapali.com","amama.in","voylla.com"
    },
    "necklace": {
        "nykaafashion.com","ajio.com","myntra.com","tatacliq.com",
        "jaypore.com","tjori.com","caratlane.com","bluestone.com",
        "tribeamrapali.com","amama.in","voylla.com"
    },
    "jeans": {"myntra.com","ajio.com","nykaafashion.com","tatacliq.com","zara.com","hm.com"},
    "trousers": {"myntra.com","ajio.com","nykaafashion.com","tatacliq.com","zara.com","hm.com","fablestreet.com","andindia.com","globaldesi.in"},
    "skirt": {"myntra.com","ajio.com","nykaafashion.com","tatacliq.com","zara.com","hm.com","thelabellife.com"},
    "shirt": {"myntra.com","ajio.com","nykaafashion.com","tatacliq.com","zara.com","hm.com","fablestreet.com"},
    "tshirt": {"myntra.com","ajio.com","nykaafashion.com","tatacliq.com","zara.com","hm.com","the-souled-store.com"},
    "kurta": {"nykaafashion.com","ajio.com","myntra.com","tatacliq.com","fabindia.com","wforwoman.com","soch.com","aurelia.com"},
    "dress": {"myntra.com","ajio.com","nykaafashion.com","tatacliq.com","zara.com","hm.com","thelabellife.com","andindia.com"},
    "saree": {"nykaafashion.com","ajio.com","myntra.com","tatacliq.com","jaypore.com","tjori.com","suta.in","okhai.org"}
}

DOMAIN_POSITIVE = {
    "nykaafashion.com": ["\"@type\":\"Product\"", "product-card", "/p/"],
    "nicobar.com":      ["\"@type\":\"Product\"", "product-grid", "/products/"],
    "myntra.com":       ["product-base", "results-base", "\"@type\":\"Product\""],
    "ajio.com":         ["\"@type\":\"Product\"", "prod-name", "/p/"],
    "tatacliq.com":     ["\"@type\":\"Product\"", "plp", "/product/"],
    "zara.com":         ["product", "\"@type\":\"Product\"", "/search?searchTerm="],
    "hm.com":           ["product-item", "\"@type\":\"Product\""],
    "caratlane.com":    ["product-card","\"@type\":\"Product\""],
    "bluestone.com":    ["product-card","\"@type\":\"Product\""],
    "capresebags.com":  ["product-grid","\"@type\":\"Product\""],
    "baggit.com":       ["product-grid","\"@type\":\"Product\""],
    "lavieworld.com":   ["product-grid","\"@type\":\"Product\""],
    "hidesign.com":     ["product-list","\"@type\":\"Product\""],
    "damilano.com":     ["catalog-product","\"@type\":\"Product\""],
    "linoperros.com":   ["product-grid","\"@type\":\"Product\""],
    "zouk.co.in":       ["product-grid","\"@type\":\"Product\""],
    "tribeamrapali.com":["product-grid","\"@type\":\"Product\""],
    "amama.in":         ["product-grid","\"@type\":\"Product\""],
    "voylla.com":       ["product-grid","\"@type\":\"Product\""],
}
DOMAIN_NORESULT = {
    "nykaafashion.com": ["no results", "did not match any products"],
    "nicobar.com":      ["no products", "no results"],
    "myntra.com":       ["no results found"],
    "ajio.com":         ["no results"],
    "tatacliq.com":     ["0 results","no products"],
}

# ---------------- Utilities ----------------
def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc or ""
    except Exception:
        return ""
    return host.lower().lstrip("www.")

def _retailer_name_from_domain(domain: str) -> str:
    known = {"nykaafashion.com":"Nykaa Fashion","tatacliq.com":"Tata CLiQ","hm.com":"H&M"}
    if domain in known: return known[domain]
    base = tldextract.extract(domain).domain if tldextract else (domain.split(".")[-2] if "." in domain else domain)
    return base.replace("-", " ").title()

def _favicon_for(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=32"

def _is_mainstream(domain: str) -> bool:
    return domain in MAINSTREAM_DOMAINS

def _is_indian(domain: str) -> bool:
    d = domain.lower()
    return d.endswith(".in") or d in INDIAN_BRAND_DOMAINS

def _good_link(url: str) -> bool:
    d = _domain(url)
    return bool(d) and d not in BLOCK_DOMAINS

def _dedupe_by_domain(items):
    seen = set(); out = []
    for it in items:
        d = _domain(it.get("url",""))
        if not d or d in seen: continue
        seen.add(d); out.append(it)
    return out

def _infer_category(query: str) -> str|None:
    q = (query or "").lower()
    for cat, keys in CATEGORY_KEYWORDS.items():
        if any(k in q for k in keys):
            return cat
    return None

def _matches_category(cand: dict, cat: str|None) -> bool:
    if not cat: return True
    keys = CATEGORY_KEYWORDS.get(cat, set())
    title = (cand.get("title") or "").lower()
    url   = (cand.get("url") or "").lower()
    return any(k in title or k in url for k in keys)

def _looks_ecom(url: str, domain: str) -> bool:
    u = url.lower()
    return domain in INDIAN_BRAND_DOMAINS or any(h in u for h in ECOMMERCE_HINTS)

def _clean_query_for_site(q: str) -> str:
    return re.sub(r"\b(buy|online|india)\b", "", q, flags=re.I).strip()

def _variants_for_category(query: str, cat: str|None) -> list[str]:
    q0 = _clean_query_for_site(query)
    out = [q0] if q0 else []
    if not cat:
        return out or [query]
    if cat == "belt":
        base = re.sub(r"\bparty\b", "", q0, flags=re.I).strip() or "slim belt"
        out = [base, "women skinny belt", "women slim belt", "women waist belt"]
    elif cat in {"earrings","necklace"}:
        base = re.sub(r"\bparty\b", "", q0, flags=re.I).strip()
        out = [base or cat, f"women {cat}", f"fashion {cat}"]
    elif cat in {"bag"}:
        base = re.sub(r"\bparty\b", "", q0, flags=re.I).strip()
        out = [base or "tote bag", "women tote bag", "women crossbody bag"]
    return list(dict.fromkeys([s for s in out if s])) or [query]

# ---------------- HTTP + validation ----------------
def _http_get(url: str) -> str | None:
    timeout = float(os.getenv("HTTP_TIMEOUT", "6"))
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/124 Safari/537.36"}
    try:
        r = requests.get(url, timeout=timeout, headers=headers)
        if r.status_code != 200: return None
        txt = r.text or ""
        if len(txt) < 1200: return None
        return txt
    except Exception:
        return None

def _page_has_products(html: str, domain: str) -> bool:
    if not html: return False
    low = html.lower()
    for h in DOMAIN_NORESULT.get(domain, []):
        if h in low: return False
    if any(p in low for p in ("no results","0 results","no products found","try removing filters")):
        return False
    for p in DOMAIN_POSITIVE.get(domain, []):
        if p.lower() in low: return True
    if '"@type":"product"' in low or "schema.org/product" in low: return True
    if "₹" in low and ("add to cart" in low or "add to bag" in low or "product" in low): return True
    if low.count("/product") + low.count("/products/") + low.count("/p/") >= 5: return True
    return False

def _page_matches_category(html: str, cat: str|None) -> bool:
    if not html or not cat: return True
    low = html.lower()
    keys = CATEGORY_KEYWORDS.get(cat, set())
    hits = sum(1 for k in keys if k in low)
    return hits >= 2

def _normalize_to_search(cand: dict, raw_query: str):
    url = cand.get("url",""); d = cand.get("domain","")
    if not url or not d: return
    if _looks_ecom(url, d): return
    tpl = SITE_SEARCH_TEMPLATES.get(d)
    if tpl:
        cand["url"] = tpl.format(q=quote_plus(_clean_query_for_site(raw_query)))
        cand["title"] = f"Search: {raw_query} on {d}"

# ---------------- Web search providers ----------------
def _search_serpapi(query: str, max_results: int = 40):
    key = os.getenv("SERPAPI_KEY")
    if not key: return []
    url = "https://serpapi.com/search.json"
    params = {"engine":"google","q":query,"api_key":key,"gl":"in","hl":"en"}
    r = requests.get(url, params=params, timeout=20); r.raise_for_status()
    data = r.json()
    out = []
    for sec in ("shopping_results","organic_results"):
        for res in data.get(sec, []) or []:
            link = res.get("link") or res.get("url")
            if not link or not _good_link(link): continue
            out.append({"url":link, "domain":_domain(link), "title":res.get("title","")})
    return _dedupe_by_domain(out)

def _search_bing(query: str, max_results: int = 40):
    key = os.getenv("BING_KEY")
    if not key: return []
    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": key}
    params = {"q":query,"mkt":"en-IN","count":max_results}
    r = requests.get(url, params=params, headers=headers, timeout=20); r.raise_for_status()
    data = r.json()
    out = []
    for res in (data.get("webPages", {}).get("value") or []):
        link = res.get("url")
        if not link or not _good_link(link): continue
        out.append({"url":link, "domain":_domain(link), "title":res.get("name","")})
    return _dedupe_by_domain(out)

def _search_ddg(query: str, max_results: int = 40):
    if DDGS is None: return []
    out = []
    with DDGS() as ddgs:
        for res in ddgs.text(query, region="in-en", max_results=max_results):
            link = res.get("href") or res.get("url")
            if not link or not _good_link(link): continue
            out.append({"url":link, "domain":_domain(link), "title":res.get("title","")})
    return _dedupe_by_domain(out)

def _provider_results(query: str, max_results: int = 40):
    prov = (os.getenv("SEARCH_PROVIDER") or "ddg").lower()
    if prov == "serpapi":
        items = _search_serpapi(query, max_results); 
        if items: return items
    if prov == "bing":
        items = _search_bing(query, max_results); 
        if items: return items
    return _search_ddg(query, max_results)

# ---------------- Fallback (category-aware) ----------------
FALLBACK_SITES = [
    ("Myntra",        "https://www.myntra.com/{q}"),
    ("AJIO",          "https://www.ajio.com/search/?text={q}"),
    ("Nykaa Fashion", "https://www.nykaafashion.com/search?q={q}"),
    ("Tata CLiQ",     "https://www.tatacliq.com/search/?text={q}"),
    ("FableStreet",   "https://www.fablestreet.com/search?q={q}"),
    ("The Label Life","https://www.thelabellife.com/search?q={q}"),
    ("Jaypore",       "https://www.jaypore.com/search?q={q}"),
    ("Okhai",         "https://okhai.org/search?q={q}"),
    ("Suta",          "https://www.suta.in/search?q={q}"),
    ("Nicobar",       "https://www.nicobar.com/search?q={q}")
]
def _fallback_site_search(query: str, needed: int, cat: str|None):
    if needed <= 0: return []
    q = _clean_query_for_site(query)
    items = []
    if cat and cat in CATEGORY_ALLOWED_DOMAINS:
        domains = list(CATEGORY_ALLOWED_DOMAINS[cat]); random.shuffle(domains)
        for d in domains:
            tpl = SITE_SEARCH_TEMPLATES.get(d)
            if not tpl: continue
            url = tpl.format(q=quote_plus(q))
            items.append({"url": url, "domain": d, "title": f"Search: {query}"})
            if len(items) == needed: break
        return items
    random.shuffle(FALLBACK_SITES)
    for _, urltpl in FALLBACK_SITES:
        url = urltpl.format(q=quote_plus(q))
        dom = _domain(url)
        items.append({"url": url, "domain": dom, "title": f"Search: {query}"})
        if len(items) == needed: break
    return items

# ---------------- Public: main API ----------------
def search_links_for_query(query: str, vibe: str = "", user_prefs: dict | None = None, total_k: int = 6) -> list[dict]:
    """
    Returns [{retailer, url, favicon}] after:
      - India-first + niche/mainstream mix
      - category allowlists
      - homepage -> site-search rewriting
      - fast parallel validation of product/search pages
      - in-memory caching
    """
    user_prefs = user_prefs or {}
    prefs_key = (user_prefs or {}).get("prefer_tier", "balanced")
    cache_key = _ck(query, vibe, prefs_key, total_k)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    avoid = set((user_prefs.get("avoid_domains") or []))
    prefer = (user_prefs.get("prefer_tier") or "balanced").lower()

    indian_share = float(os.getenv("INDIAN_SHARE", "0.7"))
    niche_share  = float(os.getenv("NICHE_SHARE", "0.5"))
    if prefer == "niche":        niche_share = max(niche_share, 0.6)
    elif prefer == "mainstream": niche_share = min(niche_share, 0.3)

    india_target = max(1, int(round(total_k * indian_share)))
    niche_target = max(1, int(round(total_k * niche_share)))

    cat = _infer_category(query)

    # 1) candidate collection
    variants = _variants_for_category(query, cat)
    candidates = []
    for v in variants:
        search_q = f"{v} {vibe or ''} buy online India".strip()
        items = _provider_results(search_q, max_results=30)
        if items: candidates.extend(items)
        if len(candidates) >= 60: break

    # 2) filter + normalize
    allowed = CATEGORY_ALLOWED_DOMAINS.get(cat, None)
    filtered = []
    for c in candidates:
        url = c.get("url",""); d = c.get("domain","")
        if not url or not d or d in BLOCK_DOMAINS or d in avoid: continue
        if allowed and d not in allowed: continue
        if not _matches_category(c, cat): continue
        if not _looks_ecom(url, d):
            if d in SITE_SEARCH_TEMPLATES:
                _normalize_to_search(c, query)
            else:
                continue
        filtered.append(c)

    # 3) buckets
    IN_MAIN, IN_NICHE, OUT_MAIN, OUT_NICHE = [], [], [], []
    for c in filtered:
        d = c["domain"]
        is_ind = _is_indian(d)
        is_main = _is_mainstream(d)
        (IN_MAIN if (is_ind and is_main) else
         IN_NICHE if (is_ind and not is_main) else
         OUT_MAIN if (not is_ind and is_main) else
         OUT_NICHE).append(c)
    for lst in (IN_MAIN, IN_NICHE, OUT_MAIN, OUT_NICHE):
        random.shuffle(lst)

    queue = []
    queue.extend(IN_NICHE[: india_target // 2])
    queue.extend(IN_MAIN[: max(0, india_target - (india_target // 2))])
    have_niche = sum(1 for x in queue if x in IN_NICHE or x in OUT_NICHE)
    if have_niche < niche_target:
        need = niche_target - have_niche
        extra_in = IN_NICHE[len([x for x in queue if x in IN_NICHE]):]
        queue.extend(extra_in[:need])
        need -= min(need, len(extra_in))
        if need > 0:
            queue.extend(OUT_NICHE[:need])
    pools = [IN_MAIN, OUT_MAIN, IN_NICHE, OUT_NICHE]
    seen_urls = {x.get("url") for x in queue}
    for p in pools:
        for r in p:
            if len(queue) >= 3 * total_k: break
            if r.get("url") not in seen_urls:
                queue.append(r); seen_urls.add(r.get("url"))

    # 4) parallel validation
    maxcheck = int(os.getenv("VALIDATION_MAXCHECK", "6"))
    conc = int(os.getenv("VALIDATION_CONCURRENCY", "8"))
    to_check = queue[:maxcheck]
    validated = []

    def _validate(cand):
        d = cand["domain"]; url = cand["url"]
        html = _http_get(url)
        if not html and d in SITE_SEARCH_TEMPLATES:
            _normalize_to_search(cand, query)
            html = _http_get(cand["url"])
        if not html: return None
        if not _page_has_products(html, d): return None
        if not _page_matches_category(html, cat): return None
        return cand

    with ThreadPoolExecutor(max_workers=max(1, conc)) as ex:
        futures = [ex.submit(_validate, c) for c in to_check]
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                validated.append(res)
                if len(validated) >= total_k:
                    break

    if len(validated) < total_k:
        need = total_k - len(validated)
        fb = _fallback_site_search(query, need * 2, cat)
        with ThreadPoolExecutor(max_workers=max(1, conc)) as ex:
            futures = [ex.submit(_validate, c) for c in fb]
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    validated.append(res)
                    if len(validated) >= total_k:
                        break

    # 5) map to UI
    out, seen_dom = [], set()
    for c in validated:
        d = c["domain"]
        if d in seen_dom: continue
        seen_dom.add(d)
        out.append({
            "retailer": _retailer_name_from_domain(d),
            "url": c["url"],
            "favicon": _favicon_for(d)
        })
        if len(out) == total_k: break

    _cache_set(cache_key, out)
    return out

# --------------- User prefs (optional) ---------------
def load_user_prefs(username: str) -> dict:
    if not username: return {}
    os.makedirs("user_prefs", exist_ok=True)
    path = os.path.join("user_prefs", f"{username}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    default = {"prefer_tier": "balanced", "avoid_domains": []}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
    except Exception:
        pass
    return default
