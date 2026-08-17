"""
Verified filesystem primitives for the Anthropic Claude node's history store.

The history routes reach the disk through this module. They never receive a
path from the browser: they receive an entry id and a date, and the server
rebuilds the path from them. These primitives are what make that rebuilt path
safe to act on.

One call sits outside: history_manager removes an empty day, month or year
folder with os.rmdir directly. That is left alone deliberately. On Windows,
RemoveDirectoryW deletes a junction or a symlink itself and never follows it to
what it points at, which Microsoft states outright, so routing it through here
would add a check that changes nothing. rmdir also refuses a folder that still
has anything in it, so there is no emptiness test to race.

WHAT THIS LAYER DEFENDS AGAINST

- Redirection through reparse points. A junction or a symlink planted anywhere
  in the node's own directory chain (comfyui_anthropic_claude / history /
  YYYY / MM / DD / the file itself) is spotted by its reparse tag and refused,
  so a listing walk cannot be steered onto another drive or a network share.
  Junctions are the case that matters most: Python reports is_symlink() as
  False for a junction, so the reparse tag is the only thing that identifies
  one. Only tags that actually redirect are refused. Windows Deduplication,
  OneDrive Files On-Demand and app execution aliases also use reparse points
  but do not redirect, and refusing those would break perfectly normal
  installs, so they are accepted.
- Hard links. A second directory entry pointing at a file outside the history
  tree is invisible to path resolution. Reads check the link count on the open
  handle, and writes never modify a file in place: they write a fresh temporary
  file and rename it over the target, which detaches the link instead of
  writing through it.
- Swap-after-check on the file itself. Every read confirms, after opening, that
  the handle it holds is the same file the pre-open check inspected.
- Runaway reads. Every read is bounded by a byte cap enforced during the read,
  not by a size taken from the file's metadata, which a writer running at the
  same time can invalidate.
- Blocking on an unreachable network location. Nothing here resolves a path
  supplied by the caller, so nothing here can be pointed at a file server and
  made to wait out a connection timeout. Reads also check for a link before
  opening rather than after, because opening comes first would already have
  paid that wait.

WHAT THIS LAYER DOES NOT DEFEND AGAINST

The residual ancestor race. Another program running as the same user can swap
one of the parent folders (an ancestor directory) WHILE a request is in flight.
Each operation checks the chain folder by folder, but Windows then resolves the
whole path again when the file is actually opened, so an ancestor replaced in
between redirects the operation, and comparing file identities cannot spot it
because both sides resolve through the same replaced folder. Closing that gap
needs handle-relative traversal, which Python does not offer on Windows
(os.supports_dir_fd is empty there). Anyone able to win that race is already
running code as the user and has more direct ways to reach the same files.

So the containment here is best effort against a local program racing a live
request, and solid against anything planted in advance. That is stated rather
than glossed over, because the difference decides what this layer can be
relied on for.

Rewriting an entry, which favouriting does, re-encodes data this module did not
author. A small file can expand enormously on the way back out: deeply nested
structures cost a couple of bytes each to store and far more to lay out with
indentation. So the write is capped while it is being built, not after, and
gives up the moment the result would pass the cap. That bounds the memory used
and the bytes written together, and it is why the cap is a parameter on the
write rather than only on the read.

© 2026 Created with ❤️ by Alex Munteanu | alexmunteanu.com
"""

import json
import math
import os
import re
import stat as stat_module
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


# The name-surrogate bit of a Windows reparse tag. Set on junctions
# (0xa0000003), volume mount points (also 0xa0000003) and symlinks
# (0xa000000c), which all substitute one name for another. Not set on
# Deduplication (0x80000013), OneDrive cloud files (0x9000001a) or app
# execution aliases (0x8000001b), which leave the name alone.
# Testing FILE_ATTRIBUTE_REPARSE_POINT instead would refuse all six.
NAME_SURROGATE = 0x20000000

# 256 KB per history file. The largest entry in a 1695-entry real store is
# under 10 KB, so this is 26x headroom and still bounds a planted file.
MAX_ENTRY_BYTES = 256 * 1024

# Widest a single stored text field is kept at. The file cap above already
# bounds the whole body; this stops one field from filling all of it.
MAX_FIELD_CHARS = 200000

# Thumbnails per entry. Matches the index range the image route accepts.
MAX_IMAGES = 64

# Characters that give a name power beyond naming one file in one folder:
# the two separators, the drive and alternate-stream colon, the wildcards,
# the redirection characters, and the control range.
_UNSAFE_CHARS_RE = re.compile(r"[\x00-\x1f<>:\"/\\|?*]")

# Windows treats these as devices whatever folder they sit in and whatever
# extension follows, so CON.md opens the console rather than a file. The
# dollar-suffixed console names and CLOCK$ count too, and so do COM0 and LPT0.
_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"]
    + ["COM" + str(n) for n in range(0, 10)]
    + ["LPT" + str(n) for n in range(0, 10)]
)

# Windows reads the superscript digits as their plain forms when deciding
# whether a name is a device, so COM<superscript one> is COM1. Python's
# isalnum() says these are letters-or-digits, so the save-template sanitizer
# keeps them and they would otherwise slip past the list above.
_SUPERSCRIPT_DIGITS = {0xB9: "1", 0xB2: "2", 0xB3: "3"}

# os.replace can lose a brief race with a search indexer or an antivirus
# scanner holding the target open. Back off between tries instead of
# hammering: a tight loop is over in a few milliseconds and gives those
# handles no time to close. Total wait is about one second.
_REPLACE_BACKOFF = (0.01, 0.05, 0.15, 0.3, 0.5)

_O_BINARY = getattr(os, "O_BINARY", 0)


# ---------------------------------------------------------------------------
# Link detection
# ---------------------------------------------------------------------------

def is_link(st):
    """True when a stat result describes something that redirects elsewhere.

    Accepts any stat result: os.lstat(), or DirEntry.stat(follow_symlinks=False)
    which on Windows is answered from the directory listing at no extra cost.
    Anything unrecognizable is treated as a link, so a surprise is refused
    rather than followed.
    """
    mode = getattr(st, "st_mode", None)
    if not isinstance(mode, int):
        return True
    if stat_module.S_ISLNK(mode):
        return True
    tag = getattr(st, "st_reparse_tag", 0)
    if not isinstance(tag, int):
        return True
    return bool(tag & NAME_SURROGATE)


def is_safe_component(name):
    """True when name is a single, plain file or folder name.

    Refuses anything that can reach past the folder it is used in: the two
    separators, a drive or stream colon, dot and dot-dot, wildcards, control
    characters, and the reserved device names. Also refuses a trailing dot or
    space, which Windows strips on the way to disk, so that "entry." and
    "entry" would compare as different strings while naming the same file.

    Ordinary punctuation, spaces and accented letters are allowed, because a
    template can legitimately be called "Luma Ray 2 & 3" and refusing that
    would break saving it without making anything safer.
    """
    if not isinstance(name, str) or not name or len(name) > 255:
        return False
    if name in (".", ".."):
        return False
    if name[-1] in (".", " ") or name[0] == " ":
        return False
    if _UNSAFE_CHARS_RE.search(name):
        return False
    stem = name.split(".")[0].strip().upper().translate(_SUPERSCRIPT_DIGITS)
    return stem not in _RESERVED_NAMES


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------

def scan_children(directory, want_dir=False):
    """Yield the directory's children that are safe to use.

    Skips anything that redirects and anything of the wrong kind. On Windows
    the reparse tag and the file kind both come from the directory listing
    itself, so the filtering costs no extra system calls. Never raises: an
    unreadable directory simply yields nothing.
    """
    try:
        scanner = os.scandir(directory)
    except OSError:
        return
    try:
        for entry in scanner:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if is_link(st):
                continue
            if want_dir:
                if not stat_module.S_ISDIR(st.st_mode):
                    continue
            elif not stat_module.S_ISREG(st.st_mode):
                continue
            yield entry
    except OSError:
        return
    finally:
        try:
            scanner.close()
        except OSError:
            pass


def descend(root, components):
    """Walk root down through components, refusing any redirect on the way.

    Each component is appended and checked on its own, so a junction sitting
    three levels down is caught at that level instead of after the whole path
    has already been resolved through it. Returns the joined path, or None if
    a component is malformed, missing, or redirects.

    root itself is NOT checked. Callers pass the ComfyUI input directory as
    root, and relocating that directory with a junction is a legitimate setup
    that must keep working. Checking starts at the first folder this node owns.
    """
    try:
        current = Path(root)
    except (TypeError, ValueError):
        return None
    for name in components:
        if not is_safe_component(name):
            return None
        current = current / name
        try:
            st = os.lstat(current)
        except (OSError, ValueError):
            return None
        if is_link(st):
            return None
    return current


def ensure_dir_chain(root, components):
    """Create the folder chain under root, refusing any redirect. Path or None.

    The write-side twin of descend(). Each level is checked before the next is
    created, so a junction already sitting at one of them stops the whole thing
    instead of the rest being created inside whatever it points at. That is the
    reason this cannot just be mkdir(parents=True): mkdir accepts an existing
    junction as an existing folder, which would quietly move the entire history
    store wherever the junction leads.
    """
    try:
        current = Path(root)
    except (TypeError, ValueError):
        return None
    for name in components:
        if not is_safe_component(name):
            return None
        current = current / name
        try:
            st = os.lstat(current)
        except OSError:
            try:
                os.mkdir(current)
            except FileExistsError:
                pass
            except OSError:
                return None
            try:
                st = os.lstat(current)
            except OSError:
                return None
        except ValueError:
            return None
        if is_link(st) or not stat_module.S_ISDIR(st.st_mode):
            return None
    return current


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read_bytes_verified(path, max_bytes):
    """Read a plain file, or return None. Never raises.

    The order matters:

    1. Check for a redirect BEFORE opening. Opening first would follow a
       symlink pointing at an unreachable file server and stall this worker
       for the whole connection timeout before the check could refuse it.
    2. Refuse anything that is not a plain file.
    3. Open, and stat the open handle.
    4. Refuse a file with more than one name. A hard link is a second name for
       data that may live outside the history tree, and no amount of path
       checking can see it; the count on the handle can.
    5. Confirm the handle is the same file step 1 inspected, so a swap between
       the check and the open is caught.
    6. Read with the cap enforced as it goes, asking for one byte more than
       allowed so a file at the limit is told apart from one over it. The size
       reported by the stat is not used as the bound, because a writer can
       change the file after it is taken.
    """
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        return None
    try:
        pre = os.lstat(path)
    except (OSError, ValueError):
        return None
    if is_link(pre):
        return None
    if not stat_module.S_ISREG(pre.st_mode):
        return None

    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | _O_BINARY)
        opened = os.fstat(fd)
        if getattr(opened, "st_nlink", 1) > 1:
            return None
        if not os.path.samestat(opened, pre):
            return None
        chunks = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            return None
        return data
    except (OSError, ValueError):
        return None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def read_entry_verified(path, max_bytes=MAX_ENTRY_BYTES):
    """Read one history entry as a normalized dict, or None. Never raises.

    Reading, decoding and normalizing happen together, in that order, inside
    this one function. Nothing else in the codebase ever sees a field straight
    off the disk, so filtering, searching, sorting, paging and the JSON
    response can all count on every field already being the right type.
    """
    raw = read_bytes_verified(path, max_bytes)
    if raw is None:
        return None
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    except RecursionError:
        # A body nested thousands of levels deep exhausts the decoder's own
        # stack. That is neither a ValueError nor a UnicodeDecodeError, and
        # letting it out would take the whole listing down with it.
        return None
    if not isinstance(decoded, dict):
        return None
    return _normalize_entry(decoded)


def set_entry_flag(path, key, value, max_bytes=MAX_ENTRY_BYTES):
    """Change one key in a stored entry and leave everything else alone.

    True if the file was rewritten, False otherwise. Never raises.

    The unchecked object exists only inside this function and is never handed
    back, so there is no way for raw stored data to reach filtering, sorting,
    searching, caching or the browser. Everything that displays an entry goes
    through read_entry_verified instead.

    Keeping the rest of the file untouched is the point. Writing back a tidied
    version would drop fields the previous release still reads, and this
    release promises to change nothing already on disk beyond the one key
    being set.
    """
    if not isinstance(key, str):
        return False
    raw = read_bytes_verified(path, max_bytes)
    if raw is None:
        return False
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return False
    if not isinstance(body, dict):
        return False
    body[key] = value
    return write_json_atomic(path, body, max_bytes)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _as_text(value, limit=MAX_FIELD_CHARS):
    if not isinstance(value, str):
        return ""
    return value[:limit]


def _as_int(value, default, low, high):
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if not math.isfinite(value):
            return default
        number = int(value)
    else:
        return default
    if number < low:
        return low
    if number > high:
        return high
    return number


def _as_float(value, default, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    number = float(value)
    # Infinity and NaN survive json.loads and come back out of json.dumps as
    # the bare tokens Infinity and NaN, which JSON.parse in the browser
    # rejects outright. One planted entry would break the whole listing.
    if not math.isfinite(number):
        return default
    if number < low:
        return low
    if number > high:
        return high
    return number


def _as_optional_float(value, low, high):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    if number < low:
        return low
    if number > high:
        return high
    return number


def _as_dimensions(value):
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:MAX_IMAGES]:
        if not isinstance(item, dict):
            continue
        out.append({
            "width": _as_int(item.get("width"), 0, 0, 100000),
            "height": _as_int(item.get("height"), 0, 0, 100000),
        })
    return out


def _normalize_entry(raw):
    """Turn a decoded entry body into a fixed shape with known types.

    id and date come out empty on purpose. They are the entry's address, and
    the caller sets them from where the file actually sits on disk, so a
    planted file cannot claim to be somewhere it is not.

    image_paths is not carried through. It is still written to new entries so
    that rolling back to the previous release keeps showing thumbnails, but
    nothing reads it any more: thumbnail addresses are worked out from the
    entry id, and sending absolute paths to the browser is what made all the
    path handling necessary in the first place.
    """
    dimensions = _as_dimensions(raw.get("image_dimensions"))
    count = len(dimensions)
    if not count:
        # Entries written before dimensions were recorded still list their
        # thumbnails. Only the length of that list is used, never a path.
        stored = raw.get("image_paths")
        if isinstance(stored, list):
            count = min(len(stored), MAX_IMAGES)

    return {
        "id": "",
        "date": "",
        "timestamp": _as_text(raw.get("timestamp"), 64),
        "prompt": _as_text(raw.get("prompt")),
        "model": _as_text(raw.get("model"), 200),
        "model_display": _as_text(raw.get("model_display"), 200),
        "seed": _as_int(raw.get("seed"), 0, 0, 2 ** 63 - 1),
        "template": _as_text(raw.get("template"), 200) or "None",
        "temperature": _as_float(raw.get("temperature"), 1.0, 0.0, 1.0),
        "max_tokens": _as_int(raw.get("max_tokens"), 4096, 1, 10000000),
        "extended_thinking": raw.get("extended_thinking") is True,
        "thinking_budget": _as_int(raw.get("thinking_budget"), 4096, 0, 10000000),
        "max_image_size": _as_int(raw.get("max_image_size"), 1024, 1, 100000),
        "image_count": count,
        "image_dimensions": dimensions,
        "response": _as_text(raw.get("response")),
        "thinking": _as_text(raw.get("thinking")),
        "input_tokens": _as_int(raw.get("input_tokens"), 0, 0, 10 ** 12),
        "output_tokens": _as_int(raw.get("output_tokens"), 0, 0, 10 ** 12),
        "cost": _as_optional_float(raw.get("cost"), 0.0, 10 ** 9),
        "cost_str": _as_text(raw.get("cost_str"), 64),
        "duration_ms": _as_int(raw.get("duration_ms"), 0, 0, 10 ** 12),
        "error": _as_text(raw.get("error")) if isinstance(raw.get("error"), str) else None,
        "favorite": raw.get("favorite") is True,
    }


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _encode_bounded(obj, max_bytes):
    """Encode obj as JSON, giving up as soon as it would pass max_bytes.

    The encoding is built piece by piece and abandoned at the moment the total
    goes over, so a small object that expands hugely costs the cap in memory
    rather than the full expanded size. Encoding it all and then measuring
    would be too late: the memory has already been taken by then.

    Produces the same bytes as json.dumps(obj, indent=2, ensure_ascii=False),
    checked against every entry in a real 1695-entry store.
    """
    encoder = json.JSONEncoder(indent=2, ensure_ascii=False)
    chunks = []
    total = 0
    try:
        for piece in encoder.iterencode(obj):
            data = piece.encode("utf-8")
            total += len(data)
            if total > max_bytes:
                return None
            chunks.append(data)
    except (TypeError, ValueError, RecursionError, MemoryError):
        return None
    return b"".join(chunks)


def write_json_atomic(path, obj, max_bytes=MAX_ENTRY_BYTES):
    """Write obj as JSON by rename. True on success, False otherwise.

    Keeps the two-space indented, non-escaped layout the store has always
    used, so a file written by this release and one written by the previous
    one are byte-compatible and rolling back changes nothing on disk.

    max_bytes bounds what is produced, not only what was read. A stored entry
    can be read within the read cap and still encode to hundreds of times its
    own size, which would write a file too large to ever read back, so the
    entry would disappear from the listing it was just edited in.
    """
    payload = _encode_bounded(obj, max_bytes)
    if payload is None:
        return False
    return write_bytes_atomic(path, payload)


def write_bytes_atomic(path, payload):
    """Write bytes by rename. True on success, False otherwise. Never raises.

    A fresh file is created next to the target with a name nothing can guess,
    then renamed over it. That replaces the directory entry instead of writing
    through it, so if the target happens to be a hard link to a file elsewhere,
    the other name keeps its original content and this one becomes a normal
    single-named file.

    There is deliberately no in-place fallback when the rename cannot be done.
    Writing in place is exactly the behaviour this function exists to avoid,
    and quietly falling back to it would undo the protection at the moment it
    is needed most.
    """
    try:
        target = Path(path)
    except (TypeError, ValueError):
        return False
    if not isinstance(payload, (bytes, bytearray)):
        return False

    # The temporary name has to fit in the same 255-character limit as the
    # real one, and it adds eighteen characters of its own. Without trimming,
    # a long but perfectly legal name can be created and then never replaced,
    # because only the replace path builds a temporary sibling. The random
    # part keeps the trimmed name unique, and the exclusive create catches a
    # collision anyway.
    suffix = "." + uuid.uuid4().hex[:12] + ".tmp"
    stem = target.name[:254 - len(suffix)]
    temp = target.parent / ("." + stem + suffix)
    fd = None
    try:
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_BINARY, 0o600)
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
    except (OSError, ValueError):
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        _discard(temp)
        return False
    try:
        os.close(fd)
    except OSError:
        _discard(temp)
        return False

    for index in range(len(_REPLACE_BACKOFF) + 1):
        try:
            os.replace(temp, target)
            return True
        except OSError:
            if index >= len(_REPLACE_BACKOFF):
                break
            time.sleep(_REPLACE_BACKOFF[index])
    _discard(temp)
    return False


def _discard(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def open_new_exclusive(path):
    """Open a brand new file for binary writing, or return None.

    Fails if anything already exists at that name, so it can never write
    through a link someone left lying in wait. Never raises; the caller closes
    the returned file.
    """
    fd = None
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_BINARY, 0o600)
        return os.fdopen(fd, "wb")
    except (OSError, ValueError):
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        return None


def unlink_if_regular(path):
    """Delete a plain file. True if it is gone, False otherwise. Never raises.

    The check is there to avoid removing something that is not ours. It is not
    load-bearing for safety: on Windows, deleting a junction or a symlink
    removes the link itself and never touches what it points at, which
    Microsoft states outright for DeleteFileW and RemoveDirectoryW. So even
    if the check were raced, the file at the other end would survive.
    """
    try:
        st = os.lstat(path)
    except (OSError, ValueError):
        return False
    if is_link(st) or not stat_module.S_ISREG(st.st_mode):
        return False
    try:
        os.unlink(path)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Per-entry serialization
# ---------------------------------------------------------------------------

_entry_locks = {}
_entry_locks_guard = threading.Lock()


@contextmanager
def entry_lock(entry_id):
    """Hold a lock for one entry while it is read and written.

    Favouriting reads an entry and writes it straight back. Two requests for
    the same entry landing on two worker threads would otherwise collide on
    the rename and one would fail for no good reason. The table of locks is
    counted rather than capped: a lock exists only while somebody is waiting
    on it or holding it, so the table can never grow past the number of
    requests running at once, which the worker pool already limits.
    """
    key = str(entry_id)
    with _entry_locks_guard:
        state = _entry_locks.get(key)
        if state is None:
            state = [threading.Lock(), 0]
            _entry_locks[key] = state
        state[1] += 1
        lock = state[0]
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _entry_locks_guard:
            state[1] -= 1
            if state[1] <= 0:
                _entry_locks.pop(key, None)
