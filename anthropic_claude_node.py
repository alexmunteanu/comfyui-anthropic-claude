"""
Anthropic Claude Node for ComfyUI (V3 API)
Provides a node that calls the Anthropic Claude API with text and image inputs.
© 2026 Created with ♥ by Alex Munteanu | alexmunteanu.com
"""

import hashlib
import base64
import re
import threading
import time
import unicodedata
from io import BytesIO
from pathlib import Path
from typing_extensions import override

import numpy as np
from PIL import Image

import folder_paths
from comfy_api.latest import ComfyExtension, io

from . import safe_fs
from .template_registry import (
    BUILTIN_TEMPLATES,
    LEGACY_TEMPLATE_ALIASES,
    RETIRED_TEMPLATES,
    resolve_builtin_template_name,
)

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")


_CREDENTIALS_RE = re.compile(r"//[^/\s:@]+:[^/\s@]+@")


_SEG_INNER = r"[^\\/\r\n\"']"
_SEG_LAST = r"[^\s\\/\r\n\"']"
_TAIL = "(?:" + _SEG_LAST + r"*(?: " + _SEG_LAST + r"+)*?\.[A-Za-z0-9]{1,8}|" + _SEG_LAST + "*)"


_WINPATH_RE = re.compile(
    r"(?<![A-Za-z])[A-Za-z]:[\\/](?:" + _SEG_INNER + r"*[\\/])*" + _TAIL)
_UNCPATH_RE = re.compile(r"\\\\(?:" + _SEG_INNER + r"*[\\/])*" + _TAIL)
_POSIXPATH_RE = re.compile(
    r"/(?:home|Users|root|var|tmp|opt|etc|mnt|srv)/(?:" + _SEG_INNER + r"*/)*" + _TAIL)

MAX_ERROR_CHARS = 400


def _safe_error_text(exc, secret=None):
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
    if secret:
        text = text.replace(secret, "<credential>")
    text = _SECRET_RE.sub("sk-***", text)
    text = _CREDENTIALS_RE.sub("//***:***@", text)
    text = _WINPATH_RE.sub("<path>", text)
    text = _UNCPATH_RE.sub("<path>", text)
    text = _POSIXPATH_RE.sub("<path>", text)
    if len(text) > MAX_ERROR_CHARS:
        text = text[:MAX_ERROR_CHARS] + "..."
    return text or type(exc).__name__


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


    return text.replace("\r\n", "\n").replace("\r", "\n")


def _load_template(name):
    if not isinstance(name, str) or not name or name == "None":
        return ""
    resolved_name = resolve_builtin_template_name(name)
    if resolved_name in BUILTIN_TEMPLATES:
        return _read_template_file(
            _get_templates_dir(),
            BUILTIN_TEMPLATES[resolved_name],
        )
    return _read_template_file(_get_user_templates_dir(), name + ".md")


def _effective_connected_instructions(instructions):
    """Treat whitespace-only connected text as absent without trimming content."""
    text = instructions or ""
    return text if text.strip() else ""


MODEL_PRICING_EXACT = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-fable-5-1": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-5-20251101": (5.00, 25.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
}


MODEL_PRICING_PRESERVED_EXACT = {
    "claude-fable-5": (10.00, 50.00),
    "claude-mythos-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-4-1": (15.00, 75.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-3-opus": (15.00, 75.00),
    "claude-3-7-sonnet": (3.00, 15.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-haiku": (0.25, 1.25),
}


MODEL_PRICING_FAMILY = [
    ("fable", 10.00, 50.00),
    ("mythos", 10.00, 50.00),
    ("opus", 5.00, 25.00),
    ("sonnet", 2.00, 10.00),
    ("haiku", 1.00, 5.00),
]

_MODEL_ID_SUFFIX = re.compile(r"(-\d{8}|-latest|-0)$")


def _normalize_model_id(model):
    """Lowercase and strip one trailing snapshot, latest, or zero suffix."""
    if not isinstance(model, str):
        return ""
    return _MODEL_ID_SUFFIX.sub("", model.strip().lower(), count=1)


def _lookup_price(model, input_tokens=0):
    """Return (input_price, output_price, is_exact) or None if unpriced."""
    if not isinstance(model, str):
        return None
    raw_key = model.strip().lower()
    if not raw_key:
        return None

    if raw_key in MODEL_PRICING_EXACT:
        input_price, output_price = MODEL_PRICING_EXACT[raw_key]
        if raw_key == "claude-haiku-5-5" and input_tokens > 100000:
            input_price, output_price = 0.50, 2.50
        return input_price, output_price, True

    key = _normalize_model_id(raw_key)
    if key in MODEL_PRICING_PRESERVED_EXACT:
        input_price, output_price = MODEL_PRICING_PRESERVED_EXACT[key]
        return input_price, output_price, True
    for pattern, input_price, output_price in MODEL_PRICING_FAMILY:
        if pattern in key:
            return input_price, output_price, False
    return None


def _calculate_cost(model, input_tokens, output_tokens):
    """Calculate USD cost based on model and token counts."""
    priced = _lookup_price(model, input_tokens)
    if priced is None:
        return None
    input_price, output_price, _is_exact = priced
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def _price_is_exact(model):
    """Return whether the selected model has a verified exact rate."""
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


FALLBACK_MODELS = [
    "claude-haiku-5-5",
    "claude-sonnet-5-5",
    "claude-opus-5-5",
    "claude-fable-5-1",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-opus-4-5-20251101",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
]

MODEL_FETCH_DEADLINE_SECONDS = 3.0
MAX_MODEL_PAGES = 20
MAX_MODELS = MAX_MODEL_PAGES * 1000
MAX_MODEL_ID_CHARS = 256
MAX_MODEL_DISPLAY_NAME_CHARS = 256
MAX_STARTUP_WARNINGS = 10
_BIDI_CONTROL_CODEPOINTS = frozenset(
    [0x061C, 0x200E, 0x200F]
    + list(range(0x202A, 0x202F))
    + list(range(0x2066, 0x206A))
)

_cached_models = None
_models_fetch_time = 0
_startup_warnings = []
_api_error = {"ok": True, "error": "", "error_type": ""}


def _fallback_model_records():
    return [{"id": model_id, "display_name": None} for model_id in FALLBACK_MODELS]


def _is_safe_model_id(value):
    if not isinstance(value, str) or not value or len(value) > MAX_MODEL_ID_CHARS:
        return False
    return value.isascii() and value.isprintable() and not any(
        character.isspace() for character in value
    )


def _is_safe_model_display_name(value):
    if value is None:
        return True
    if not isinstance(value, str) or len(value) > MAX_MODEL_DISPLAY_NAME_CHARS:
        return False
    if value and not value.isprintable():
        return False
    return not any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        or ord(character) in _BIDI_CONTROL_CODEPOINTS
        for character in value
    )


def _add_startup_warning(text):
    if text in _startup_warnings or len(_startup_warnings) >= MAX_STARTUP_WARNINGS:
        return
    _startup_warnings.append(text)


ANTHROPIC_API_BASE_URL = "https://api.anthropic.com"
MESSAGE_REQUEST_TIMEOUT_SECONDS = 600.0
MAX_API_KEY_CHARS = 512
MAX_CREDENTIAL_FILE_BYTES = MAX_API_KEY_CHARS * 4 + 1
_CREDENTIAL_ROOT = Path(__file__).parent
_CREDENTIAL_DIR_NAME = ".anthropic_claude"
_CREDENTIAL_FILE_NAME = "api_key"

_credential_state_lock = threading.RLock()
_credential_replacement_lock = threading.Lock()
_active_api_key = ""
_credential_generation = 0
_credential_status = "missing"
_credential_error_type = ""
_bootstrap_attempted = False


class CredentialProbeError(Exception):
    """A categorized provider failure with fixed, credential-free text."""

    def __init__(self, status, error_type, message):
        super().__init__(message)
        self.status = status
        self.error_type = error_type
        self.safe_message = message


def _valid_credential_token(value):
    if not isinstance(value, str) or not value or len(value) > MAX_API_KEY_CHARS:
        return False
    return value.isprintable() and not any(character.isspace() for character in value)


def _read_stored_api_key():
    """Read and validate the fixed package credential through safe_fs only."""
    try:
        directory = safe_fs.descend(_CREDENTIAL_ROOT, [_CREDENTIAL_DIR_NAME])
        if directory is None:
            return {"status": "missing", "key": None}
        path = safe_fs.descend(
            _CREDENTIAL_ROOT,
            [_CREDENTIAL_DIR_NAME, _CREDENTIAL_FILE_NAME],
        )
        if path is None:
            return {"status": "missing", "key": None}
        raw = safe_fs.read_bytes_verified(path, MAX_CREDENTIAL_FILE_BYTES)
    except Exception:
        return {"status": "storage_error", "key": None}
    if raw is None:
        return {"status": "storage_error", "key": None}
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    try:
        key = raw.decode("utf-8")
    except (AttributeError, UnicodeDecodeError):
        return {"status": "invalid", "key": None}
    if not _valid_credential_token(key):
        return {"status": "invalid", "key": None}
    return {"status": "valid", "key": key}


def _credential_public_status():
    """Return package-wide credential state without key-derived data."""
    with _credential_state_lock:
        status = "valid" if _active_api_key else _credential_status
        return {
            "ok": bool(_active_api_key),
            "status": status,
            "error_type": _credential_error_type,
        }


def _credential_needs_bootstrap():
    """Return whether the saved credential still needs its first validation."""
    with _credential_state_lock:
        return not _active_api_key and not _bootstrap_attempted


def _credential_snapshot():
    """Return the active backend credential and generation."""
    _bootstrap_stored_credential()
    with _credential_state_lock:
        return _active_api_key, _credential_generation


def _set_inactive_credential_status(status, error_type):
    global _credential_status, _credential_error_type
    with _credential_state_lock:
        if _active_api_key:
            return
        _credential_status = status
        _credential_error_type = error_type


def _failure_result(status, error_type, message):
    active = _credential_public_status()
    return {
        "ok": False,
        "status": status,
        "active_status": active["status"],
        "error": {
            "error_type": error_type,
            "error": message,
        },
    }


def _activate_validated_credential(key, records):
    global _active_api_key, _credential_generation
    global _credential_status, _credential_error_type
    global _cached_models, _models_fetch_time
    with _credential_state_lock:
        _active_api_key = key
        _credential_generation += 1
        _credential_status = "valid"
        _credential_error_type = ""
        _cached_models = list(records)
        _models_fetch_time = time.time()
        _response_cache.clear()
        _api_error.update(ok=True, error="", error_type="")
        display_names = _build_model_map(_cached_models)
        return _credential_generation, display_names


def _replace_credential(candidate, persist):
    if not _valid_credential_token(candidate):
        _set_inactive_credential_status("invalid", "invalid_format")
        return _failure_result(
            "invalid",
            "invalid_format",
            "Enter one API key without spaces.",
        )

    if not _credential_replacement_lock.acquire(blocking=False):
        return _failure_result(
            "unavailable",
            "busy",
            "A key check is already running.",
        )
    try:
        try:
            records = _probe_model_catalog(candidate)
        except CredentialProbeError as exc:
            _set_inactive_credential_status(exc.status, exc.error_type)
            return _failure_result(exc.status, exc.error_type, exc.safe_message)

        if persist:
            try:
                directory = safe_fs.ensure_dir_chain(
                    _CREDENTIAL_ROOT,
                    [_CREDENTIAL_DIR_NAME],
                )
            except Exception:
                directory = None
            if directory is None:
                _set_inactive_credential_status("storage_error", "storage_error")
                return _failure_result(
                    "storage_error",
                    "storage_error",
                    "The API key could not be saved.",
                )
            path = directory / _CREDENTIAL_FILE_NAME
            try:
                saved = safe_fs.write_bytes_atomic(
                    path,
                    candidate.encode("utf-8"),
                )
            except Exception:
                saved = False
            if not saved:
                _set_inactive_credential_status("storage_error", "storage_error")
                return _failure_result(
                    "storage_error",
                    "storage_error",
                    "The API key could not be saved.",
                )

        _generation, display_names = _activate_validated_credential(
            candidate,
            records,
        )
        return {
            "ok": True,
            "status": "valid",
            "models": display_names,
        }
    finally:
        _credential_replacement_lock.release()


def _save_validated_api_key(candidate):
    """Validate, atomically persist, then publish one package-wide key."""
    return _replace_credential(candidate, persist=True)


def _bootstrap_stored_credential(force=False):
    """Validate the saved key before use, with explicit retry recovery."""
    global _bootstrap_attempted, _credential_status, _credential_error_type
    with _credential_state_lock:
        if _active_api_key:
            return _credential_public_status()
        if _bootstrap_attempted and not force:
            return _credential_public_status()
        _bootstrap_attempted = True
        _credential_status = "checking"
        _credential_error_type = ""

    stored = _read_stored_api_key()
    if stored["status"] != "valid":
        _set_inactive_credential_status(
            stored["status"],
            "" if stored["status"] == "missing" else stored["status"],
        )
        return _credential_public_status()

    result = _replace_credential(stored["key"], persist=False)
    if result.get("ok"):
        return _credential_public_status()
    return _credential_public_status()


_display_to_id = {}
_id_to_display = {}


_TERMINAL_MODEL_SNAPSHOT_RE = re.compile(r"-\d{8}$")


def _strip_terminal_model_snapshot(model_id):
    return _TERMINAL_MODEL_SNAPSHOT_RE.sub("", model_id)


def _make_display_name(model_id, api_display_name=None):
    """Return the API label, or derive a readable family/version label."""
    if isinstance(api_display_name, str) and api_display_name.strip():
        return api_display_name.strip()
    if not isinstance(model_id, str):
        return str(model_id)

    name = _strip_terminal_model_snapshot(model_id.strip().lower())
    if name.startswith("claude-"):
        name = name[7:]

    families = ("opus", "sonnet", "haiku", "fable", "mythos")
    for family in families:
        direct = re.match(rf"^{family}-(\d+)(?:-(\d+))?", name)
        if direct:
            version = direct.group(1)
            if direct.group(2):
                version += "." + direct.group(2)
            return f"{family.capitalize()} {version}"

        legacy = re.match(rf"^(\d+)(?:-(\d+))?-{family}(?:-|$)", name)
        if legacy:
            version = legacy.group(1)
            if legacy.group(2):
                version += "." + legacy.group(2)
            return f"{family.capitalize()} {version}"

    return model_id


def _build_model_map(model_records):
    """Build bidirectional display-name/model-ID mappings in server order."""
    global _display_to_id, _id_to_display
    _display_to_id = {}
    _id_to_display = {}
    display_names = []

    for record in model_records:
        if isinstance(record, str):
            model_id = record
            api_display_name = None
        elif isinstance(record, dict):
            model_id = record.get("id")
            api_display_name = record.get("display_name")
        else:
            continue
        if not isinstance(model_id, str) or not model_id:
            continue

        display_name = _make_display_name(model_id, api_display_name)
        if display_name in _display_to_id:
            display_name = model_id
            suffix = 2
            while display_name in _display_to_id:
                display_name = f"{model_id} ({suffix})"
                suffix += 1

        _display_to_id[display_name] = model_id
        _id_to_display[model_id] = display_name
        display_names.append(display_name)

    return display_names


def _model_version(model_id, family):
    if not isinstance(model_id, str):
        return None
    name = _strip_terminal_model_snapshot(model_id.strip().lower())
    direct = re.match(rf"^claude-{family}-(\d+)(?:-(\d+))?", name)
    if direct:
        return int(direct.group(1)), int(direct.group(2) or 0)
    legacy = re.match(rf"^claude-(\d+)(?:-(\d+))?-{family}(?:-|$)", name)
    if legacy:
        return int(legacy.group(1)), int(legacy.group(2) or 0)
    return None


def _select_default_model(model_ids):
    """Select the numerically latest Sonnet ID, preserving server-order ties."""
    candidates = []
    for index, item in enumerate(model_ids):
        model_id = item.get("id") if isinstance(item, dict) else item
        version = _model_version(model_id, "sonnet")
        if version is not None:
            candidates.append((version, -index, model_id))
    if candidates:
        return max(candidates)[2]
    for item in model_ids:
        model_id = item.get("id") if isinstance(item, dict) else item
        if isinstance(model_id, str) and model_id:
            return model_id
    return FALLBACK_MODELS[0]


def _resolve_model(display_or_id):
    """Resolve a display name or model ID to the actual API model ID."""
    if display_or_id in _display_to_id:
        return _display_to_id[display_or_id]
    return display_or_id


def _is_anthropic_exception(exc, name):
    error_type = getattr(anthropic, name, None)
    return isinstance(error_type, type) and isinstance(exc, error_type)


def _categorized_probe_error(exc):
    status_code = getattr(exc, "status_code", None)
    if _is_anthropic_exception(exc, "AuthenticationError") or status_code == 401:
        return CredentialProbeError(
            "invalid",
            "auth_error",
            "The API key was not accepted.",
        )
    if _is_anthropic_exception(exc, "PermissionDeniedError") or status_code == 403:
        return CredentialProbeError(
            "invalid",
            "permission_error",
            "The API key cannot list Anthropic models.",
        )
    if (
        _is_anthropic_exception(exc, "RateLimitError")
        or _is_anthropic_exception(exc, "APIConnectionError")
        or _is_anthropic_exception(exc, "APITimeoutError")
        or status_code == 429
        or (isinstance(status_code, int) and status_code >= 500)
    ):
        return CredentialProbeError(
            "unavailable",
            "provider_unavailable",
            "Anthropic is temporarily unavailable.",
        )
    return CredentialProbeError(
        "unavailable",
        "provider_unavailable",
        "Anthropic is temporarily unavailable.",
    )


def _pin_anthropic_request_auth(request, api_key):
    """Put exactly one saved credential on an outgoing Anthropic request."""
    request.headers.pop("Authorization", None)
    request.headers.pop("X-Api-Key", None)
    request.headers["X-Api-Key"] = api_key


def _anthropic_client(api_key, *, timeout):
    """Build a client whose credential and endpoint cannot come from ambient config."""
    def pin_request_auth(request):
        _pin_anthropic_request_auth(request, api_key)

    headers = {"X-Api-Key": api_key}
    omit = getattr(anthropic, "omit", None)
    if omit is not None:
        headers["Authorization"] = omit
    http_client = anthropic.DefaultHttpxClient(
        timeout=timeout,
        event_hooks={"request": [pin_request_auth]},
    )
    return anthropic.Anthropic(
        api_key=api_key,
        base_url=ANTHROPIC_API_BASE_URL,
        timeout=timeout,
        max_retries=0,
        default_headers=headers,
        http_client=http_client,
    )


def _probe_model_catalog(candidate):
    """Validate a key through the bounded official Models API only."""
    if not ANTHROPIC_AVAILABLE:
        raise CredentialProbeError(
            "unavailable",
            "missing_package",
            "The Anthropic package is not installed.",
        )

    deadline = time.monotonic() + MODEL_FETCH_DEADLINE_SECONDS
    try:
        client = _anthropic_client(
            candidate,
            timeout=MODEL_FETCH_DEADLINE_SECONDS,
        )
        records = []
        after_id = None
        seen_cursors = set()
        seen_model_ids = set()

        for _page_index in range(MAX_MODEL_PAGES):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("model catalogue deadline exceeded")
            request = {"limit": 1000, "timeout": remaining}
            if after_id is not None:
                request["after_id"] = after_id
            response = client.models.list(**request)
            if time.monotonic() >= deadline:
                raise TimeoutError("model catalogue deadline exceeded")

            page_data = getattr(response, "data", None)
            if not isinstance(page_data, (list, tuple)):
                raise ValueError("model catalogue page has invalid data")
            if len(page_data) > 1000:
                raise ValueError("model catalogue page exceeds item limit")

            for item in page_data:
                if isinstance(item, dict):
                    model_id = item.get("id")
                    display_name = item.get("display_name")
                else:
                    model_id = getattr(item, "id", None)
                    display_name = getattr(item, "display_name", None)
                if not _is_safe_model_id(model_id):
                    raise ValueError("model catalogue entry has invalid id")
                if not _is_safe_model_display_name(display_name):
                    raise ValueError("model catalogue entry has invalid display name")
                if model_id in seen_model_ids:
                    raise ValueError("model catalogue contains duplicate ids")
                if len(records) >= MAX_MODELS:
                    raise ValueError("model catalogue exceeds item limit")
                seen_model_ids.add(model_id)
                records.append({
                    "id": model_id,
                    "display_name": display_name,
                })

            if not bool(getattr(response, "has_more", False)):
                break
            cursor = getattr(response, "last_id", None)
            if not _is_safe_model_id(cursor) or cursor in seen_cursors:
                raise ValueError("model catalogue cursor did not advance")
            seen_cursors.add(cursor)
            after_id = cursor
        else:
            raise ValueError("model catalogue exceeded page limit")

        if not records:
            raise ValueError("model catalogue is empty")
        return records
    except CredentialProbeError:
        raise
    except (TimeoutError, ValueError) as exc:
        raise CredentialProbeError(
            "unavailable",
            "catalog_error",
            "The Anthropic model catalogue was unavailable.",
        ) from exc
    except Exception as exc:
        raise _categorized_probe_error(exc) from None


def _fetch_models():
    """Fetch models with the active validated credential or a safe fallback."""
    global _cached_models, _models_fetch_time, _credential_error_type

    fallback = _cached_models or _fallback_model_records()
    api_key, _generation = _credential_snapshot()
    if not api_key:
        public = _credential_public_status()
        error_type = public["error_type"] or "missing_key"
        _api_error.update(
            ok=False,
            error="Add and validate an Anthropic API key on the node.",
            error_type=error_type,
        )
        return fallback

    if _cached_models and (time.time() - _models_fetch_time < 3600):
        return _cached_models

    try:
        records = _probe_model_catalog(api_key)
    except CredentialProbeError as exc:
        with _credential_state_lock:
            _credential_error_type = exc.error_type
        _api_error.update(
            ok=False,
            error=exc.safe_message,
            error_type=exc.error_type,
        )
        return fallback

    with _credential_state_lock:
        _cached_models = records
        _models_fetch_time = time.time()
        _credential_error_type = ""
        _api_error.update(ok=True, error="", error_type="")
    return records


def _refresh_models():
    """Retry saved-key bootstrap, then refresh the active model catalogue."""
    global _models_fetch_time
    api_key, _generation = _credential_snapshot()
    if not api_key:
        _bootstrap_stored_credential(force=True)
    _models_fetch_time = 0
    model_records = _fetch_models()
    if _api_error["ok"]:
        _startup_warnings.clear()
    return _build_model_map(model_records)


KNOWN_OUTPUT_LIMITS = {
    model_id: (64000 if "-4-5-" in model_id else 128000)
    for model_id in FALLBACK_MODELS
}


def _uses_adaptive_thinking(model_id):
    """Return whether a model uses the adaptive thinking request schema."""
    if not isinstance(model_id, str):
        return False
    lowered = model_id.lower()
    if "fable" in lowered or "mythos" in lowered:
        return True
    for family in ("opus", "sonnet", "haiku"):
        version = _model_version(lowered, family)
        if version is not None:
            major, minor = version
            return major >= 5 or (major == 4 and minor >= 6)
    return False


def _restricts_temperature(model_id):
    """Return whether non-default sampling parameters must be omitted."""
    if not isinstance(model_id, str):
        return False
    lowered = model_id.lower()
    if "fable" in lowered or "mythos" in lowered:
        return True
    for family in ("opus", "sonnet", "haiku"):
        version = _model_version(lowered, family)
        if version is not None:
            major, minor = version
            return major >= 5 or (major == 4 and minor >= 7)
    return False


def _budget_to_effort(thinking_budget):
    """Map the legacy budget control to adaptive effort."""
    if thinking_budget <= 8192:
        return "low"
    if thinking_budget <= 32768:
        return "medium"
    return "high"


def _validate_request_limits(model, max_tokens, extended_thinking,
                             thinking_budget):
    """Return a user-facing validation error, or None for a valid request."""
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
        return "Maximum response tokens must be a positive integer."

    adaptive = _uses_adaptive_thinking(model)
    total_tokens = max_tokens
    if extended_thinking:
        if (
            not isinstance(thinking_budget, int)
            or isinstance(thinking_budget, bool)
            or thinking_budget < 1
        ):
            return "Thinking budget must be a positive integer."
        if not adaptive:
            total_tokens = max_tokens + thinking_budget
            if thinking_budget >= total_tokens:
                return "Thinking budget must be lower than total output tokens."

    limit = KNOWN_OUTPUT_LIMITS.get(str(model).strip().lower())
    if limit is not None and total_tokens > limit:
        return (
            f"This model supports at most {limit} total output tokens; "
            f"the request needs {total_tokens}."
        )
    return None


def _build_request_kwargs(model, content, instructions, temperature,
                          max_tokens, extended_thinking, thinking_budget):
    """Build the pure Messages API request dictionary."""
    limit_error = _validate_request_limits(
        model,
        max_tokens,
        extended_thinking,
        thinking_budget,
    )
    if limit_error is not None:
        raise ValueError(limit_error)

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if instructions and instructions.strip():
        kwargs["system"] = instructions

    if extended_thinking:
        if _uses_adaptive_thinking(model):
            kwargs["thinking"] = {
                "type": "adaptive",
                "display": "summarized",
            }
            kwargs["extra_body"] = {
                "output_config": {
                    "effort": _budget_to_effort(thinking_budget),
                },
            }
        else:
            kwargs["max_tokens"] = max_tokens + thinking_budget
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }
    elif not _restricts_temperature(model):
        kwargs["temperature"] = temperature

    return kwargs


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


_response_cache = {}


MAX_CACHED_RESPONSES = 64


def _get_cached_response(key):
    with _credential_state_lock:
        return _response_cache.get(key)


def _cache_response(key, value):
    """Store a result, dropping the oldest once the cache is full."""
    with _credential_state_lock:
        if key not in _response_cache and len(_response_cache) >= MAX_CACHED_RESPONSES:
            oldest = next(iter(_response_cache), None)
            if oldest is not None:
                _response_cache.pop(oldest, None)
        _response_cache[key] = value


def _compute_cache_key(prompt, model, seed, images=None, instructions=None,
                       temperature=1.0, max_tokens=4096,
                       extended_thinking=False, thinking_budget=4096,
                       max_image_size=1024, credential_generation=0):
    h = hashlib.sha256()

    def add_field(value):
        if value is None:
            payload = b"n"
        elif isinstance(value, bool):
            payload = b"b1" if value else b"b0"
        elif isinstance(value, int):
            payload = b"i" + str(value).encode("ascii")
        elif isinstance(value, float):
            payload = b"f" + value.hex().encode("ascii")
        elif isinstance(value, str):
            payload = b"s" + value.encode("utf-8")
        elif isinstance(value, bytes):
            payload = b"y" + value
        else:
            payload = b"r" + repr(value).encode("utf-8")
        h.update(len(payload).to_bytes(8, "big"))
        h.update(payload)

    for value in (
        credential_generation,
        seed,
        prompt,
        model,
        temperature,
        max_tokens,
        extended_thinking,
        thinking_budget,
        max_image_size,
        instructions,
    ):
        add_field(value)
    if images is not None:
        add_field(tuple(int(dimension) for dimension in images.shape))
        add_field(images.cpu().numpy().tobytes()[:4096])
    return h.hexdigest()


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


class AnthropicClaudeNode(io.ComfyNode):
    """ComfyUI node for calling the Anthropic Claude API with text and image inputs."""

    @classmethod
    def define_schema(cls):
        model_records = _fetch_models()
        display_names = _build_model_map(model_records)
        default_model_id = _select_default_model(model_records)
        default_model = _id_to_display.get(
            default_model_id,
            display_names[0] if display_names else default_model_id,
        )

        return io.Schema(
            node_id="AnthropicClaudeNode",
            display_name="Anthropic Claude",
            category="LLM/Anthropic",
            description=(
                "Calls the Anthropic Claude API with text and optional image inputs. "
                "Features: vision, extended thinking, seed-based caching. "
                "Add and validate the API key on the node. "
                "Install: pip install anthropic>=0.122.0"
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
                    tooltip="Show summarized thinking when supported. Some current models still think adaptively when this is off, but keep it hidden.",
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
        instructions = _effective_connected_instructions(instructions)
        if not instructions and template and template != "None":
            instructions = _load_template(template)
        model = _resolve_model(model)
        _api_key, credential_generation = _credential_snapshot()
        return _compute_cache_key(
            prompt, model, seed, images, instructions,
            temperature, max_tokens, extended_thinking, thinking_budget,
            max_image_size, credential_generation,
        )

    @classmethod
    def execute(cls, prompt, model, seed,
                images=None, template=None, instructions=None,
                temperature=1.0, max_tokens=4096,
                extended_thinking=False, thinking_budget=4096,
                max_image_size=1024) -> io.NodeOutput:

        instructions = _effective_connected_instructions(instructions)
        if not instructions and template and template != "None":
            resolved_template = resolve_builtin_template_name(template)
            if resolved_template in RETIRED_TEMPLATES:
                err = (
                    f"ERROR: Template '{resolved_template}' is retired. "
                    f"{RETIRED_TEMPLATES[resolved_template]}"
                )
                return io.NodeOutput(
                    err,
                    "",
                    ui={"text": [err], "usage": ["N/A"], "error": [err]},
                )
            instructions = _load_template(resolved_template)
            if not instructions.strip():
                err = (
                    f"ERROR: Template '{template}' could not be loaded (file missing, "
                    f"unreadable, or empty). Use the Refresh Templates button and re-select."
                )
                return io.NodeOutput(
                    err,
                    "",
                    ui={"text": [err], "usage": ["N/A"], "error": [err]},
                )
        model = _resolve_model(model)


        if not ANTHROPIC_AVAILABLE:
            err = "ERROR: 'anthropic' package not installed. Run: pip install anthropic"
            return io.NodeOutput(err, "", ui={"text": [err], "usage": ["N/A"], "error": [err]})

        api_key, credential_generation = _credential_snapshot()
        if not api_key:
            err = "ERROR: Add and validate an Anthropic API key on the node."
            return io.NodeOutput(err, "", ui={"text": [err], "usage": ["N/A"], "error": [err]})

        if not prompt.strip():
            err = "ERROR: Prompt is empty."
            return io.NodeOutput(err, "", ui={"text": [err], "usage": ["N/A"], "error": [err]})

        limit_error = _validate_request_limits(
            model,
            max_tokens,
            extended_thinking,
            thinking_budget,
        )
        if limit_error is not None:
            err = "ERROR: " + limit_error
            return io.NodeOutput(
                err,
                "",
                ui={"text": [err], "usage": ["N/A"], "error": [err]},
            )


        cache_key = _compute_cache_key(
            prompt, model, seed, images, instructions,
            temperature, max_tokens, extended_thinking, thinking_budget,
            max_image_size, credential_generation,
        )
        cached = _get_cached_response(cache_key)
        if cached is not None:
            return io.NodeOutput(cached[0], cached[1], ui={
                "text": [cached[0]],
                "thinking": [cached[1]],
                "usage": [cached[2]],
                "cost": [cached[3]],
                "model_used": [cached[4]],
                "cached": ["true"],
                "error": [""],
            })


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


        kwargs = _build_request_kwargs(
            model,
            content,
            instructions,
            temperature,
            max_tokens,
            extended_thinking,
            thinking_budget,
        )


        t_start = time.time()
        api_error = None
        message = None
        try:
            client = _anthropic_client(
                api_key,
                timeout=MESSAGE_REQUEST_TIMEOUT_SECONDS,
            )
            message = client.messages.create(**kwargs)
        except anthropic.AuthenticationError:
            api_error = "ERROR: The saved Anthropic API key is invalid."
        except anthropic.RateLimitError:
            api_error = "ERROR: Rate limited by Anthropic API. Wait and retry."
        except anthropic.BadRequestError as exc:
            api_error = "ERROR: Anthropic API error: " + _safe_error_text(exc, api_key)
        except anthropic.APIError as exc:
            api_error = "ERROR: Anthropic API error: " + _safe_error_text(exc, api_key)
        except Exception as exc:
            api_error = "ERROR: " + _safe_error_text(exc, api_key)
        duration_ms = int((time.time() - t_start) * 1000)

        if api_error:
            _try_save_history(
                prompt, model, seed, template, temperature, max_tokens,
                extended_thinking, thinking_budget, max_image_size,
                "", "", 0, 0, None, "", duration_ms, api_error, images,
            )
            return io.NodeOutput(
                api_error,
                "",
                ui={"text": [api_error], "usage": ["N/A"], "error": [api_error]},
            )


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


        _cache_response(
            cache_key,
            (response_text, thinking_text, usage_str, cost_str, model),
        )

        _try_save_history(
            prompt, model, seed, template, temperature, max_tokens,
            extended_thinking, thinking_budget, max_image_size,
            response_text, thinking_text, input_tokens, output_tokens,
            cost, cost_str, duration_ms, None, images,
        )

        return io.NodeOutput(response_text, thinking_text, ui={
            "text": [response_text],
            "thinking": [thinking_text],
            "usage": [usage_str],
            "cost": [cost_str],
            "model_used": [model],
            "cached": ["false"],
            "error": [""],
        })


class AnthropicClaudeExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            AnthropicClaudeNode,
        ]

    @override
    async def on_load(self) -> None:


        pass


async def comfy_entrypoint() -> AnthropicClaudeExtension:
    return AnthropicClaudeExtension()
