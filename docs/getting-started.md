# Getting Started

You need a ComfyUI install, an Anthropic API key, and about two minutes.

## 1. Install the Node

**Option A: ComfyUI Manager (recommended)**

Open ComfyUI, go to Manager, search "Anthropic Claude", click Install.

**Option B: Comfy Registry CLI**

```bash
comfy node install anthropic-claude
```

**Option C: Manual**

Clone into your `custom_nodes/` folder:

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/alexmunteanu/comfyui-anthropic-claude.git comfyui_anthropic_claude
```

Then install the Python dependency:

```bash
pip install anthropic>=0.40.0
```

If you're using ComfyUI's virtual environment, activate it first.

## 2. Set Your API Key

The node reads your key from the `CLAUDE_API_KEY` environment variable.

**Windows (permanent):**

```powershell
[System.Environment]::SetEnvironmentVariable("CLAUDE_API_KEY", "sk-ant-your-key-here", "User")
```

Restart ComfyUI after setting it.

**Linux/macOS:**

Add to your `~/.bashrc` or `~/.zshrc`:

```bash
export CLAUDE_API_KEY="sk-ant-your-key-here"
```

Then `source ~/.bashrc` and restart ComfyUI.

Get your API key at [platform.claude.com](https://platform.claude.com/).

**No restart needed?** If you forgot to set the key before starting ComfyUI (or set it wrong), the node shows an API Connection Issue modal. Paste your key directly into the modal's input field and click Retry Connection. The node picks it up immediately, no restart required.

## 3. First Run

1. Restart ComfyUI (so it picks up the new node and env var)
2. Double-click the canvas, search "Anthropic Claude"
3. Type a prompt, pick a model, run the workflow
4. The response appears on the **response** output, and cost/tokens show in the footer

The footer also shows a colored dot for the Claude API status. Green means everything's running normally. Hover over it for details.

Every execution is saved to history automatically. Click the **History** button on the node to browse past runs, search by keyword, or restore previous settings.

If the model list can't be fetched at startup (no API key, network issue), an API Connection Issue modal appears with a clear explanation and a Retry button. You can paste your API key directly in the modal to fix it without restarting.

For all inputs, templates, and advanced features, see the [Usage Guide](usage.md).
