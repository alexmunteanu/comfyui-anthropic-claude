# Troubleshooting

Find the message you see, then follow the fix under it.

## Key status messages

The line under the key field on the node shows the state of your saved key.

| Status | Meaning | Fix |
| --- | --- | --- |
| Key: Checking... | The node is checking the saved key with Anthropic. | Wait a moment. |
| Key: Ready | The key works. | Nothing to do. |
| Key: Not set | No key is saved. | Paste your key and click **Save & validate**. |
| Key: Invalid | Anthropic rejected the key. | Paste the full key from [platform.claude.com](https://platform.claude.com/) and save again. |
| Key: Unavailable | Anthropic could not be reached to check the key. | Check your connection or [status.claude.com](https://status.claude.com/). The saved key is kept. |
| Key: Save failed | The key was valid but could not be written to disk. | Make sure the account running ComfyUI can write to the node's folder. |

Anthropic keys start with `sk-ant-`. Copy the whole key with no spaces before or after it.

## "ERROR: Add and validate an Anthropic API key on the node."

No key is active. Look at the status line under the key field:

- **Key: Not set.** Enter your key in the **Anthropic API key** field and click **Save & validate**.
- **Key: Unavailable.** Your key is saved, but Anthropic could not be reached to check it when ComfyUI started, and runs do not retry that check. Click **Retry Connection** in the window that opened, or click **Save & validate** again.
- **Key: Invalid** or **Key: Save failed.** The saved key cannot be used. Save a working key with **Save & validate**; for Save failed, also see the key status table above.

If you used the `CLAUDE_API_KEY` environment variable with versions before 1.7.0: the node no longer reads it. Save the key on the node once and it loads automatically from then on.

## The key disappeared after an update

The key lives in `.anthropic_claude/` inside the node's folder. Replacing that folder by hand removes the key with it. Copy `.anthropic_claude/` from the old folder into the new one, or enter the key again.

## API Connection Issue window

This window opens after a run fails because the saved key was rejected, no working key is active, or Anthropic is rate limiting. Problems at startup show only on the key status line, not in a window.

**Retry Connection** checks the saved key again and reloads the model list, without restarting ComfyUI. If the retry fails, the window shows the new cause:

- **The saved Anthropic API key is invalid.** Save a working key on the node.
- **Add and validate an Anthropic API key on the node.** No key is saved yet; see that error's entry above.
- **The saved Anthropic API key cannot list models.** The key lacks permission for the model list. Check it on [platform.claude.com](https://platform.claude.com/), then save it again.
- **The saved API key file is not valid** or **could not be read.** Save your key again on the node.
- **Could not connect to the Anthropic API.** Another connection failure. Check your network and [status.claude.com](https://status.claude.com/), then retry.
- **The 'anthropic' package is not installed.** See the next section.
- **Anthropic is temporarily unavailable**, **is rate limiting requests**, or **the model catalogue is unavailable.** Wait, then click **Retry Connection** again. Runs work again once the key check succeeds.

**Dismiss** closes the window.

## "ERROR: 'anthropic' package not installed"

The Anthropic Python package is missing from the Python that runs ComfyUI. Install it with that same Python, then restart ComfyUI:

```bash
python -m pip install "anthropic>=0.122.0"
```

On a portable or virtual-environment install, call its Python directly, for example `ComfyUI\.venv\Scripts\python.exe -m pip install "anthropic>=0.122.0"` on Windows.

## "ERROR: Rate limited by Anthropic API. Wait and retry."

Your account hit Anthropic's rate limit. Wait a minute and run again. If it keeps happening, check your usage and limits on [platform.claude.com](https://platform.claude.com/).

## "ERROR: Template '...' is retired."

The template targets a service that no longer exists, such as Sora 2. Pick a current template; [Models and templates](models.md) lists them.

## "ERROR: Template '...' could not be loaded"

The template file is missing, unreadable, or empty. Click **Refresh Templates** and select the template again. If it is one of your own, check that its `.md` file is still in the user templates folder.

## An old workflow shows a different template name

A renamed template opened under its new name, for example "Veo 3.1 (Retiring 2026-10-22)" now opens as "Veo 3.1", and "GPT Image 2.5 Sunburst Edit" as "GPT Image 2.5 Edit".

## Template updates do not change an old workflow's results

A workflow stores the template text in its **instructions** field when you select a template, and it runs that saved text. Templates updated in a new version of the node, such as the Seedance 2.5 and Kling Omni templates in 1.9.1, reach the workflow only after you select the template again. If the dropdown already shows the right template, select **None**, then the template.

## "ERROR: Prompt is empty."

Type a request in **prompt**.

## "ERROR: This model supports at most ... total output tokens"

The request asks for more output than the model allows. Lower **max_tokens**, or **thinking_budget** if thinking is on.

## "ERROR: Anthropic API error: ..."

Anthropic refused the request. The text after the colon says why, for example a model your account cannot use or a setting that model does not accept. Pick another model or change that setting.

## "Name conflicts with a built-in template"

Your template's name matches a built-in one. Choose another name. Version 1.9.0 adds the built-in names "GPT Image 2.5" and "GPT Image 2.5 Edit". A saved template of yours with exactly one of those names is now hidden by the built-in; rename your `.md` file to bring it back.

## The model list is short or its names look different

The node could not load your account's model list at startup and fell back to its built-in list of 14 models, with names built from their IDs. Fix the key or connection, then click **Retry Connection** or restart ComfyUI.

## The cost shows "~" and "(est.)", or "cost: unknown model"

The node has no exact price for that model, so it estimates from the model family's rate, or shows no price at all. Your actual bill comes from Anthropic, not from the node.

## The status dot stays gray

The node cannot reach [status.claude.com](https://status.claude.com/), often because of a firewall or proxy. The dot is information only; the node works the same either way.

## The thinking output is empty

Extended thinking is off. Turn on **extended_thinking** to receive a reasoning summary. With it on, a short request at low effort can still return no summary; raise **thinking_budget** above 8,192 for medium effort.

## The node does not appear after install

1. Check that the folder is `ComfyUI/custom_nodes/comfyui_anthropic_claude` and contains `__init__.py`.
2. Read the ComfyUI console at startup for import errors, most often the missing `anthropic` package.
3. Update ComfyUI. The node uses the V3 node API.
4. Hard-refresh the browser tab so the node's interface loads.
