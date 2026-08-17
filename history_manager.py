"""
History manager for Anthropic Claude Node.
Saves and retrieves execution history (prompts, settings, responses).

Entries are addressed by an id and a date, never by a path. The id is the
file's own name and the date is the folder it sits in, so the address always
describes where the file actually is and nothing sent by the browser is ever
used to build a path. Every read, write and delete goes through safe_fs.

© 2026 Created with ❤️ by Alex Munteanu | alexmunteanu.com
"""

import os
import re
import uuid
from datetime import date as date_type, datetime
from pathlib import Path

import numpy as np
from PIL import Image

import folder_paths

from . import safe_fs


THUMB_MAX_DIM = 300

# The two folders this node owns inside ComfyUI's input directory. Checking
# for redirects starts here: the input directory itself may legitimately be
# moved with a junction, and refusing that broke relocated installs before.
NODE_FOLDER = "comfyui_anthropic_claude"
HISTORY_FOLDER = "history"

# How much work one listing or statistics pass will do. Reaching it reports
# truncated: true rather than quietly returning a short answer, because a
# silent cap makes a user's own history look like it disappeared.
MAX_SCAN_WORK = 20000

# A 300px JPEG at quality 65 is a few tens of KB. This is far above any real
# thumbnail and still refuses to load something large planted under the name.
MAX_IMAGE_BYTES = 2 * 1024 * 1024

MAX_SEARCH_CHARS = 200
PREVIEW_CHARS = 150

# The address of an entry, as written by _generate_entry_id: HHMMSS and six
# hex characters of a uuid4.
# Every pattern ends with \Z rather than $. In Python, $ also matches just
# before a final newline, so "2026-08-17\n" would pass as a date and the
# server would then echo that exact string back as the entry's address.
ID_RE = re.compile(r"^[0-9]{6}_[0-9a-f]{6}\Z")
DATE_RE = re.compile(r"^20[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])\Z")
INDEX_RE = re.compile(r"^[0-9]{1,2}\Z")
MAX_IMAGE_INDEX = 63

_YEAR_RE = re.compile(r"^20[0-9]{2}\Z")
_MONTH_RE = re.compile(r"^(0[1-9]|1[0-2])\Z")
_DAY_RE = re.compile(r"^(0[1-9]|[12][0-9]|3[01])\Z")
_ENTRY_FILE_RE = re.compile(r"^[0-9]{6}_[0-9a-f]{6}\.json\Z")
_DIGITS_RE = re.compile(r"^[0-9]+\Z")

SORT_KEYS = ("date_desc", "date_asc", "cost_desc", "tokens_desc")


# ---------------------------------------------------------------------------
# Address validation
# ---------------------------------------------------------------------------

def valid_id(value):
    return isinstance(value, str) and bool(ID_RE.match(value))


def valid_date(value):
    """True for a real calendar date in the store's YYYY-MM-DD spelling.

    The pattern alone is not enough: it happily accepts 2025-02-31, which
    would then address a folder that can never exist and, worse, would pass
    a range comparison as though it were a real day.
    """
    if not isinstance(value, str) or not DATE_RE.match(value):
        return False
    try:
        date_type(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return False
    return True


def valid_index(value):
    if not isinstance(value, str) or not INDEX_RE.match(value):
        return False
    return 0 <= int(value) <= MAX_IMAGE_INDEX


# ---------------------------------------------------------------------------
# Locating the store
# ---------------------------------------------------------------------------

def _input_root():
    return folder_paths.get_input_directory()


def _warn_blocked_chain(components):
    """Tell the user when a folder in the chain is a link, not a real folder.

    Refusing a redirected folder is deliberate, but doing it silently is not:
    the modal would just say there is no history, which looks exactly like an
    empty store. Someone who moved their history folder with mklink, which is
    an ordinary thing to do, would otherwise lose every entry from the upgrade
    onward without a word.

    A folder that is simply not there yet is normal on a fresh install and
    says nothing.
    """
    base = Path(_input_root())
    for depth in range(1, len(components) + 1):
        if safe_fs.descend(base, components[:depth]) is not None:
            continue
        try:
            os.lstat(base.joinpath(*components[:depth]))
        except OSError:
            return
        _add_warning(
            "History is unavailable: '" + "/".join(components[:depth])
            + "' inside ComfyUI's input folder is a link, not a real folder. "
            "Replace it with a real folder to save and read history again."
        )
        return


def _add_warning(text):
    """Surface a message as a toast, if the node module is loaded."""
    try:
        from .anthropic_claude_node import _add_startup_warning
    except Exception:
        return
    _add_startup_warning(text)


def _history_root():
    """The history folder, or None if it is missing or redirects somewhere."""
    root = safe_fs.descend(_input_root(), [NODE_FOLDER, HISTORY_FOLDER])
    if root is None:
        _warn_blocked_chain([NODE_FOLDER, HISTORY_FOLDER])
    return root


def _entry_path(entry_id, date):
    """Rebuild an entry's path from its address. None if anything is wrong."""
    if not valid_id(entry_id) or not valid_date(date):
        return None
    return safe_fs.descend(_input_root(), [
        NODE_FOLDER, HISTORY_FOLDER,
        date[0:4], date[5:7], date[8:10],
        entry_id + ".json",
    ])


def _thumb_name(entry_id, index):
    return entry_id + "_" + str(index) + ".jpg"


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

def _generate_entry_id():
    now = datetime.now()
    return now.strftime("%H%M%S") + "_" + uuid.uuid4().hex[:6], now


def _save_thumbnails(image_tensor, entry_dir, entry_id):
    """Write one JPEG per input image. Returns (paths, dimensions).

    The file name carries the slot number, and a slot is only used once its
    image is actually on disk, so the two lists always describe the same
    thumbnails and slot N is always the file ending _N.jpg. That is what lets
    the server work out a thumbnail's location from the entry id alone.
    """
    if image_tensor is None:
        return [], []
    paths = []
    dimensions = []
    tensor = image_tensor
    if len(tensor.shape) == 3:
        tensor = tensor.unsqueeze(0)
    slot = 0
    for i in range(tensor.shape[0]):
        if slot >= safe_fs.MAX_IMAGES:
            break
        img_np = (tensor[i].cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
        pil_img = Image.fromarray(img_np)
        orig_w, orig_h = pil_img.size
        if orig_w > THUMB_MAX_DIM or orig_h > THUMB_MAX_DIM:
            scale = THUMB_MAX_DIM / max(orig_w, orig_h)
            pil_img = pil_img.resize(
                (int(orig_w * scale), int(orig_h * scale)), Image.LANCZOS
            )
        thumb_path = entry_dir / _thumb_name(entry_id, slot)
        handle = safe_fs.open_new_exclusive(thumb_path)
        if handle is None:
            continue
        try:
            pil_img.save(handle, format="JPEG", quality=65)
        except (OSError, ValueError):
            handle.close()
            safe_fs.unlink_if_regular(thumb_path)
            continue
        handle.close()
        paths.append(str(thumb_path))
        dimensions.append({"width": orig_w, "height": orig_h})
        slot += 1
    return paths, dimensions


def save_entry(data, image_tensor=None):
    """Write one history entry. Returns its id, or None if it was not saved."""
    entry_id, now = _generate_entry_id()
    day_chain = [
        NODE_FOLDER, HISTORY_FOLDER,
        now.strftime("%Y"), now.strftime("%m"), now.strftime("%d"),
    ]
    date_dir = safe_fs.ensure_dir_chain(_input_root(), day_chain)
    if date_dir is None:
        _warn_blocked_chain(day_chain)
        return None

    thumb_paths, img_dims = _save_thumbnails(image_tensor, date_dir, entry_id)

    entry = {
        "id": entry_id,
        "timestamp": now.isoformat(),
        "prompt": data.get("prompt", ""),
        "model": data.get("model", ""),
        "model_display": data.get("model_display", ""),
        "seed": data.get("seed", 0),
        "template": data.get("template", "None"),
        "temperature": data.get("temperature", 1.0),
        "max_tokens": data.get("max_tokens", 4096),
        "extended_thinking": data.get("extended_thinking", False),
        "thinking_budget": data.get("thinking_budget", 4096),
        "max_image_size": data.get("max_image_size", 1024),
        # Nothing reads this any more. Thumbnails are found from the entry id.
        # It stays in the file so that going back to the previous release,
        # which does read it, still shows the thumbnails for entries written
        # by this one.
        "image_paths": thumb_paths,
        "image_dimensions": img_dims,
        "response": data.get("response", ""),
        "thinking": data.get("thinking", ""),
        "input_tokens": data.get("input_tokens", 0),
        "output_tokens": data.get("output_tokens", 0),
        "cost": data.get("cost"),
        "cost_str": data.get("cost_str", ""),
        "duration_ms": data.get("duration_ms", 0),
        "error": data.get("error"),
        "favorite": False,
    }

    if not safe_fs.write_json_atomic(date_dir / (entry_id + ".json"), entry):
        # The thumbnails were written first and are addressed through the
        # entry id, so without the entry file nothing can ever reach them
        # again. Take them back out rather than leave them on disk forever.
        for thumb in thumb_paths:
            safe_fs.unlink_if_regular(thumb)
        return None
    return entry_id


# ---------------------------------------------------------------------------
# Walking the store
# ---------------------------------------------------------------------------

def _sorted_names(directory, pattern, newest_first=True):
    names = [
        child.name for child in safe_fs.scan_children(directory, want_dir=True)
        if pattern.match(child.name)
    ]
    names.sort(reverse=newest_first)
    return names


def _iter_entries(progress, date_from="", date_to=""):
    """Yield normalized entries newest first, with their real id and date.

    Entries are handed over one at a time rather than collected into a list,
    so however large the store is, only one entry is held in memory at a time
    and the caller decides what little of it to keep.

    progress is updated as the walk runs: "scanned" counts the entry files
    looked at and "truncated" says whether the work limit was reached before
    the store ran out.
    """
    root = _history_root()
    if root is None:
        return
    budget = MAX_SCAN_WORK
    for year in _sorted_names(root, _YEAR_RE):
        year_dir = root / year
        for month in _sorted_names(year_dir, _MONTH_RE):
            month_dir = year_dir / month
            for day in _sorted_names(month_dir, _DAY_RE):
                date_str = year + "-" + month + "-" + day
                if date_from and date_str < date_from:
                    continue
                if date_to and date_str > date_to:
                    continue
                # Visiting a folder costs work too, so a store padded with
                # empty day folders cannot spin this loop for free.
                budget -= 1
                if budget <= 0:
                    progress["truncated"] = True
                    return
                day_dir = month_dir / day
                names = [
                    child.name
                    for child in safe_fs.scan_children(day_dir, want_dir=False)
                    if _ENTRY_FILE_RE.match(child.name)
                ]
                names.sort(reverse=True)
                for name in names:
                    if budget <= 0:
                        progress["truncated"] = True
                        return
                    budget -= 1
                    progress["scanned"] += 1
                    entry = safe_fs.read_entry_verified(day_dir / name)
                    if entry is None:
                        continue
                    entry["id"] = name[:-5]
                    entry["date"] = date_str
                    yield entry


def _summarize(entry):
    """The short form the listing sends. No paths, ever."""
    return {
        "id": entry["id"],
        "date": entry["date"],
        "timestamp": entry["timestamp"],
        "prompt_preview": entry["prompt"][:PREVIEW_CHARS],
        "response_preview": entry["response"][:PREVIEW_CHARS],
        "model": entry["model"],
        "model_display": entry["model_display"],
        "seed": entry["seed"],
        "template": entry["template"],
        "cost": entry["cost"],
        "cost_str": entry["cost_str"],
        "input_tokens": entry["input_tokens"],
        "output_tokens": entry["output_tokens"],
        "favorite": entry["favorite"],
        "image_count": entry["image_count"],
        "has_thinking": bool(entry["thinking"]),
        # Cut to the same length as the other previews. The row shows this in
        # a single ellipsised line, so nothing is gained by sending more, and
        # sending it whole let one crafted entry inflate a page of results by
        # a thousandfold. The full text is still there in the entry itself.
        "error": entry["error"][:PREVIEW_CHARS] if entry["error"] else entry["error"],
    }


def _matches(entry, needle):
    return (needle in entry["prompt"].lower()
            or needle in entry["response"].lower()
            or needle in entry["model_display"].lower()
            or needle in entry["model"].lower()
            or needle in entry["template"].lower())


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def list_entries(page=1, per_page=20, search="", date_from="", date_to="",
                 favorites_only=False, sort_by="date_desc"):
    """One page of the history, newest first unless asked otherwise.

    A page is a snapshot taken while the store may be changing underneath it.
    An entry saved or deleted during the walk may or may not appear, and two
    pages fetched one after the other may not line up perfectly. For an
    execution log that is fine, and it is the price of not locking the whole
    store for the length of a listing.
    """
    page = max(1, _to_int(page, 1))
    per_page = min(200, max(1, _to_int(per_page, 20)))
    if sort_by not in SORT_KEYS:
        sort_by = "date_desc"
    needle = search.lower()[:MAX_SEARCH_CHARS] if isinstance(search, str) else ""
    date_from = date_from if valid_date(date_from) else ""
    date_to = date_to if valid_date(date_to) else ""

    progress = {"scanned": 0, "truncated": False}
    records = []
    for entry in _iter_entries(progress, date_from, date_to):
        if favorites_only and not entry["favorite"]:
            continue
        if needle and not _matches(entry, needle):
            continue
        records.append(_summarize(entry))

    # Ordering by date and id uses where the file actually lives rather than
    # the timestamp written inside it, so an entry cannot push itself to the
    # top of the list by claiming a time it was not written at.
    if sort_by == "date_asc":
        records.sort(key=lambda r: (r["date"], r["id"]))
    elif sort_by == "cost_desc":
        records.sort(key=lambda r: r["cost"] or 0.0, reverse=True)
    elif sort_by == "tokens_desc":
        records.sort(key=lambda r: r["input_tokens"] + r["output_tokens"], reverse=True)
    else:
        records.sort(key=lambda r: (r["date"], r["id"]), reverse=True)

    total = len(records)
    start = (page - 1) * per_page
    return {
        "entries": records[start:start + per_page],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "scanned": progress["scanned"],
        "truncated": progress["truncated"],
    }


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_entry(entry_id, date):
    """One full entry, or None."""
    path = _entry_path(entry_id, date)
    if path is None:
        return None
    entry = safe_fs.read_entry_verified(path)
    if entry is None:
        return None
    entry["id"] = entry_id
    entry["date"] = date
    return entry


def get_stats():
    progress = {"scanned": 0, "truncated": False}
    total_runs = 0
    total_cost = 0.0
    total_tokens = 0
    model_counts = {}
    for entry in _iter_entries(progress):
        total_runs += 1
        if entry["cost"] is not None:
            total_cost += entry["cost"]
        total_tokens += entry["input_tokens"] + entry["output_tokens"]
        name = entry["model_display"] or entry["model"] or "unknown"
        model_counts[name] = model_counts.get(name, 0) + 1
    most_used = max(model_counts, key=model_counts.get) if model_counts else ""
    return {
        "total_runs": total_runs,
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens,
        "most_used_model": most_used,
        "truncated": progress["truncated"],
    }


def read_image_bytes(entry_id, date, index):
    """A thumbnail's bytes, or None.

    The location is worked out from the entry id and the slot number, so the
    only images this can ever return are ones this node wrote. The bytes are
    read and handed back rather than the file being served directly, so the
    checks apply to the data that actually goes out instead of to a name that
    gets resolved a second time on the way.
    """
    if not valid_id(entry_id) or not valid_date(date) or not valid_index(index):
        return None
    path = safe_fs.descend(_input_root(), [
        NODE_FOLDER, HISTORY_FOLDER,
        date[0:4], date[5:7], date[8:10],
        _thumb_name(entry_id, int(index)),
    ])
    if path is None:
        return None
    return safe_fs.read_bytes_verified(path, MAX_IMAGE_BYTES)


# ---------------------------------------------------------------------------
# Changing
# ---------------------------------------------------------------------------

def delete_entry(entry_id, date):
    """Delete one entry and its own thumbnails. True if the entry is gone."""
    if not valid_id(entry_id) or not valid_date(date):
        return False
    with safe_fs.entry_lock(entry_id):
        path = _entry_path(entry_id, date)
        if path is None:
            return False
        day_dir = path.parent

        # Only files named after THIS entry are removed, and only from the day
        # folder the entry itself sits in. Earlier releases deleted whatever
        # the entry's own JSON listed, which let a planted entry name another
        # entry's files and have them deleted along with it. Working the names
        # out from the id instead makes that impossible to express.
        prefix = entry_id + "_"
        for child in safe_fs.scan_children(day_dir, want_dir=False):
            name = child.name
            if not name.startswith(prefix) or not name.lower().endswith(".jpg"):
                continue
            if not _DIGITS_RE.match(name[len(prefix):-4]):
                continue
            safe_fs.unlink_if_regular(day_dir / name)

        if not safe_fs.unlink_if_regular(path):
            return False

        # Tidy up the day, month and year folders once they are empty. rmdir
        # refuses a folder with anything in it, so there is nothing to test
        # first and nothing to get wrong between testing and acting. The three
        # steps are the three levels there are, so this cannot climb out of
        # the history folder even if the comparison below were ever wrong.
        root = _history_root()
        parent = day_dir
        for _ in range(3):
            if root is None or parent == root:
                break
            try:
                os.rmdir(parent)
            except OSError:
                break
            parent = parent.parent
        return True


def toggle_favorite(entry_id, date):
    """Flip an entry's favourite flag. Returns the new value, or None.

    The current value is read through the checked reader, which reports the
    flag as a real true or false whatever the file actually holds, and the new
    value is written by the setter, which changes that one key and leaves the
    rest of the file exactly as it was. Neither step ever produces the stored
    object itself, so there is no unchecked data to mishandle.
    """
    if not valid_id(entry_id) or not valid_date(date):
        return None
    with safe_fs.entry_lock(entry_id):
        path = _entry_path(entry_id, date)
        if path is None:
            return None
        entry = safe_fs.read_entry_verified(path)
        if entry is None:
            return None
        new_state = not entry["favorite"]
        if not safe_fs.set_entry_flag(path, "favorite", new_state):
            return None
        return new_state
