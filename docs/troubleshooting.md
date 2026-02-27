# Troubleshooting

## API Connection Issue modal appears

When the node can't connect to the Anthropic API at startup, a modal appears with the specific error (missing key, invalid key, network issue). You have two options:

1. **Paste your key and retry**: type or paste your API key into the input field in the modal, then click Retry Connection. If it works, the modal closes, models refresh, and you're good to go.
2. **Dismiss**: close the modal and continue with the fallback model list.

This modal also appears during execution if the API call fails with an authentication error.

## "CLAUDE_API_KEY environment variable not set"

The node can't find your API key.

**Fix**: Set the `CLAUDE_API_KEY` environment variable and restart ComfyUI. See [Getting Started](getting-started.md#2-set-your-api-key) for instructions per OS.

You can also paste the key directly into the API Connection Issue modal without restarting.

Make sure you restart ComfyUI after setting the variable. Environment variables set in a terminal only apply to processes started from that terminal.

## "'anthropic' package not installed"

The Python SDK isn't installed in ComfyUI's Python environment.

**Fix**:

```bash
pip install anthropic>=0.40.0
```

If ComfyUI uses a virtual environment (common with portable installs), activate it first:

```bash
# Windows (ComfyUI portable)
ComfyUI\.venv\Scripts\activate
pip install anthropic>=0.40.0
```

## "Invalid API key"

Your key is set but Anthropic rejected it.

**Fix**: Check for typos. Keys start with `sk-ant-`. Make sure you copied the full key without trailing spaces. On Windows, use right-click paste instead of Ctrl+V (Ctrl+V can append invisible characters in some terminals).

You can also paste a corrected key into the API Connection Issue modal and click Retry Connection.

## "Rate limited by Anthropic API"

You've hit Anthropic's rate limits.

**Fix**: Wait a minute and try again. If this happens frequently, check your [API usage dashboard](https://console.anthropic.com/) for rate limit tiers.

## Status dot is gray and stays gray

The gray dot means the node can't reach [status.claude.com](https://status.claude.com/) to check API health. This is purely cosmetic and doesn't affect the node's functionality.

**Common causes**:

- Firewall or proxy blocking outbound requests to `status.claude.com`
- Corporate network restrictions
- status.claude.com itself is down (rare)

**Fix**: Check if you can open `https://status.claude.com` in your browser. If your network blocks it, the dot will stay gray. The node works exactly the same either way.

## Model dropdown shows generic names

If the API key isn't set or the Anthropic API is unreachable at startup, the dropdown falls back to a hardcoded list. The node still works, just with a shorter model list.

**Fix**: Set your API key and restart ComfyUI, or paste it in the API Connection Issue modal and click Retry Connection.

## "Name conflicts with built-in template"

You tried to save a user template with a name that matches one of the 33 built-in templates.

**Fix**: Choose a different name. Built-in template names are reserved to prevent user files from being hidden by the collision.

## Templates not showing up

User-saved templates are `.md` files in `<ComfyUI input folder>/comfyui_anthropic_claude/user_templates/`. If they're not appearing:

1. Click the "Refresh Templates" button on the node
2. Check that the files are `.md` format (not `.txt`)
3. Verify the folder path exists

## High cost for image inputs

Each image is converted to JPEG and sent as base64. Larger images use more tokens.

**Fix**: Lower the `max_image_size` input. Default is 1024px. Going to 512px roughly quarters the token count per image.

## Extended thinking returns empty

The thinking output is only populated when `extended_thinking` is enabled. If it's off, the output is an empty string. This is normal.

## Node not found after install

If ComfyUI can't find the node:

1. Check that the folder is named `comfyui_anthropic_claude` inside `custom_nodes/`
2. Verify `__init__.py` exists in the folder
3. Check the ComfyUI console for import errors at startup
4. Make sure you're running a ComfyUI version that supports V3 nodes (2025+)
