# Getting started

By the end of this page you will have the node installed, your Anthropic API key saved, and a finished Nano Banana prompt on screen. You need a working ComfyUI and an Anthropic API key from [platform.claude.com](https://platform.claude.com/).

## 1. Install the node

The quickest route is **ComfyUI Manager**: open it, search for "Anthropic Claude", and install. The Comfy Registry CLI does the same thing:

```bash
comfy node install anthropic-claude
```

To install by hand, clone the repository into `custom_nodes` and install the one Python dependency with the Python that runs ComfyUI:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/alexmunteanu/comfyui-anthropic-claude.git comfyui_anthropic_claude
python -m pip install -r comfyui_anthropic_claude/requirements.txt
```

If your ComfyUI uses a virtual environment or a portable build, run that last command with its Python, for example `ComfyUI\.venv\Scripts\python.exe -m pip install ...` on Windows.

Restart ComfyUI, then hard-refresh the browser tab (Ctrl+Shift+R, or Cmd+Shift+R on macOS) so the node's interface loads fresh.

## 2. Add the node and save your key

1. Double-click the canvas, search for **Anthropic Claude**, and add it. It lives under **LLM/Anthropic**.
2. Paste your key (it starts with `sk-ant-`) into the **Anthropic API key** field on the node.
3. Click **Save & validate**.

The status line under the field reads **Key: Ready** when the key works. The node checks the key with Anthropic before saving it, so a typo never replaces a working key.

You do this once. The key stays on the machine running ComfyUI and loads automatically after every restart. It is never written into workflows, history, or anything you share. [Where your key is stored](usage.md#where-your-key-is-stored) has the details.

## 3. Write your first prompt

1. Set **template** to **Nano Banana 2.1**.
2. In **prompt**, write the idea in plain words:

   ```text
   a ceramic coffee cup on a rainy cafe windowsill, morning light, cozy
   ```

3. Leave **model** on its default, the newest Sonnet.
4. Queue the workflow.

The finished Nano Banana prompt appears on the **response** output. Connect it to a **Preview Any** node to read it, or straight into your image node's prompt input. The footer under the node shows what the run cost and how many tokens it used.

Run it again without changing anything and the answer comes back instantly at no cost; the footer repeats the first run's cost and tokens. The node caches each result by seed and inputs. Change the seed, or click **Randomize Seed**, when you want a fresh take.

## Next steps

- [Models and templates](models.md): which of the 97 templates to pick for Kling, Seedance, GPT Image, Veo, and the rest.
- [Usage guide](usage.md): every input, images, thinking, your own templates, and history.
- [Troubleshooting](troubleshooting.md): what the key status and error messages mean.
