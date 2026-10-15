# Anthropic Claude for ComfyUI

Describe the shot you want in plain words, pick the model you will render with, and Claude writes the prompt in that model's own language. The node ships 97 templates for image and video models, current and earlier, including Nano Banana, GPT Image, Seedance, Kling, Veo, Wan, FLUX, and Seedream.

![The Anthropic Claude node in ComfyUI](./node.png)

## Install

Search for "Anthropic Claude" in **ComfyUI Manager** and install it, or use the Comfy Registry CLI:

```bash
comfy node install anthropic-claude
```

Restart ComfyUI and hard-refresh the browser. Manual install steps are in [Getting started](docs/getting-started.md).

## First run

1. Add **Anthropic Claude** from **LLM/Anthropic**.
2. Paste your Anthropic API key into the key field and click **Save & validate**. The node saves it on your ComfyUI machine and never writes it into workflows.
3. Pick a template, for example **Nano Banana 2.1** or **Kling 3.0**.
4. Type your idea in **prompt** and run. The finished prompt comes out of **response**, ready to wire into your image or video node.

## What it does

- **Model-specific prompt templates.** Current versions of Nano Banana, GPT Image, Seedance, Kling, Veo and Gemini Omni, Wan, FLUX, Seedream, Qwen, MiniMax, Runway, Luma, and others, with separate templates for editing.
- **Image input.** Connect images so Claude can describe a reference or plan an edit.
- **Your own templates.** Save any instructions as a template and reuse them.
- **History.** Every call to Claude is saved with its prompt, response, settings, and cost. Search it, star favorites, and restore settings in one click.
- **Cost and status.** The footer shows each run's cost and tokens, plus a live Claude API status dot.
- **Caching.** Same seed and inputs return the saved answer without a new API call.

This node writes prompts. It does not run the image or video models themselves.

## Documentation

- [Getting started](docs/getting-started.md): install, save your key, write your first prompt.
- [Models and templates](docs/models.md): which template to pick for each model and version.
- [Usage guide](docs/usage.md): every input and output, thinking, your own templates, history.
- [Troubleshooting](docs/troubleshooting.md): key status, error messages, and fixes.

## License

MIT. Dependencies keep their own licenses.

© 2026 Created with ♥ by Alex Munteanu | [alexmunteanu.com](https://alexmunteanu.com)
