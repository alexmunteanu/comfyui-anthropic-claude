"""
ComfyUI Anthropic Claude Node
Custom node for calling the Anthropic Claude API with text and image inputs.
© 2026 Created with ❤️ by Alex Munteanu | alexmunteanu.com
"""

VERSION = "1.4.4"

WEB_DIRECTORY = "./js"

from .anthropic_claude_node import (
    comfy_entrypoint,
    BUILTIN_TEMPLATES,
    _get_user_templates_dir,
    _load_template,
    _list_all_template_names,
    _startup_warnings,
)

from . import history_manager

try:
    from server import PromptServer
    from aiohttp import web

    # -- Template routes --

    @PromptServer.instance.routes.post("/anthropic_claude/save_template")
    async def save_template(request):
        data = await request.json()
        name = data.get("name", "").strip()
        content = data.get("content", "")
        if not name:
            return web.json_response({"error": "Name required"}, status=400)
        safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
        if not safe_name:
            return web.json_response({"error": "Invalid name"}, status=400)
        if safe_name in BUILTIN_TEMPLATES:
            return web.json_response({"error": "Name conflicts with built-in template"}, status=400)
        user_dir = _get_user_templates_dir()
        path = user_dir / f"{safe_name}.md"
        path.write_text(content, encoding="utf-8")
        return web.json_response({"ok": True, "name": safe_name})

    @PromptServer.instance.routes.get("/anthropic_claude/load_template")
    async def load_template(request):
        name = request.query.get("name", "").strip()
        if not name or name == "None":
            return web.json_response({"content": ""})
        content = _load_template(name)
        return web.json_response({"content": content})

    @PromptServer.instance.routes.get("/anthropic_claude/list_templates")
    async def list_templates(request):
        names = _list_all_template_names()
        return web.json_response({"templates": names})

    @PromptServer.instance.routes.get("/anthropic_claude/startup_warnings")
    async def startup_warnings(request):
        warnings = list(_startup_warnings)
        _startup_warnings.clear()
        return web.json_response({"warnings": warnings})

    # -- History routes --

    @PromptServer.instance.routes.get("/anthropic_claude/history/list")
    async def history_list(request):
        page = int(request.query.get("page", "1"))
        per_page = int(request.query.get("per_page", "20"))
        search = request.query.get("search", "")
        date_from = request.query.get("date_from", "")
        date_to = request.query.get("date_to", "")
        favorites_only = request.query.get("favorites_only", "") == "true"
        sort_by = request.query.get("sort_by", "date_desc")
        result = history_manager.list_entries(
            page=page, per_page=per_page, search=search,
            date_from=date_from, date_to=date_to,
            favorites_only=favorites_only, sort_by=sort_by,
        )
        return web.json_response(result)

    @PromptServer.instance.routes.get("/anthropic_claude/history/entry")
    async def history_entry(request):
        entry_path = request.query.get("path", "")
        if not entry_path:
            return web.json_response({"error": "path required"}, status=400)
        entry = history_manager.get_entry(entry_path)
        if entry is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(entry)

    @PromptServer.instance.routes.post("/anthropic_claude/history/delete")
    async def history_delete(request):
        data = await request.json()
        entry_path = data.get("path", "")
        if not entry_path:
            return web.json_response({"error": "path required"}, status=400)
        ok = history_manager.delete_entry(entry_path)
        return web.json_response({"ok": ok})

    @PromptServer.instance.routes.post("/anthropic_claude/history/favorite")
    async def history_favorite(request):
        data = await request.json()
        entry_path = data.get("path", "")
        if not entry_path:
            return web.json_response({"error": "path required"}, status=400)
        new_state = history_manager.toggle_favorite(entry_path)
        if new_state is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"favorite": new_state})

    @PromptServer.instance.routes.get("/anthropic_claude/history/stats")
    async def history_stats(request):
        stats = history_manager.get_stats()
        return web.json_response(stats)

    @PromptServer.instance.routes.get("/anthropic_claude/history/image")
    async def history_image(request):
        img_path = request.query.get("path", "")
        if not img_path:
            return web.Response(status=404)
        resolved = history_manager.resolve_image_path(img_path)
        if resolved is None:
            return web.Response(status=404)
        return web.FileResponse(resolved)

except Exception:
    pass
