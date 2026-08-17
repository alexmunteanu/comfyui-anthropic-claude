"""
ComfyUI Anthropic Claude Node
Custom node for calling the Anthropic Claude API with text and image inputs.
© 2026 Created with ❤️ by Alex Munteanu | alexmunteanu.com
"""

VERSION = "1.5.25"

WEB_DIRECTORY = "./js"

from .anthropic_claude_node import (
    comfy_entrypoint,
    BUILTIN_TEMPLATES,
    LEGACY_TEMPLATE_ALIASES,
    MAX_TEMPLATE_BYTES,
    _get_user_templates_dir,
    _load_template,
    _list_all_template_names,
    _startup_warnings,
    _api_error,
    _refresh_models,
    _set_session_api_key,
)

from . import history_manager
from . import safe_fs

try:
    import asyncio
    import concurrent.futures
    import functools
    import json
    import logging
    import os
    import time
    import urllib.parse

    from server import PromptServer
    from aiohttp import web

    # Reading the history means touching the disk, and doing that inside an
    # async handler runs it on the same loop that serves every other ComfyUI
    # request, so one slow listing stalls the whole server. The work goes to
    # a small pool of worker threads instead. The pool is deliberately small:
    # an unlimited one would simply move the problem from the loop to the
    # disk and to memory.
    _executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=4, thread_name_prefix="anthropic-claude-history")

    # How many pieces of disk work may run at once, and how long a request
    # will wait for a turn before giving up. The wait is the important half:
    # without it, a burst is turned away the instant the workers are busy,
    # which sounds even-handed and is not.
    MAX_IN_FLIGHT = 4
    SLOT_WAIT_SECONDS = 2.0

    # Most distinct scans that may be shared at once. Entries are removed as
    # they finish, so this only ever caps a pathological spread of queries.
    MAX_SHARED_CALLS = 64

    # Marks "no worker came free in time" so it cannot be confused with a
    # piece of work that legitimately produced no result.
    _BUSY = object()

    _slots = None
    _slots_loop = None
    _shared_calls = {}

    # Listing and statistics both read the whole store. Repeats within this
    # window reuse the last answer, so a burst costs one pass rather than one
    # per request. Kept short because it is only there to absorb bursts, and
    # cleared outright whenever something changes.
    CACHE_TTL_SECONDS = 2.0
    MAX_CACHED_RESULTS = 32
    _result_cache = {}

    # Longest API key accepted from the error modal. Real keys are around a
    # hundred characters.
    MAX_API_KEY_CHARS = 512

    # An address is an id and a date. A few hundred bytes is generous; the
    # limit is here so a body is never decoded before its size is known.
    MAX_ADDRESS_BODY_BYTES = 4096
    # A template body is its content plus the JSON around it, and JSON escapes
    # can double a string, so this allows for that on top of the content cap.
    MAX_TEMPLATE_BODY_BYTES = MAX_TEMPLATE_BYTES * 2 + 8192

    def _get_slots():
        """The free-worker count for the loop that is currently running.

        Made on first use rather than at import, because this kind of counter
        attaches itself to the loop that first touches it. ComfyUI runs one
        loop for its whole life, so it is made once; if a different loop ever
        turns up it gets its own counter instead of raising.
        """
        global _slots, _slots_loop
        loop = asyncio.get_running_loop()
        if _slots is None or _slots_loop is not loop:
            _slots = asyncio.Semaphore(MAX_IN_FLIGHT)
            _slots_loop = loop
        return _slots

    async def _run_with_slot(func, args, kwargs, started=None):
        """Take a worker, do the work, give the worker back.

        Returns _BUSY if no worker came free in time. `started` is set the
        moment a worker is taken, which is the point after which giving up on
        this piece of work no longer helps anyone.
        """
        slots = _get_slots()
        try:
            await asyncio.wait_for(slots.acquire(), timeout=SLOT_WAIT_SECONDS)
        except asyncio.TimeoutError:
            return _BUSY
        if started is not None:
            started.set()
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                _executor, functools.partial(func, *args, **kwargs))
        finally:
            slots.release()

    async def _offload(func, *args, **kwargs):
        """Run blocking work on a worker thread, waiting briefly for a turn.

        Returns _BUSY only once the wait has run out.

        Turning a request away the instant every worker is busy sounds
        even-handed and is the opposite. Being refused costs whoever is
        flooding almost nothing, so they immediately ask again and take the
        next free worker too, while the person actually using the UI needs one
        worker once and never wins the race for it. Making everyone queue for
        the same short while costs the flooder exactly what it costs anyone
        else, and the event loop stays free either way, which was the point of
        moving this work off it.
        """
        return await _run_with_slot(func, args, kwargs)

    async def _offload_shared(key, func, *args, **kwargs):
        """Let identical requests arriving together share one run.

        Reading the whole store costs the same whether one page asked for it
        or fifty did, so the first caller does the work and the rest wait on
        its answer instead of each queueing for a worker of their own. That is
        what keeps the UI's own repeated query cheap while something else is
        hammering the store with a different one.

        Only ever used for the read-only routes that scan everything. Anything
        that CHANGES something must not be shared: two clicks on the same
        favourite would come back with one answer between them and one of the
        two changes would quietly vanish.
        """
        run = _shared_calls.get(key)
        started_it = run is None
        if started_it:
            if len(_shared_calls) >= MAX_SHARED_CALLS:
                return await _offload(func, *args, **kwargs)
            loop = asyncio.get_running_loop()
            started = asyncio.Event()
            run = {"task": None, "started": started, "waiting": 0}
            run["task"] = loop.create_task(
                _run_with_slot(func, args, kwargs, started))
            _shared_calls[key] = run
            run["task"].add_done_callback(functools.partial(_finish_shared, key))
        run["waiting"] += 1
        try:
            # Shielded either way, so one caller giving up, which a closed
            # browser tab does, cannot cancel work the others still want.
            #
            # Whoever started the run sees it through. Its wait for a worker
            # is already limited inside the run itself, and once it has one,
            # cutting the answer short would throw away work that is nearly
            # done and report "busy" to the one request that was not waiting
            # on anybody. Reading the whole store takes noticeably longer when
            # several reads run at once, so a limit here would fire on exactly
            # the requests that were being served properly.
            #
            # Anyone who merely joined an existing run does get a limit: they
            # did not start this work, and if what they joined has stalled,
            # waiting on it is no better than waiting for a worker.
            if started_it:
                return await asyncio.shield(run["task"])
            return await asyncio.wait_for(
                asyncio.shield(run["task"]), timeout=SLOT_WAIT_SECONDS)
        except asyncio.TimeoutError:
            return _BUSY
        finally:
            run["waiting"] -= 1
            # Nobody is waiting on this any more. If it has not taken a worker
            # yet, drop it. Letting it go on to read the whole store for an
            # answer no one will ever see would keep that worker from the next
            # person in the queue, and a flood of abandoned reads starving
            # everyone else is precisely the failure this wait exists to fix.
            # Once it HAS a worker it is left alone: the read cannot be
            # stopped anyway, and its answer is worth keeping for the retry.
            if (run["waiting"] <= 0 and not run["started"].is_set()
                    and not run["task"].done()):
                run["task"].cancel()

    def _finish_shared(key, task):
        """Retire a finished run and keep its answer for whoever asks next.

        Remembering the answer here rather than in the route matters when a
        caller gave up waiting: the run carries on, its result is kept, and
        the retry that the 503 asked for is answered from memory instead of
        starting the same scan over again.
        """
        _shared_calls.pop(key, None)
        if task.cancelled():
            return
        # Reading the exception also marks it as seen, which is what stops a
        # failed run from being reported later as an error nobody looked at.
        if task.exception() is not None:
            return
        result = task.result()
        if result is not _BUSY:
            _cache_put(key, result)

    def _guarded(handler):
        """Turn an unexpected failure into a plain 500 instead of letting it
        escape. A handler that raises would otherwise be answered by the
        server's own error page, which says more about the machine than the
        user needs and differs from how every other failure here is reported.
        """
        @functools.wraps(handler)
        async def wrapper(request):
            try:
                return await handler(request)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.getLogger(__name__).exception(
                    "Anthropic Claude: %s failed", handler.__name__)
                return web.json_response({"error": "Request failed"}, status=500)
        return wrapper

    def _busy_response():
        # Retry-After is set on the response rather than passed in, so it is
        # attached whichever way the response object was built.
        response = web.json_response({"error": "Busy, try again"}, status=503)
        response.headers["Retry-After"] = "1"
        return response

    def _cached(key):
        hit = _result_cache.get(key)
        if hit is None:
            return None
        if hit[0] <= time.monotonic():
            _result_cache.pop(key, None)
            return None
        return hit[1]

    def _cache_put(key, value):
        if len(_result_cache) >= MAX_CACHED_RESULTS:
            _result_cache.clear()
        _result_cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, value)

    def _cache_clear():
        _result_cache.clear()

    # -- Origin --

    def _same_origin(request):
        """False when the request says it came from a different site.

        A browser attaches Origin to every cross-site request and cannot be
        talked out of it, so an Origin naming somewhere else is proof the call
        did not come from this server's own page. No Origin means it was not a
        cross-site browser request at all: a local script has none, and a local
        script can read CLAUDE_API_KEY straight out of the environment anyway,
        so refusing it would protect nothing.

        This check is NOT turned off by --enable-cors-header. That flag exists
        so other tools can call ComfyUI, and it replaces ComfyUI's own origin
        check with headers that invite any page to send credentialed requests.
        Convenience for the server as a whole must not switch off the guard on
        a route that accepts an API key, which is the one thing here that a
        hostile page cannot already get some other way.

        Out of scope, deliberately: a direct non-browser client on an exposed
        --listen port. Nothing in ComfyUI is authenticated in that setup, so
        this route is not what is holding the door shut.

        Ports are compared the way ComfyUI compares them: when one side omits
        the port, both are compared without it, because browsers leave the
        default port out of Origin.
        """
        origin = request.headers.get("Origin")
        # Absent and present-but-empty are different things. Absent means it
        # was not a cross-site browser request. An Origin that is there but
        # names nothing cannot be matched against anything, so it is refused
        # rather than waved through.
        if origin is None:
            return True
        host = request.headers.get("Host", "")
        if not host:
            return False
        try:
            sent = urllib.parse.urlsplit(origin)
            here = urllib.parse.urlsplit("//" + host.lower())
        except ValueError:
            return False
        if sent.port is None or here.port is None:
            sent_name, here_name = sent.hostname, here.hostname
        else:
            sent_name, here_name = sent.netloc.lower(), here.netloc.lower()
        if not sent_name or not here_name:
            return False
        return sent_name == here_name

    def _foreign_origin_response():
        return web.json_response({"error": "Cross-site request refused"}, status=403)

    # -- Request helpers --

    async def _read_body(request, max_bytes):
        """The whole raw body, or None if it is bigger than max_bytes.

        The size is settled before anything is decoded. ComfyUI allows bodies
        up to a hundred megabytes by default, and decoding one of those runs
        on the event loop and stops the entire server while it happens, even
        though the request was always going to be rejected.

        Read in a loop rather than in one call. Asking the stream for N bytes
        hands back only what has arrived so far, so a single read of a
        perfectly legal body can return a fragment of it, which then fails to
        decode and reads as though nothing was sent at all. That turned a
        template larger than the connection's buffer into a complaint that the
        name was missing.
        """
        length = request.content_length
        if length is not None and length > max_bytes:
            return None
        chunks = []
        total = 0
        try:
            while True:
                chunk = await request.content.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    return None
                chunks.append(chunk)
        except Exception:
            return b""
        return b"".join(chunks)

    def _decode_object(raw):
        """A dict from JSON bytes, or an empty dict for anything else."""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    async def _json_body(request, max_bytes=MAX_ADDRESS_BODY_BYTES):
        """The posted body as a dict, or None if it was too large.

        A body that is missing, malformed, or a list instead of an object
        reads as "nothing was sent" rather than raising out of the handler.
        """
        raw = await _read_body(request, max_bytes)
        if raw is None:
            return None
        return _decode_object(raw)

    def _too_large_response():
        return web.json_response({"error": "Request is too large"}, status=413)

    def _bounded_int(raw, default, low, high):
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return min(high, max(low, value))

    def _address(source):
        """Pull a validated (id, date) out of a query or a body.

        Returns (None, None) unless both are present and well formed. A
        request carrying the old "path" field and nothing else lands here
        with nothing to read, which is the point: the old shape is refused
        outright rather than quietly accepted, so a browser still running
        the previous version's script fails visibly instead of keeping the
        old behaviour alive.
        """
        entry_id = source.get("id", "")
        date = source.get("date", "")
        if not history_manager.valid_id(entry_id):
            return None, None
        if not history_manager.valid_date(date):
            return None, None
        return entry_id, date

    # -- Template routes --

    def _create_template_exclusive(path, payload):
        """Create a template only if that name is free."""
        handle = safe_fs.open_new_exclusive(path)
        if handle is None:
            return "exists" if os.path.lexists(path) else "error"
        try:
            handle.write(payload)
        except OSError:
            handle.close()
            safe_fs.unlink_if_regular(path)
            return "error"
        handle.close()
        return "ok"

    @PromptServer.instance.routes.post("/anthropic_claude/save_template")
    @_guarded
    async def save_template(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        data = await _json_body(request, MAX_TEMPLATE_BODY_BYTES)
        if data is None:
            return _too_large_response()
        name = data.get("name", "")
        content = data.get("content", "")
        # An existing template is only replaced when the request says so.
        # A template becomes the system prompt for the user's own billed
        # calls, so silently replacing one changes what they are paying for
        # without telling them.
        overwrite = data.get("overwrite") is True
        if not isinstance(name, str) or not isinstance(content, str):
            return web.json_response({"error": "Name and content must be text"}, status=400)
        name = name.strip()
        if not name:
            return web.json_response({"error": "Name required"}, status=400)
        safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
        if not safe_name or not safe_fs.is_safe_component(safe_name + ".md"):
            return web.json_response({"error": "Invalid name"}, status=400)
        if safe_name in BUILTIN_TEMPLATES or safe_name in LEGACY_TEMPLATE_ALIASES:
            return web.json_response({"error": "Name conflicts with a built-in template"}, status=400)
        # Measured on the encoded bytes, which is what the reader limits too.
        # Counting characters instead let a template of CJK text save happily
        # at three bytes each and then read back as empty, because the reader
        # refused it.
        payload = content.encode("utf-8")
        if len(payload) > MAX_TEMPLATE_BYTES:
            return web.json_response({"error": "Template is too large"}, status=413)

        # Reaching the templates folder can mean creating it, and on a setup
        # where the input folder lives on another drive that is a disk touch
        # like any other, so it does not belong on the event loop.
        user_dir = await _offload(_get_user_templates_dir)
        if user_dir is _BUSY:
            return _busy_response()
        if user_dir is None:
            return web.json_response({"error": "Cannot reach the templates folder"}, status=500)
        path = user_dir / (safe_name + ".md")

        if overwrite:
            written = await _offload(safe_fs.write_bytes_atomic, path, payload)
            if written is _BUSY:
                return _busy_response()
            if not written:
                return web.json_response({"error": "Could not save the template"}, status=500)
        else:
            outcome = await _offload(_create_template_exclusive, path, payload)
            if outcome is _BUSY:
                return _busy_response()
            if outcome == "exists":
                return web.json_response(
                    {"error": "exists", "name": safe_name}, status=409)
            if outcome != "ok":
                return web.json_response({"error": "Could not save the template"}, status=500)
        return web.json_response({"ok": True, "name": safe_name})

    @PromptServer.instance.routes.get("/anthropic_claude/load_template")
    @_guarded
    async def load_template(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        name = request.query.get("name", "").strip()
        if not name or name == "None":
            return web.json_response({"content": ""})
        content = await _offload(_load_template, name)
        if content is _BUSY:
            return _busy_response()
        return web.json_response({"content": content})

    @PromptServer.instance.routes.get("/anthropic_claude/list_templates")
    @_guarded
    async def list_templates(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        names = await _offload(_list_all_template_names)
        if names is _BUSY:
            return _busy_response()
        # "aliases" is additive and leaves "templates" unchanged. It lets the UI resolve a
        # retired display name held in a saved workflow or a history entry to its current
        # one, using the same single hop _load_template performs server-side. Alias keys
        # are never listed in "templates".
        return web.json_response({
            "templates": names,
            "aliases": dict(LEGACY_TEMPLATE_ALIASES),
        })

    @PromptServer.instance.routes.get("/anthropic_claude/startup_warnings")
    @_guarded
    async def startup_warnings(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        # Reading the warnings no longer empties the list. Anything at all
        # could fetch this route, and whatever did so first used to be handed
        # the only copy, leaving the user with warnings they never saw. The
        # list is cleared when a model refresh actually succeeds instead.
        return web.json_response({"warnings": list(_startup_warnings)})

    @PromptServer.instance.routes.get("/anthropic_claude/api_health")
    @_guarded
    async def api_health(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        return web.json_response(_api_error)

    @PromptServer.instance.routes.post("/anthropic_claude/refresh_models")
    @_guarded
    async def refresh_models(request):
        # This route takes an API key and makes it outrank CLAUDE_API_KEY for
        # the rest of the session, which is the one thing here a hostile page
        # cannot already get by other means. See _same_origin for why the
        # check is not waived under --enable-cors-header.
        if not _same_origin(request):
            return _foreign_origin_response()
        data = await _json_body(request)
        if data is None:
            return _too_large_response()
        api_key = data.get("api_key", "")
        if not isinstance(api_key, str):
            return web.json_response({"error": "api_key must be a string"}, status=400)
        if len(api_key) > MAX_API_KEY_CHARS:
            return web.json_response({"error": "api_key is too long"}, status=400)
        # Held in a module variable for this process only. Writing it to
        # os.environ would persist it process-wide and hand it to every child
        # process ComfyUI spawns.
        # Assigned unconditionally: the session key outranks CLAUDE_API_KEY,
        # so skipping the assignment on an empty value would leave a key
        # mistyped into the error modal shadowing a working environment
        # variable with no way back short of restarting ComfyUI.
        _set_session_api_key(api_key.strip())
        display_names = await _offload(_refresh_models)
        if display_names is _BUSY:
            return _busy_response()
        return web.json_response({
            "ok": _api_error["ok"],
            "models": display_names,
            "error": _api_error,
        })

    # -- History routes --
    #
    # Entries are named by id and date. No path is ever sent to the browser
    # and none is ever accepted back, so there is no longer anything for a
    # crafted path to reach.

    @PromptServer.instance.routes.get("/anthropic_claude/history/list")
    @_guarded
    async def history_list(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        query = request.query
        search = query.get("search", "")
        date_from = query.get("date_from", "")
        date_to = query.get("date_to", "")
        sort_by = query.get("sort_by", "date_desc")
        settings = (
            _bounded_int(query.get("page", "1"), 1, 1, 1000000),
            _bounded_int(query.get("per_page", "20"), 20, 1, 200),
            search[:history_manager.MAX_SEARCH_CHARS],
            date_from if history_manager.valid_date(date_from) else "",
            date_to if history_manager.valid_date(date_to) else "",
            query.get("favorites_only", "") == "true",
            sort_by if sort_by in history_manager.SORT_KEYS else "date_desc",
        )
        key = ("list",) + settings
        result = _cached(key)
        if result is None:
            result = await _offload_shared(
                key, history_manager.list_entries,
                page=settings[0], per_page=settings[1], search=settings[2],
                date_from=settings[3], date_to=settings[4],
                favorites_only=settings[5], sort_by=settings[6],
            )
            if result is _BUSY:
                return _busy_response()
            _cache_put(key, result)
        return web.json_response(result)

    @PromptServer.instance.routes.get("/anthropic_claude/history/entry")
    @_guarded
    async def history_entry(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        entry_id, date = _address(request.query)
        if entry_id is None:
            return web.json_response({"error": "id and date required"}, status=400)
        entry = await _offload(history_manager.get_entry, entry_id, date)
        if entry is _BUSY:
            return _busy_response()
        if entry is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(entry)

    @PromptServer.instance.routes.post("/anthropic_claude/history/delete")
    @_guarded
    async def history_delete(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        body = await _json_body(request)
        if body is None:
            return _too_large_response()
        entry_id, date = _address(body)
        if entry_id is None:
            return web.json_response({"error": "id and date required"}, status=400)
        ok = await _offload(history_manager.delete_entry, entry_id, date)
        if ok is _BUSY:
            return _busy_response()
        # The store changed, so any remembered listing or totals are wrong.
        _cache_clear()
        return web.json_response({"ok": ok})

    @PromptServer.instance.routes.post("/anthropic_claude/history/favorite")
    @_guarded
    async def history_favorite(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        body = await _json_body(request)
        if body is None:
            return _too_large_response()
        entry_id, date = _address(body)
        if entry_id is None:
            return web.json_response({"error": "id and date required"}, status=400)
        new_state = await _offload(history_manager.toggle_favorite, entry_id, date)
        if new_state is _BUSY:
            return _busy_response()
        if new_state is None:
            return web.json_response({"error": "not found"}, status=404)
        _cache_clear()
        return web.json_response({"favorite": new_state})

    @PromptServer.instance.routes.get("/anthropic_claude/history/stats")
    @_guarded
    async def history_stats(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        stats = _cached(("stats",))
        if stats is None:
            stats = await _offload_shared(("stats",), history_manager.get_stats)
            if stats is _BUSY:
                return _busy_response()
            _cache_put(("stats",), stats)
        return web.json_response(stats)

    @PromptServer.instance.routes.get("/anthropic_claude/history/image")
    @_guarded
    async def history_image(request):
        if not _same_origin(request):
            return _foreign_origin_response()
        query = request.query
        entry_id, date = _address(query)
        index = query.get("index", "")
        if entry_id is None or not history_manager.valid_index(index):
            return web.Response(status=404)
        # The thumbnail's location is worked out from the entry id, and the
        # bytes are read and returned rather than the file being handed to
        # the server to open again. Only JPEGs this node wrote can ever come
        # back, and the browser is told not to guess at the type.
        data = await _offload(history_manager.read_image_bytes, entry_id, date, index)
        if data is _BUSY:
            return web.Response(status=503, headers={"Retry-After": "1"})
        if data is None:
            return web.Response(status=404)
        # Content-Type is set through the header map rather than the
        # content_type argument. aiohttp refuses both together, and the header
        # map is where the previous release put it, so the check that the type
        # is forced keeps testing the same thing.
        return web.Response(
            body=data,
            headers={
                "Content-Type": "image/jpeg",
                "X-Content-Type-Options": "nosniff",
            },
        )

except Exception:
    # Swallowed so a route problem cannot stop ComfyUI from starting, but
    # never silently: registration happens one route at a time, so a failure
    # part way through leaves some routes live and others missing, and the UI
    # then half works with nothing in the log to explain it.
    try:
        import logging as _logging
        _logging.getLogger(__name__).exception(
            "Anthropic Claude: API routes could not be registered")
    except Exception:
        pass
