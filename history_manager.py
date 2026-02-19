"""
History manager for Anthropic Claude Node.
Saves and retrieves execution history (prompts, settings, responses).
© 2026 Created with ❤️ by Alex Munteanu | alexmunteanu.com
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

import folder_paths


THUMB_MAX_DIM = 300


def _get_history_dir():
    history_dir = Path(folder_paths.get_input_directory()) / "comfyui_anthropic_claude" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir


def _generate_entry_id():
    now = datetime.now()
    uid = uuid.uuid4().hex[:6]
    return now.strftime("%H%M%S") + "_" + uid, now


def _entry_date_path(history_dir, dt):
    return history_dir / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d")


def _save_thumbnails(image_tensor, entry_dir, entry_id):
    if image_tensor is None:
        return [], []
    paths = []
    dimensions = []
    t = image_tensor
    if len(t.shape) == 3:
        t = t.unsqueeze(0)
    for i in range(t.shape[0]):
        img_np = (t[i].cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
        pil_img = Image.fromarray(img_np)
        orig_w, orig_h = pil_img.size
        dimensions.append({"width": orig_w, "height": orig_h})
        if orig_w > THUMB_MAX_DIM or orig_h > THUMB_MAX_DIM:
            scale = THUMB_MAX_DIM / max(orig_w, orig_h)
            pil_img = pil_img.resize(
                (int(orig_w * scale), int(orig_h * scale)), Image.LANCZOS
            )
        thumb_path = entry_dir / (entry_id + "_" + str(i) + ".jpg")
        pil_img.save(thumb_path, format="JPEG", quality=65)
        paths.append(str(thumb_path))
    return paths, dimensions


def save_entry(data, image_tensor=None):
    history_dir = _get_history_dir()
    entry_id, now = _generate_entry_id()
    date_dir = _entry_date_path(history_dir, now)
    date_dir.mkdir(parents=True, exist_ok=True)

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

    json_path = date_dir / (entry_id + ".json")
    json_path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry_id


def _walk_entries(history_dir, date_from=None, date_to=None):
    entries = []
    if not history_dir.is_dir():
        return entries
    for year_dir in sorted(history_dir.iterdir(), reverse=True):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        for month_dir in sorted(year_dir.iterdir(), reverse=True):
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            for day_dir in sorted(month_dir.iterdir(), reverse=True):
                if not day_dir.is_dir() or not day_dir.name.isdigit():
                    continue
                date_str = year_dir.name + "-" + month_dir.name + "-" + day_dir.name
                if date_from and date_str < date_from:
                    continue
                if date_to and date_str > date_to:
                    continue
                for f in sorted(day_dir.glob("*.json"), reverse=True):
                    try:
                        entry = json.loads(f.read_text(encoding="utf-8"))
                        entry["_path"] = str(f)
                        entries.append(entry)
                    except (json.JSONDecodeError, OSError):
                        continue
    return entries


def list_entries(page=1, per_page=20, search="", date_from="", date_to="",
                 favorites_only=False, sort_by="date_desc"):
    history_dir = _get_history_dir()
    entries = _walk_entries(history_dir, date_from or None, date_to or None)

    if favorites_only:
        entries = [e for e in entries if e.get("favorite")]

    if search:
        q = search.lower()
        filtered = []
        for e in entries:
            if (q in e.get("prompt", "").lower() or
                    q in e.get("response", "").lower() or
                    q in e.get("model_display", "").lower() or
                    q in e.get("model", "").lower() or
                    q in e.get("template", "").lower()):
                filtered.append(e)
        entries = filtered

    if sort_by == "date_asc":
        entries.sort(key=lambda e: e.get("timestamp", ""))
    elif sort_by == "date_desc":
        entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    elif sort_by == "cost_desc":
        entries.sort(key=lambda e: e.get("cost") or 0, reverse=True)
    elif sort_by == "tokens_desc":
        entries.sort(key=lambda e: (e.get("input_tokens", 0) + e.get("output_tokens", 0)), reverse=True)

    total = len(entries)
    start = (page - 1) * per_page
    end = start + per_page
    page_entries = entries[start:end]

    summaries = []
    for e in page_entries:
        summaries.append({
            "id": e.get("id", ""),
            "timestamp": e.get("timestamp", ""),
            "prompt_preview": e.get("prompt", "")[:150],
            "response_preview": e.get("response", "")[:150],
            "model": e.get("model", ""),
            "model_display": e.get("model_display", ""),
            "seed": e.get("seed", 0),
            "template": e.get("template", "None"),
            "cost_str": e.get("cost_str", ""),
            "input_tokens": e.get("input_tokens", 0),
            "output_tokens": e.get("output_tokens", 0),
            "favorite": e.get("favorite", False),
            "has_images": bool(e.get("image_paths")),
            "has_thinking": bool(e.get("thinking")),
            "error": e.get("error"),
            "_path": e.get("_path", ""),
        })

    return {
        "entries": summaries,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


def get_entry(entry_path):
    p = Path(entry_path)
    history_dir = _get_history_dir()
    try:
        resolved = p.resolve()
        if not str(resolved).startswith(str(history_dir.resolve())):
            return None
    except (OSError, ValueError):
        return None
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def delete_entry(entry_path):
    p = Path(entry_path)
    history_dir = _get_history_dir()
    try:
        resolved = p.resolve()
        if not str(resolved).startswith(str(history_dir.resolve())):
            return False
    except (OSError, ValueError):
        return False
    if not p.is_file():
        return False
    try:
        entry = json.loads(p.read_text(encoding="utf-8"))
        for img_path in entry.get("image_paths", []):
            ip = Path(img_path)
            if ip.is_file():
                ip.unlink()
        p.unlink()
        parent = p.parent
        while parent != history_dir and parent.is_dir():
            try:
                next(parent.iterdir())
                break
            except StopIteration:
                parent.rmdir()
                parent = parent.parent
        return True
    except (json.JSONDecodeError, OSError):
        return False


def toggle_favorite(entry_path):
    p = Path(entry_path)
    history_dir = _get_history_dir()
    try:
        resolved = p.resolve()
        if not str(resolved).startswith(str(history_dir.resolve())):
            return None
    except (OSError, ValueError):
        return None
    if not p.is_file():
        return None
    try:
        entry = json.loads(p.read_text(encoding="utf-8"))
        entry["favorite"] = not entry.get("favorite", False)
        p.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
        return entry["favorite"]
    except (json.JSONDecodeError, OSError):
        return None


def get_stats():
    history_dir = _get_history_dir()
    entries = _walk_entries(history_dir)
    total_runs = len(entries)
    total_cost = 0.0
    total_tokens = 0
    model_counts = {}
    for e in entries:
        c = e.get("cost")
        if c is not None:
            total_cost += c
        total_tokens += e.get("input_tokens", 0) + e.get("output_tokens", 0)
        m = e.get("model_display") or e.get("model", "unknown")
        model_counts[m] = model_counts.get(m, 0) + 1
    most_used = ""
    if model_counts:
        most_used = max(model_counts, key=model_counts.get)
    return {
        "total_runs": total_runs,
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens,
        "most_used_model": most_used,
    }


def resolve_image_path(path_str):
    p = Path(path_str)
    history_dir = _get_history_dir()
    try:
        resolved = p.resolve()
        if not str(resolved).startswith(str(history_dir.resolve())):
            return None
    except (OSError, ValueError):
        return None
    if p.is_file():
        return p
    return None
