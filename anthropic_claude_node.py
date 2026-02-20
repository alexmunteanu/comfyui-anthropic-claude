"""
Anthropic Claude Node for ComfyUI (V3 API)
Provides a node that calls the Anthropic Claude API with text and image inputs.
© 2026 Created with ❤️ by Alex Munteanu | alexmunteanu.com
"""

import os
import hashlib
import base64
import time
from io import BytesIO
from pathlib import Path
from typing_extensions import override

import numpy as np
from PIL import Image

import folder_paths
from comfy_api.latest import ComfyExtension, io

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


BUILTIN_TEMPLATES = {
    "FLUX": "flux.md",
    "FLUX Kontext Edit": "flux_edit.md",
    "Grok": "grok.md",
    "Grok Edit": "grok_edit.md",
    "Ideogram 3": "ideogram.md",
    "Kling 2.1 & 2.5": "kling_2-1_2-5.md",
    "Kling 2.6": "kling_2-6.md",
    "Kling 2.6 Motion Control": "kling_2-6_mc.md",
    "Kling V3": "kling_v3.md",
    "Kling O1": "kling_o1.md",
    "Kling V3 Omni": "kling_o3.md",
    "LTX 2 Pro": "ltx2pro.md",
    "Luma Ray 2 & 3": "luma.md",
    "Minimax": "minimax.md",
    "Nano Banana Pro": "nano_banana_pro.md",
    "Nano Banana Pro Edit": "nano_banana_pro_edit.md",
    "Pika 2.2 & 2.5": "pika.md",
    "Qwen Image": "qwen_image.md",
    "Qwen Image Edit": "qwen_edit.md",
    "Runway Gen-4 & 4.5": "runway.md",
    "Runway Aleph Edit": "runway_edit.md",
    "Seedance 1.0 & 1.5": "seedance_1_1-5.md",
    "Seedance 2.0": "seedance_2.md",
    "Seedance 2.0 Edit": "seedance_2_edit.md",
    "Seedream 4.0 / 4.5": "seedream.md",
    "Seedream Edit": "seedream_edit.md",
    "Sora 2 & 2 Pro": "sora.md",
    "Sora 2 Edit": "sora_edit.md",
    "Veo 3 & 3.1": "veo.md",
    "Wan 2.1 & 2.2": "wan_2-1_2-2.md",
    "Wan 2.5 & 2.6": "wan_2-5_2-6.md",
}


def _get_templates_dir():
    return Path(__file__).parent / "templates"


def _get_user_templates_dir():
    user_dir = Path(folder_paths.get_input_directory()) / "comfyui_anthropic_claude" / "user_templates"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def _list_all_template_names():
    names = ["None"] + sorted(BUILTIN_TEMPLATES.keys())
    user_dir = _get_user_templates_dir()
    user_files = sorted(user_dir.glob("*.md"))
    for f in user_files:
        name = f.stem
        if name not in BUILTIN_TEMPLATES:
            names.append(name)
    return names


def _load_template(name):
    if name == "None" or not name:
        return ""
    if name in BUILTIN_TEMPLATES:
        path = _get_templates_dir() / BUILTIN_TEMPLATES[name]
    else:
        path = _get_user_templates_dir() / f"{name}.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


MODEL_PRICING = [
    ("3-haiku", 0.25, 1.25),
    ("haiku", 1.00, 5.00),
    ("3-7-sonnet", 3.00, 15.00),
    ("3-5-sonnet", 3.00, 15.00),
    ("sonnet", 3.00, 15.00),
    ("opus", 15.00, 75.00),
]


def _calculate_cost(model, input_tokens, output_tokens):
    model_lower = model.lower()
    for pattern, input_price, output_price in MODEL_PRICING:
        if pattern in model_lower:
            cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
            return cost
    return None


def _format_cost(cost):
    if cost is None:
        return "cost: unknown model"
    if cost < 0.01:
        return f"{cost * 100:.2f}\u00a2"
    return f"${cost:.4f}"


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

_display_to_id = {}
_id_to_display = {}


def _make_display_name(model_id):
    import re
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
    if display_or_id in _display_to_id:
        return _display_to_id[display_or_id]
    return display_or_id


def _fetch_models():
    global _cached_models, _models_fetch_time

    if _cached_models and (time.time() - _models_fetch_time < 3600):
        return _cached_models

    if not ANTHROPIC_AVAILABLE:
        _api_error.update(ok=False, error="The 'anthropic' package is not installed. Run: pip install anthropic", error_type="missing_package")
        return FALLBACK_MODELS

    api_key = os.environ.get("CLAUDE_API_KEY", "")
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
        _startup_warnings.append("Authentication failed: invalid API key")
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        _api_error.update(ok=False, error="Cannot reach the Anthropic API. Check your internet connection.", error_type="connection_error")
        _startup_warnings.append(f"Failed to fetch models: {e}")
    except Exception as e:
        _api_error.update(ok=False, error=f"Failed to connect to the Anthropic API: {e}", error_type="unknown")
        _startup_warnings.append(f"Failed to fetch models: {e}")

    return FALLBACK_MODELS


def _refresh_models():
    global _cached_models, _models_fetch_time
    _cached_models = None
    _models_fetch_time = 0
    model_ids = _fetch_models()
    display_names = _build_model_map(model_ids)
    return display_names


def _tensor_to_base64_images(image_tensor, max_dim=1024):
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
                "Setup: set CLAUDE_API_KEY env var. Install: pip install anthropic>=0.40.0"
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
                    default=7392041856130974,
                    min=0,
                    max=9007199254740991,
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
        model = _resolve_model(model)

        if not ANTHROPIC_AVAILABLE:
            err = "ERROR: 'anthropic' package not installed. Run: pip install anthropic"
            return io.NodeOutput(err, "", ui={"text": [err], "usage": ["N/A"], "error": [err]})

        api_key = os.environ.get("CLAUDE_API_KEY", "")
        if not api_key:
            err = "ERROR: CLAUDE_API_KEY environment variable not set."
            return io.NodeOutput(err, "", ui={"text": [err], "usage": ["N/A"], "error": [err]})

        if not prompt.strip():
            err = "ERROR: Prompt is empty."
            return io.NodeOutput(err, "", ui={"text": [err], "usage": ["N/A"], "error": [err]})

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

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }

        if instructions and instructions.strip():
            kwargs["system"] = instructions

        if extended_thinking:
            kwargs["temperature"] = 1.0
            kwargs["max_tokens"] = max_tokens + thinking_budget
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }
        else:
            kwargs["temperature"] = temperature

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
        except anthropic.APIError as e:
            api_error = f"ERROR: Anthropic API error: {e}"
        except Exception as e:
            api_error = f"ERROR: {e}"
        duration_ms = int((time.time() - t_start) * 1000)

        if api_error:
            _try_save_history(
                prompt, model, seed, template, temperature, max_tokens,
                extended_thinking, thinking_budget, max_image_size,
                "", "", 0, 0, None, "", duration_ms, api_error, images,
            )
            return io.NodeOutput(api_error, "", ui={"text": [api_error], "usage": ["N/A"], "error": [api_error]})

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
        cost_str = _format_cost(cost)

        _response_cache[cache_key] = (response_text, thinking_text, usage_str, cost_str, model)

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
