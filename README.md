# Anthropic Claude

A ComfyUI V3 node for optimizing image and video prompts, with 89 built-in templates, text and image inputs, model discovery and execution history.

## Installation

1. Copy this package to `ComfyUI/custom_nodes/comfyui_anthropic_claude/`.
2. In ComfyUI's Python environment, run `python -m pip install -r requirements.txt`.
3. Restart ComfyUI and hard-refresh the browser.
4. Add **Anthropic Claude** from **LLM/Anthropic**.
5. Enter your Anthropic API key in the masked field and select **Save & validate**.

An importable example is in `examples/basic_workflow.json`. ComfyUI supplies the V3 API, Pillow, numpy and its other runtime dependencies.

## Key storage

The validated key is saved only on the ComfyUI server machine at `.anthropic_claude/api_key` inside this package. It is checked and loaded automatically after restart. Environment variables are not used for API-key configuration.

The key is excluded from workflows, API prompts, node copies, browser storage and history. Failed replacement preserves the working key. The saved file is plaintext: restrict access to the server account and exclude `.anthropic_claude/` when manually sharing or backing up an installation. Git and Comfy archive ignore files exclude that directory.

When updating, preserve your existing local credential directory separately and restore it into the new running package. Never add it to a release archive.

## Use

Choose a model and template, enter your creative request, optionally connect images, and run the node. Templates include current Nano Banana, Ideogram, Pruna, Luma and Topaz targets. Historical names resolve through compatibility aliases; retired Sora selections report an error.

This is a prompt-generation node. It does not install or execute the target image and video models.

## License

MIT. Dependencies retain their own licenses.

© 2026 Created with ♥ by Alex Munteanu | [alexmunteanu.com](https://alexmunteanu.com)
