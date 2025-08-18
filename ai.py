# ai.py  — CLIP-based analysis (item type, vibe, color, pattern)
import os
from functools import lru_cache
from typing import Tuple, List

from PIL import Image, ImageOps
import torch
torch.set_num_threads(min(2, max(1, torch.get_num_threads())))  # keep CPU threads modest

# Try open_clip (fast to use, first run downloads weights once)
try:
    import open_clip
except Exception as e:
    raise RuntimeError(
        "open_clip is required. Install it in your venv:\n\n"
        "python -m pip install open_clip_torch torch torchvision pillow"
    ) from e

# -----------------------------
# Label spaces (tweak freely)
# -----------------------------
ITEM_LABELS: List[str] = [
    # tops
    "top", "t-shirt", "shirt", "blouse", "kurta", "sweater", "hoodie",
    "jacket", "cardigan", "saree blouse",
    # one-piece
    "dress", "gown", "saree", "sari", "jumpsuit",
    # bottoms
    "bottom", "jeans", "trousers", "pants", "skirt", "shorts", "lehenga",
    # accessories
    "scarf", "belt", "necklace", "earrings", "handbag", "tote bag", "crossbody bag",
]

VIBE_LABELS: List[str] = [
    "casual", "office", "smart casual", "party", "vacation",
    "date night", "festive", "wedding", "streetwear", "sporty",
]

# You can extend at runtime by dropping patterns.json next to this file:
# { "labels": ["solid","striped","checked","floral","polka dots", ...] }
DEFAULT_PATTERN_LABELS: List[str] = [
    "solid", "ribbed", "striped", "checked", "gingham", "herringbone",
    "floral", "paisley", "polka dots", "abstract", "animal print",
    "smocked", "embroidered", "lace", "denim", "knit",
]

def _load_pattern_labels() -> List[str]:
    path = os.path.join(os.path.dirname(__file__), "patterns.json")
    if os.path.exists(path):
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            labels = [s.strip() for s in (data.get("labels") or []) if s.strip()]
            if labels:
                return labels
        except Exception:
            pass
    return DEFAULT_PATTERN_LABELS

PATTERN_LABELS: List[str] = _load_pattern_labels()

# -----------------------------
# Model loading (cached)
# -----------------------------
# Model loading (cached)
@lru_cache(maxsize=1)
def load_model():
    """
    Loads OpenCLIP model + tokenizer once, cached across requests.
    Uses a small but strong ViT-B/32 checkpoint by default.
    """
    model_name = os.getenv("CLIP_MODEL_NAME", "ViT-B-32")
    pretrained = os.getenv("CLIP_PRETRAINED", "openai")

    # Choose best available device
    device = "cpu"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        device = "mps"      # Apple Silicon
    elif torch.cuda.is_available():
        device = "cuda"     # Nvidia

    # create model & preprocess; then move model to device
    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained
    )
    model.to(device)
    tokenizer = open_clip.get_tokenizer(model_name)
    model.eval()
    return model, preprocess, tokenizer, device

# -----------------------------
# Helpers
# -----------------------------
def _encode_text(prompts: List[str], tokenizer, model, device) -> torch.Tensor:
    with torch.no_grad():
        tok = tokenizer(prompts)
        feats = model.encode_text(tok.to(device))
        feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats

def _encode_image(img: Image.Image, preprocess, model, device) -> torch.Tensor:
    with torch.no_grad():
        tens = preprocess(img).unsqueeze(0).to(device)
        feats = model.encode_image(tens)
        feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats

def zero_shot(img: Image.Image, labels: List[str], template: str) -> str:
    """
    Simple zero-shot classification using CLIP.
    template e.g. "a photo of a {} outfit" or "a {} pattern fabric"
    """
    model, preprocess, tokenizer, device = load_model()
    text_prompts = [template.format(l) for l in labels]
    text_feats = _encode_text(text_prompts, tokenizer, model, device)
    img_feats = _encode_image(img, preprocess, model, device)
    # cosine similarity
    sims = (img_feats @ text_feats.t()).squeeze(0)
    idx = int(torch.argmax(sims).item())
    return labels[idx]

# Dominant color (fast + simple)
def dominant_color(img: Image.Image) -> Tuple[str, str]:
    """
    Returns (rough_name, hex). We keep naming simple and robust.
    """
    small = img.copy()
    small.thumbnail((64, 64))
    colors = small.convert("RGB").getcolors(64 * 64) or []
    if not colors:
        return ("unknown", "#aaaaaa")
    _, rgb = max(colors, key=lambda x: x[0])
    r, g, b = rgb
    hexv = "#{:02x}{:02x}{:02x}".format(r, g, b)

    # rough name buckets
    def _bucket(r, g, b):
        if max(r, g, b) < 40: return "black"
        if min(r, g, b) > 215: return "white"
        if r > 200 and g < 80 and b < 80: return "red"
        if r > 200 and g > 200 and b < 120: return "yellow"
        if r < 120 and g > 170 and b < 120: return "green"
        if r < 100 and g < 100 and b > 170: return "blue"
        if r > 180 and g < 120 and b > 180: return "pink"
        if r > 200 and g > 140 and b > 90: return "tan"
        if r > 150 and g > 150 and b > 150: return "light grey"
        if r < 120 and g < 120 and b < 120: return "dark grey"
        return "neutral"
    return (_bucket(r, g, b), hexv)

# -----------------------------
# Public: analyze_image
# -----------------------------
def analyze_image(image_path: str) -> dict:
    """
    Returns:
      {
        "raw_label": <best item label>,
        "pred_type": "top" | "bottom" | <raw_label for non-clothing>,
        "vibe": <vibe word>,
        "color_name": <rough color>,
        "color_hex": <#RRGGBB>,
        "pattern": <pattern word>
      }
    """
    # Open + fix rotation + RGB
    img = Image.open(image_path)
    try:
        img = ImageOps.exif_transpose(img)  # fix iPhone/Android rotation
    except Exception:
        pass
    img = img.convert("RGB")

    # Zero-shot predictions
    item_label  = zero_shot(img, ITEM_LABELS, template="a photo of a {}")
    # Disambiguate saree vs lehenga if needed
    if item_label in ["lehenga"]:
        cand = ["saree drape","saree","sari","lehenga set","lehenga"]
        dis = zero_shot(img, cand, template="a photo of a {} outfit")
        if dis in ["saree drape","saree","sari"]:
            item_label = "saree"  # DISAMBIG_SAREE_LEHENGA

    vibe_label  = zero_shot(img, VIBE_LABELS, template="a {} outfit")
    color_name, color_hex = dominant_color(img)
    pattern     = zero_shot(img, PATTERN_LABELS, template="a {} pattern")

    # Normalize into 'top' / 'bottom' when sensible
    if item_label in ["saree","sari"]:
        pred_type = "saree"
    elif item_label in ["top", "t-shirt", "shirt", "blouse", "kurta",
                      "sweater", "hoodie", "jacket", "cardigan", "saree blouse", "dress", "gown"]:
        pred_type = "top"
    elif item_label in ["saree","sari"]:
        pred_type = "saree"
    elif item_label in ["bottom", "jeans", "trousers", "pants", "skirt", "shorts", "lehenga", "jumpsuit"]:
        pred_type = "bottom"
    else:
        pred_type = item_label  # accessories etc.

    return {
        "raw_label": item_label,
        "pred_type": pred_type,
        "vibe": vibe_label,
        "color_name": color_name,
        "color_hex": color_hex,
        "pattern": pattern
    }
