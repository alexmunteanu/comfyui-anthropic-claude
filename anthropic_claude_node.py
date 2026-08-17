"""
Anthropic Claude Node for ComfyUI (V3 API)
Provides a node that calls the Anthropic Claude API with text and image inputs.
© 2026 Created with ❤️ by Alex Munteanu | alexmunteanu.com
"""

import os
import hashlib
import base64
import re
import time
from io import BytesIO
from pathlib import Path
from typing_extensions import override

import numpy as np
from PIL import Image

import folder_paths
from comfy_api.latest import ComfyExtension, io

from . import safe_fs

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Error text
# ---------------------------------------------------------------------------

# Anything shaped like an API key.
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")

# A username and password carried in a URL, as a proxy address does. Handled
# before the path rules, because the "//" would otherwise survive them.
_CREDENTIALS_RE = re.compile(r"//[^/\s:@]+:[^/\s@]+@")

# Local paths. A folder name is allowed to contain spaces, which is why these
# are built out of segments rather than one run of non-space characters:
# "C:\Program Files\..." would otherwise be redacted only as far as the first
# space and hand back the rest of the path intact.
#
# A segment may hold spaces when another separator follows it, since that
# proves the path continues. The last segment may hold spaces only when it
# ends in a file extension; otherwise it stops at the first space, so an error
# reading "C:\a\b failed to open" gives up the path and keeps the sentence.
_SEG_INNER = r"[^\\/\r\n\"']"
_SEG_LAST = r"[^\s\\/\r\n\"']"
_TAIL = "(?:" + _SEG_LAST + r"*(?: " + _SEG_LAST + r"+)*?\.[A-Za-z0-9]{1,8}|" + _SEG_LAST + "*)"

# The lookbehind keeps https:// intact, since the "s:/" in it would otherwise
# read as a drive letter.
_WINPATH_RE = re.compile(
    r"(?<![A-Za-z])[A-Za-z]:[\\/](?:" + _SEG_INNER + r"*[\\/])*" + _TAIL)
_UNCPATH_RE = re.compile(r"\\\\(?:" + _SEG_INNER + r"*[\\/])*" + _TAIL)
_POSIXPATH_RE = re.compile(
    r"/(?:home|Users|root|var|tmp|opt|etc|mnt|srv)/(?:" + _SEG_INNER + r"*/)*" + _TAIL)

MAX_ERROR_CHARS = 400


def _safe_error_text(exc):
    """A short description of a failure, with local detail taken out.

    What the API says about the request is kept, because that is usually what
    tells the user what to change. What is removed is anything describing this
    machine rather than the request: install paths, which carry the account
    name, and anything shaped like a key. Cleaning happens once, here, at the
    point the message is made, so the footer, the routes and the copy written
    into the history entry all get the same cleaned text.
    """
    try:
        text = str(exc)
    except Exception:
        text = ""
    text = " ".join(text.split())
    text = _SECRET_RE.sub("sk-***", text)
    text = _CREDENTIALS_RE.sub("//***:***@", text)
    text = _WINPATH_RE.sub("<path>", text)
    text = _UNCPATH_RE.sub("<path>", text)
    text = _POSIXPATH_RE.sub("<path>", text)
    if len(text) > MAX_ERROR_CHARS:
        text = text[:MAX_ERROR_CHARS] + "..."
    return text or type(exc).__name__


# ---------------------------------------------------------------------------
# Instruction templates
# ---------------------------------------------------------------------------

BUILTIN_TEMPLATES = {
    "FLUX.2": "flux.md",
    "FLUX.2 Edit": "flux_edit.md",
    "FLUX 3 Video": "flux_3_video.md",
    "Gemini Omni Flash": "gemini_omni_flash.md",
    "GPT Image 2": "gpt_image_2.md",
    "GPT Image 2 Edit": "gpt_image_2_edit.md",
    "Grok Imagine Video": "grok.md",
    "Grok Imagine Video Edit": "grok_edit.md",
    "Grok Imagine Image": "grok_image.md",
    "HunyuanImage 3.0": "hunyuan_image.md",
    "Hunyuan Video 1.5": "hunyuan_video.md",
    "Ideogram 4.0": "ideogram.md",
    "Kling Avatar 2.0": "kling_avatar.md",
    "Kling 2.1 & 2.5": "kling_2-1_2-5.md",
    "Kling 2.6": "kling_2-6.md",
    "Kling 3.0 Motion Control": "kling_2-6_mc.md",
    "Kling O1": "kling_o1.md",
    "Kling 3.0": "kling_v3.md",
    "Kling 3.0 Omni": "kling_o3.md",
    "Krea 2": "krea_2.md",
    "LTX 2 Pro": "ltx2pro.md",
    "LTX 2.3": "ltx_2-3.md",
    "Luma Ray 2 & 3": "luma.md",
    "Luma Ray 3.2": "luma_ray_3-2.md",
    "Luma Uni-1 & Max": "luma_uni-1.md",
    "Luma Uni-1 Edit": "luma_uni-1_edit.md",
    "MiniMax H3": "minimax_h3.md",
    "MiniMax Hailuo 2.3": "minimax.md",
    "Nano Banana 2": "nano_banana_2.md",
    "Nano Banana 2 Edit": "nano_banana_2_edit.md",
    "Nano Banana Pro": "nano_banana_pro.md",
    "Nano Banana Pro Edit": "nano_banana_pro_edit.md",
    "Pika 2.2 & 2.5": "pika.md",
    "PixVerse V6": "pixverse.md",
    "Qwen Image 2.0": "qwen_image.md",
    "Qwen Image 2.0 Edit": "qwen_edit.md",
    "Qwen Image 3.0": "qwen_image_3.md",
    "Qwen Image 3.0 Edit": "qwen_image_3_edit.md",
    "Recraft V4 & V4.1": "recraft.md",
    "Reve 2.1": "reve.md",
    "Runway Gen-4 & 4.5": "runway.md",
    "Runway Aleph 2 Edit": "runway_edit.md",
    "Seedance 1.0": "seedance_1-0.md",
    "Seedance 1.5": "seedance_1-5.md",
    "Seedance 2.0": "seedance_2-0.md",
    "Seedance 2.5": "seedance_2-5.md",
    "Seedance 2.5 Edit": "seedance_2-5_edit.md",
    "Seedream 4.0 & 4.5": "seedream.md",
    "Seedream 5.0 Lite": "seedream_5_lite.md",
    "Seedream 5.0 Lite Edit": "seedream_5_lite_edit.md",
    "Seedream 5.0 Pro": "seedream_5_pro.md",
    "Seedream Edit": "seedream_edit.md",
    "Sora 2 & 2 Pro": "sora.md",
    "Sora 2 Edit": "sora_edit.md",
    "Veo 3 & 3.1": "veo.md",
    "Vidu Q3": "vidu_q3.md",
    "Wan 2.1 & 2.2": "wan_2-1_2-2.md",
    "Wan 2.5 & 2.6": "wan_2-5_2-6.md",
    "Wan 2.7": "wan_2-7.md",
    "Wan 3.0": "wan_3-0.md",
}

# Maps old display names to their current names so workflows saved before the
# v1.5.22 through v1.5.24 display renames still resolve; consulted only on a
# lookup miss at load time and never listed in the template dropdown. Every
# value must be a live BUILTIN_TEMPLATES key and must never itself be a key
# here: resolution does exactly one hop.
LEGACY_TEMPLATE_ALIASES = {
    "FLUX": "FLUX.2",
    "FLUX Kontext Edit": "FLUX.2 Edit",
    "Ideogram 3": "Ideogram 4.0",
    "Qwen Image": "Qwen Image 2.0",
    "Qwen Image Edit": "Qwen Image 2.0 Edit",
    "Grok": "Grok Imagine Video",
    "Grok Edit": "Grok Imagine Video Edit",
    "Kling V3": "Kling 3.0",
    "Kling V3 Omni": "Kling 3.0 Omni",
    "Kling 2.6 Motion Control": "Kling 3.0 Motion Control",
    "Minimax": "MiniMax Hailuo 2.3",
    "Runway Aleph Edit": "Runway Aleph 2 Edit",
    "Seedance 1.0 & 1.5": "Seedance 1.0",
    "Seedance 2.0 & 2.5": "Seedance 2.5",
    "Seedance 2.0 Edit": "Seedance 2.5 Edit",
    "Luma Ray 3.14": "Luma Ray 3.2",
}


# Largest template accepted or read back, in ENCODED bytes. The biggest
# built-in is a few tens of KB, so this leaves room to spare in both
# directions. One limit in one unit for both ends: counting characters on the
# way in and bytes on the way out let a template of non-Latin text save and
# then read back as empty, since those characters cost three bytes each.
MAX_TEMPLATE_BYTES = 512 * 1024


def _get_templates_dir():
    return Path(__file__).parent / "templates"


def _get_user_templates_dir():
    """The user templates folder, or None if it cannot be reached safely."""
    return safe_fs.ensure_dir_chain(
        folder_paths.get_input_directory(),
        ["comfyui_anthropic_claude", "user_templates"],
    )


def _list_all_template_names():
    names = ["None"] + sorted(BUILTIN_TEMPLATES.keys())
    user_dir = _get_user_templates_dir()
    if user_dir is None:
        return names
    user_names = []
    for child in safe_fs.scan_children(user_dir, want_dir=False):
        # Only offer names that can actually be loaded back, so the dropdown
        # never lists something the loader will then refuse.
        if not child.name.lower().endswith(".md"):
            continue
        if not safe_fs.is_safe_component(child.name):
            continue
        stem = child.name[:-3]
        if stem and stem not in BUILTIN_TEMPLATES and stem not in LEGACY_TEMPLATE_ALIASES:
            user_names.append(stem)
    return names + sorted(user_names)


def _read_template_file(directory, filename):
    """Read one template, or return empty. Never raises, never blocks.

    The file name is checked as a plain name before it is joined to anything,
    so a name spelled as a network location cannot be built into a path at
    all. That matters more than it sounds: joining such a name and then
    resolving it opens a real connection to whatever host it points at, and
    the request sits there until that connection times out, which was
    measured at over forty seconds on an unreachable host.
    """
    if directory is None:
        return ""
    path = safe_fs.descend(directory, [filename])
    if path is None:
        return ""
    raw = safe_fs.read_bytes_verified(path, MAX_TEMPLATE_BYTES)
    if raw is None:
        return ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    # Line endings are normalized because the previous release read these
    # files in text mode, which did it automatically. Eight of the built-in
    # templates are stored with Windows line endings, so skipping this would
    # change the system prompt those eight produce and, with it, the cache
    # key every workflow using them was saved with.
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _load_template(name):
    if not isinstance(name, str) or not name or name == "None":
        return ""
    if name not in BUILTIN_TEMPLATES and name in LEGACY_TEMPLATE_ALIASES:
        name = LEGACY_TEMPLATE_ALIASES[name]
    if name in BUILTIN_TEMPLATES:
        return _read_template_file(_get_templates_dir(), BUILTIN_TEMPLATES[name])
    return _read_template_file(_get_user_templates_dir(), name + ".md")


# ---------------------------------------------------------------------------
# Pricing (USD per 1M tokens: input, output)
# ---------------------------------------------------------------------------

# Exact API model IDs -> (input, output) USD per 1M tokens.
# Verified 2026-08-14 against platform.claude.com/docs/en/about-claude/pricing.
# A trailing -YYYYMMDD snapshot date is stripped before lookup, so the dated
# and undated spellings of one model share a row.
MODEL_PRICING_EXACT = {
    # Mythos-class
    "claude-fable-5": (10.00, 50.00),
    "claude-mythos-5": (10.00, 50.00),
    # Opus
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-5": (5.00, 25.00),
    # Sonnet
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    # Haiku
    "claude-haiku-4-5": (1.00, 5.00),
    # Retired from the direct API. Kept so an old saved workflow naming one
    # still reads correctly; these rates are the published historical ones.
    # Dropping a row does NOT make the cost absent - it makes it silently
    # wrong, because the family fallback below then prices a 2024 model at a
    # 2026 rate. Haiku 3 read 4x over that way before these rows came back.
    "claude-opus-4-1": (15.00, 75.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-3-opus": (15.00, 75.00),
    "claude-3-7-sonnet": (3.00, 15.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-haiku": (0.25, 1.25),
}

# Fallback for models released after this version shipped. Ordered, first
# substring match wins, so the Mythos-class families precede the generic
# tiers. A price from this table is an ESTIMATE and is displayed as one:
# a silent family fallback is exactly what let every Opus model read at 3x
# its real cost, because a wrong number looks identical to a right one.
MODEL_PRICING_FAMILY = [
    ("fable", 10.00, 50.00),
    ("mythos", 10.00, 50.00),
    ("opus", 5.00, 25.00),
    ("sonnet", 2.00, 10.00),
    ("haiku", 1.00, 5.00),
]

# A model may be named with a dated snapshot (-20250514), the moving alias
# (-latest), or a spelled-out zero minor (-0); all three name the same rate.
_MODEL_ID_SUFFIX = re.compile(r"(-\d{8}|-latest|-0)$")


def _normalize_model_id(model):
    """Lowercase and strip ONE trailing snapshot date, -latest, or -0.

    Exactly one, not repeatedly: the vendor's ID grammar carries at most one
    such component, and stripping in a loop would fold a synthetic id like
    claude-opus-4-1-0-latest-20250514 onto a real pricing row.
    """
    if not isinstance(model, str):
        return ""
    return _MODEL_ID_SUFFIX.sub("", model.strip().lower(), count=1)


def _lookup_price(model):
    """Return (input_price, output_price, is_exact) or None if unpriced."""
    key = _normalize_model_id(model)
    if not key:
        return None
    if key in MODEL_PRICING_EXACT:
        input_price, output_price = MODEL_PRICING_EXACT[key]
        return input_price, output_price, True
    for pattern, input_price, output_price in MODEL_PRICING_FAMILY:
        if pattern in key:
            return input_price, output_price, False
    return None


def _calculate_cost(model, input_tokens, output_tokens):
    """Calculate USD cost based on model and token counts."""
    priced = _lookup_price(model)
    if priced is None:
        return None
    input_price, output_price, _is_exact = priced
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def _price_is_exact(model):
    """True when the model has its own published rate, False when the cost
    came from a family fallback and is therefore an estimate."""
    priced = _lookup_price(model)
    return bool(priced) and priced[2]


def _format_cost(cost, exact):
    """Format cost as dollars or cents, marking family-fallback estimates.

    `exact` is required rather than defaulting: a caller that forgot it would
    silently render a guessed family rate as a published one, which is the
    exact failure this release exists to remove.
    """
    if cost is None:
        return "cost: unknown model"
    if cost < 0.01:
        text = f"{cost * 100:.2f}\u00a2"
    else:
        text = f"${cost:.4f}"
    if not exact:
        return f"~{text} (est.)"
    return text


# ---------------------------------------------------------------------------
# Model fetching
# ---------------------------------------------------------------------------

FALLBACK_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
    "claude-opus-4-5",
    "claude-opus-4-1",
    "claude-sonnet-4-0",
    "claude-3-7-sonnet-latest",
    "claude-3-haiku-20240307",
]

_cached_models = None
_models_fetch_time = 0
_startup_warnings = []
_api_error = {"ok": True, "error": "", "error_type": ""}

# Reading the warnings no longer empties the list, so the same problem must
# not be able to add a new line every time a refresh is attempted.
MAX_STARTUP_WARNINGS = 10


def _add_startup_warning(text):
    if text in _startup_warnings or len(_startup_warnings) >= MAX_STARTUP_WARNINGS:
        return
    _startup_warnings.append(text)

# A key typed into the node's error modal is held here for the life of the
# process only. It is deliberately NOT written to os.environ: that would
# persist it process-wide and hand it to every child process ComfyUI spawns.
_session_api_key = ""


def _set_session_api_key(key):
    """Store a key supplied at runtime by the UI. Empty clears it."""
    global _session_api_key
    _session_api_key = (key or "").strip()


def _get_api_key():
    """Resolve the API key: a key entered in the UI this session wins,
    otherwise the CLAUDE_API_KEY environment variable."""
    return _session_api_key or os.environ.get("CLAUDE_API_KEY", "")


_display_to_id = {}
_id_to_display = {}


def _make_display_name(model_id):
    """Convert model ID to friendly display name.
    e.g. 'claude-opus-4-6' -> 'Opus 4.6'
         'claude-sonnet-4-20250514' -> 'Sonnet 4'
         'claude-3-5-sonnet-20241022' -> 'Sonnet 3.5'
         'claude-3-haiku-20240307' -> 'Haiku 3'
    """
    name = model_id.lower()
    if name.startswith("claude-"):
        name = name[7:]

    families = ["opus", "sonnet", "haiku"]

    for family in families:
        if name.startswith(family + "-"):
            rest = name[len(family) + 1:]
            nums = re.findall(r"^\d(?:-\d(?!\d))?", rest)
            if nums:
                version = nums[0].replace("-", ".")
                return f"{family.capitalize()} {version}"
            return family.capitalize()

        idx = name.find(family)
        if idx > 0:
            prefix = name[:idx].rstrip("-")
            parts = [p for p in prefix.split("-") if p.isdigit()]
            if parts:
                version = ".".join(parts)
                return f"{family.capitalize()} {version}"

    return model_id


def _build_model_map(model_ids):
    """Build bidirectional display_name <-> model_id mappings."""
    global _display_to_id, _id_to_display
    _display_to_id = {}
    _id_to_display = {}
    display_names = []

    for mid in model_ids:
        dname = _make_display_name(mid)
        if dname in _display_to_id:
            dname = mid
        _display_to_id[dname] = mid
        _id_to_display[mid] = dname
        display_names.append(dname)

    return display_names


def _resolve_model(display_or_id):
    """Resolve a display name or model ID to the actual API model ID."""
    if display_or_id in _display_to_id:
        return _display_to_id[display_or_id]
    return display_or_id


def _fetch_models():
    """Fetch available models from Anthropic API. Falls back to hardcoded list."""
    global _cached_models, _models_fetch_time

    if _cached_models and (time.time() - _models_fetch_time < 3600):
        return _cached_models

    if not ANTHROPIC_AVAILABLE:
        _api_error.update(ok=False, error="The 'anthropic' package is not installed. Run: pip install anthropic", error_type="missing_package")
        return FALLBACK_MODELS

    api_key = _get_api_key()
    if not api_key:
        _api_error.update(ok=False, error="No API key found. Set the CLAUDE_API_KEY environment variable and restart ComfyUI.", error_type="missing_key")
        return FALLBACK_MODELS

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=3.0)
        response = client.models.list(limit=100)
        models = [m.id for m in response.data]
        if models:
            _cached_models = models
            _models_fetch_time = time.time()
            _api_error.update(ok=True, error="", error_type="")
            return models
    except anthropic.AuthenticationError:
        _api_error.update(ok=False, error="Your API key is invalid or expired. Check your CLAUDE_API_KEY environment variable.", error_type="auth_error")
        _add_startup_warning("Authentication failed: invalid API key")
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        _api_error.update(ok=False, error="Cannot reach the Anthropic API. Check your internet connection.", error_type="connection_error")
        _add_startup_warning("Failed to fetch models: " + _safe_error_text(e))
    except Exception as e:
        _api_error.update(ok=False, error="Failed to connect to the Anthropic API: " + _safe_error_text(e), error_type="unknown")
        _add_startup_warning("Failed to fetch models: " + _safe_error_text(e))

    return FALLBACK_MODELS


def _refresh_models():
    """Force re-fetch models from API. Returns the display names."""
    global _cached_models, _models_fetch_time
    _cached_models = None
    _models_fetch_time = 0
    model_ids = _fetch_models()
    if _api_error["ok"]:
        # The warnings describe a startup that could not reach the API. Once
        # a fetch succeeds they are out of date, and this is now the only
        # thing that clears them: serving them used to empty the list, so
        # whatever asked first got the only copy and the user saw nothing.
        _startup_warnings.clear()
    display_names = _build_model_map(model_ids)
    return display_names


# ---------------------------------------------------------------------------
# Extended thinking schema detection
# ---------------------------------------------------------------------------

def _uses_adaptive_thinking(model_id):
    """Return True if the model requires adaptive thinking schema.
    Opus 4.7+ rejects manual thinking with a 400 error. Mythos Preview defaults to adaptive.
    Older models (Opus 4.6, Sonnet 4.6, and earlier) still support manual thinking."""
    mid = model_id.lower()
    if "mythos" in mid:
        return True
    m = re.search(r"claude-(opus|sonnet|haiku)-(\d+)-(\d+)", mid)
    if m:
        family, major, minor = m.group(1), int(m.group(2)), int(m.group(3))
        if family == "opus" and (major > 4 or (major == 4 and minor >= 7)):
            return True
    return False


def _budget_to_effort(thinking_budget):
    """Map legacy thinking_budget integer to adaptive effort level."""
    if thinking_budget <= 8192:
        return "low"
    if thinking_budget <= 32768:
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Image conversion
# ---------------------------------------------------------------------------

def _tensor_to_base64_images(image_tensor, max_dim=1024):
    """Convert ComfyUI IMAGE tensor [B,H,W,C] to list of base64 JPEG strings.
    Images are resized so neither dimension exceeds max_dim."""
    results = []
    if len(image_tensor.shape) == 3:
        image_tensor = image_tensor.unsqueeze(0)

    for i in range(image_tensor.shape[0]):
        img_np = (image_tensor[i].cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
        pil_img = Image.fromarray(img_np)

        w, h = pil_img.size
        if w > max_dim or h > max_dim:
            scale = max_dim / max(w, h)
            pil_img = pil_img.resize(
                (int(w * scale), int(h * scale)),
                Image.LANCZOS,
            )

        buffer = BytesIO()
        pil_img.save(buffer, format="JPEG", quality=95)
        b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
        results.append(b64_str)

    return results


# ---------------------------------------------------------------------------
# Response cache
# ---------------------------------------------------------------------------

_response_cache = {}

# One cached response can be as large as max_tokens allows, so the cache is
# capped. Without a limit it grows for the life of the process, one full
# response at a time.
MAX_CACHED_RESPONSES = 64


def _cache_response(key, value):
    """Store a result, dropping the oldest once the cache is full."""
    if key not in _response_cache and len(_response_cache) >= MAX_CACHED_RESPONSES:
        _response_cache.pop(next(iter(_response_cache)), None)
    _response_cache[key] = value


# ---------------------------------------------------------------------------
# Cache key computation
# ---------------------------------------------------------------------------

def _compute_cache_key(prompt, model, seed, images=None, instructions=None,
                       temperature=1.0, max_tokens=4096,
                       extended_thinking=False, thinking_budget=4096,
                       max_image_size=1024):
    h = hashlib.sha256()
    h.update(str(seed).encode())
    h.update(prompt.encode())
    h.update(model.encode())
    h.update(str(temperature).encode())
    h.update(str(max_tokens).encode())
    h.update(str(extended_thinking).encode())
    h.update(str(thinking_budget).encode())
    h.update(str(max_image_size).encode())
    if instructions:
        h.update(instructions.encode())
    if images is not None:
        h.update(str(images.shape).encode())
        h.update(images.cpu().numpy().tobytes()[:4096])
    return h.hexdigest()


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def _try_save_history(prompt, model, seed, template, temperature, max_tokens,
                      extended_thinking, thinking_budget, max_image_size,
                      response, thinking, input_tokens, output_tokens,
                      cost, cost_str, duration_ms, error, images):
    try:
        from . import history_manager
        history_manager.save_entry({
            "prompt": prompt,
            "model": model,
            "model_display": _id_to_display.get(model, model),
            "seed": seed,
            "template": template or "None",
            "temperature": temperature,
            "max_tokens": max_tokens,
            "extended_thinking": extended_thinking,
            "thinking_budget": thinking_budget,
            "max_image_size": max_image_size,
            "response": response,
            "thinking": thinking,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "cost_str": cost_str,
            "duration_ms": duration_ms,
            "error": error,
        }, image_tensor=images)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Node class
# ---------------------------------------------------------------------------

class AnthropicClaudeNode(io.ComfyNode):
    """ComfyUI node for calling the Anthropic Claude API with text and image inputs."""

    @classmethod
    def define_schema(cls):
        model_ids = _fetch_models()
        display_names = _build_model_map(model_ids)
        sonnet_models = sorted(
            [d for d in display_names if d.startswith("Sonnet")],
            reverse=True,
        )
        default_model = sonnet_models[0] if sonnet_models else display_names[0]

        return io.Schema(
            node_id="AnthropicClaudeNode",
            display_name="Anthropic Claude",
            category="LLM/Anthropic",
            description=(
                "Calls the Anthropic Claude API with text and optional image inputs. "
                "Features: vision, extended thinking, seed-based caching. "
                "Setup: set CLAUDE_API_KEY env var. Install: pip install anthropic>=0.122.0"
            ),
            inputs=[
                io.String.Input(
                    "prompt",
                    default="",
                    multiline=True,
                    dynamic_prompts=False,
                    tooltip="The text prompt to send to Claude.",
                ),
                io.Combo.Input(
                    "model",
                    options=display_names,
                    default=default_model,
                    tooltip="Claude model to use. Fetched from the Anthropic API at startup; falls back to a built-in list if unavailable.",
                ),
                io.Int.Input(
                    "seed",
                    default=739204185613097,
                    min=0,
                    max=1125899906842624,
                    control_after_generate=True,
                    tooltip="Controls caching. Fixed = reuse cached result (no API call). Randomize = new API call each run.",
                ),
                io.Image.Input(
                    "images",
                    optional=True,
                    tooltip="Optional images for Claude's vision. Accepts batched images. Each is converted to JPEG before sending.",
                ),
                io.Combo.Input(
                    "template",
                    options=_list_all_template_names(),
                    default="None",
                    optional=True,
                    tooltip="Pre-built instructions for optimizing prompts for specific AI models. Overridden when instructions input is connected.",
                ),
                io.String.Input(
                    "instructions",
                    default="",
                    multiline=True,
                    optional=True,
                    dynamic_prompts=False,
                    tooltip="System-level instructions that guide Claude's behavior and response style.",
                ),
                io.Float.Input(
                    "temperature",
                    default=1.0,
                    min=0.0,
                    max=1.0,
                    step=0.05,
                    optional=True,
                    tooltip="Controls randomness. 0.0 = deterministic, 1.0 = most creative. Forced to 1.0 when extended thinking is enabled.",
                ),
                io.Int.Input(
                    "max_tokens",
                    default=4096,
                    min=1,
                    max=128000,
                    step=1,
                    optional=True,
                    tooltip="Maximum number of tokens in Claude's response. Higher = longer responses, more cost.",
                ),
                io.Boolean.Input(
                    "extended_thinking",
                    default=False,
                    optional=True,
                    tooltip="Enable Claude's extended thinking for complex reasoning. Forces temperature to 1.0.",
                ),
                io.Int.Input(
                    "thinking_budget",
                    default=4096,
                    min=1024,
                    max=128000,
                    step=1,
                    optional=True,
                    tooltip="Max tokens for the thinking process. Only used when extended thinking is enabled.",
                ),
                io.Int.Input(
                    "max_image_size",
                    default=1024,
                    min=64,
                    max=1568,
                    step=1,
                    optional=True,
                    tooltip="Max pixel dimension for images. Images are resized to fit. API max is 1568px. Lower = fewer tokens, lower cost.",
                ),
            ],
            outputs=[
                io.String.Output(
                    "response",
                    tooltip="Claude's text response to the prompt.",
                ),
                io.String.Output(
                    "thinking",
                    tooltip="Claude's internal reasoning when extended thinking is enabled. Empty otherwise.",
                ),
            ],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, prompt, model, seed, images=None, template=None,
                           instructions=None, temperature=1.0, max_tokens=4096,
                           extended_thinking=False, thinking_budget=4096,
                           max_image_size=1024):
        instructions = instructions or ""
        if not instructions and template and template != "None":
            instructions = _load_template(template)
        model = _resolve_model(model)
        return _compute_cache_key(
            prompt, model, seed, images, instructions,
            temperature, max_tokens, extended_thinking, thinking_budget,
            max_image_size,
        )

    @classmethod
    def execute(cls, prompt, model, seed,
                images=None, template=None, instructions=None,
                temperature=1.0, max_tokens=4096,
                extended_thinking=False, thinking_budget=4096,
                max_image_size=1024) -> io.NodeOutput:

        instructions = instructions or ""
        if not instructions and template and template != "None":
            instructions = _load_template(template)
            if not instructions.strip():
                err = (
                    f"ERROR: Template '{template}' could not be loaded (file missing, "
                    f"unreadable, or empty). Use the Refresh Templates button and re-select."
                )
                return io.NodeOutput(err, "", ui={"text": [err], "usage": ["N/A"], "error": [err]})
        model = _resolve_model(model)

        # -- Validate prerequisites --
        if not ANTHROPIC_AVAILABLE:
            err = "ERROR: 'anthropic' package not installed. Run: pip install anthropic"
            return io.NodeOutput(err, "", ui={"text": [err], "usage": ["N/A"], "error": [err]})

        api_key = _get_api_key()
        if not api_key:
            err = "ERROR: CLAUDE_API_KEY environment variable not set."
            return io.NodeOutput(err, "", ui={"text": [err], "usage": ["N/A"], "error": [err]})

        if not prompt.strip():
            err = "ERROR: Prompt is empty."
            return io.NodeOutput(err, "", ui={"text": [err], "usage": ["N/A"], "error": [err]})

        # -- Check internal cache --
        cache_key = _compute_cache_key(
            prompt, model, seed, images, instructions,
            temperature, max_tokens, extended_thinking, thinking_budget,
            max_image_size,
        )
        if cache_key in _response_cache:
            cached = _response_cache[cache_key]
            return io.NodeOutput(cached[0], cached[1], ui={
                "text": [cached[0]],
                "thinking": [cached[1]],
                "usage": [cached[2]],
                "cost": [cached[3]],
                "model_used": [cached[4]],
                "cached": ["true"],
                "error": [""],
            })

        # -- Build content blocks (images first, then text) --
        content = []

        if images is not None:
            b64_images = _tensor_to_base64_images(images, max_dim=max_image_size)
            for idx, b64_str in enumerate(b64_images):
                if len(b64_images) > 1:
                    content.append({"type": "text", "text": f"Image {idx + 1}:"})
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": b64_str,
                    },
                })

        content.append({"type": "text", "text": prompt})

        # -- Build API kwargs --
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }

        if instructions and instructions.strip():
            kwargs["system"] = instructions

        if extended_thinking:
            kwargs["temperature"] = 1.0
            if _uses_adaptive_thinking(model):
                kwargs["thinking"] = {"type": "adaptive"}
                kwargs["extra_body"] = {"output_config": {"effort": _budget_to_effort(thinking_budget)}}
            else:
                kwargs["max_tokens"] = max_tokens + thinking_budget
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                }
        else:
            kwargs["temperature"] = temperature

        # -- Make API call --
        t_start = time.time()
        api_error = None
        message = None
        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(**kwargs)
        except anthropic.AuthenticationError:
            api_error = "ERROR: Invalid API key. Check your CLAUDE_API_KEY."
        except anthropic.RateLimitError:
            api_error = "ERROR: Rate limited by Anthropic API. Wait and retry."
        except anthropic.BadRequestError as e:
            # Retry with adaptive thinking if the model rejected manual thinking.
            # This test reads the UNTOUCHED exception text on purpose: the
            # marker the API sends back is what identifies the case, and
            # cleaning the text first could remove the very words being
            # looked for. Only the message shown to the user is cleaned.
            if extended_thinking and "thinking.type" in str(e) and "adaptive" in str(e):
                kwargs.pop("max_tokens", None)
                kwargs["max_tokens"] = max_tokens
                kwargs["thinking"] = {"type": "adaptive"}
                kwargs["extra_body"] = {"output_config": {"effort": _budget_to_effort(thinking_budget)}}
                try:
                    message = client.messages.create(**kwargs)
                except Exception as retry_err:
                    api_error = "ERROR: Anthropic API error: " + _safe_error_text(retry_err)
            else:
                api_error = "ERROR: Anthropic API error: " + _safe_error_text(e)
        except anthropic.APIError as e:
            api_error = "ERROR: Anthropic API error: " + _safe_error_text(e)
        except Exception as e:
            api_error = "ERROR: " + _safe_error_text(e)
        duration_ms = int((time.time() - t_start) * 1000)

        if api_error:
            _try_save_history(
                prompt, model, seed, template, temperature, max_tokens,
                extended_thinking, thinking_budget, max_image_size,
                "", "", 0, 0, None, "", duration_ms, api_error, images,
            )
            return io.NodeOutput(api_error, "", ui={"text": [api_error], "usage": ["N/A"], "error": [api_error]})

        # -- Parse response --
        response_text = ""
        thinking_text = ""

        for block in message.content:
            if block.type == "text":
                response_text += block.text
            elif block.type == "thinking":
                thinking_text += block.thinking

        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens
        usage_str = f"In: {input_tokens} | Out: {output_tokens} tokens"
        cost = _calculate_cost(model, input_tokens, output_tokens)
        cost_str = _format_cost(cost, exact=_price_is_exact(model))

        # -- Cache result --
        _cache_response(cache_key, (response_text, thinking_text, usage_str, cost_str, model))

        # -- Save history --
        _try_save_history(
            prompt, model, seed, template, temperature, max_tokens,
            extended_thinking, thinking_budget, max_image_size,
            response_text, thinking_text, input_tokens, output_tokens,
            cost, cost_str, duration_ms, None, images,
        )

        # -- Return --
        return io.NodeOutput(response_text, thinking_text, ui={
            "text": [response_text],
            "thinking": [thinking_text],
            "usage": [usage_str],
            "cost": [cost_str],
            "model_used": [model],
            "cached": ["false"],
            "error": [""],
        })


# ---------------------------------------------------------------------------
# Extension registration
# ---------------------------------------------------------------------------

class AnthropicClaudeExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            AnthropicClaudeNode,
        ]

    @override
    async def on_load(self) -> None:
        # Node Replacement API - register old-to-new node ID mappings here
        # api = ComfyAPI()
        # await api.node_replacement.register(io.NodeReplace(
        #     new_node_id="AnthropicClaudeNode",
        #     old_node_id="OldNodeName",
        # ))
        pass


async def comfy_entrypoint() -> AnthropicClaudeExtension:
    return AnthropicClaudeExtension()
