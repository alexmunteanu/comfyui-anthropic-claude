# Usage guide

Reference for every input, output, and panel on the Anthropic Claude node, version 1.9.1.

## Inputs

| Input | Default | What it does |
| --- | --- | --- |
| prompt | empty | Your request to Claude. With a template selected, describe what you want to see; the template does the prompt engineering. |
| model | newest Sonnet | The Claude model. The list comes from your Anthropic account and is cached for an hour. |
| seed | fixed number | Controls caching. The same seed with unchanged inputs returns the saved answer without a new API call. The cache keeps the last 64 answers until ComfyUI restarts. |
| images | none | Optional IMAGE input, batches included. Claude sees each image, so it can describe a reference or plan an edit. |
| template | None | A built-in or saved prompt template. See [Models and templates](models.md). |
| instructions | empty | The system prompt Claude follows. Choosing a template fills this field with the template's text. |
| temperature | 1.0 | Randomness, from 0.0 to 1.0. Applies only to Claude 4.6 and older models, and only with extended_thinking off. |
| max_tokens | 4,096 | The longest response allowed, from 1 to 128,000. |
| extended_thinking | off | Lets Claude reason before answering and returns a summary of that reasoning. |
| thinking_budget | 4,096 | How much thinking to allow, from 1,024 to 128,000. Only used when extended_thinking is on. |
| max_image_size | 1,024 | The longest side, in pixels, of each image sent to Claude. From 64 to 1,568. |

### Model

The default is the newest Sonnet your account can use, which is the right speed and cost for prompt writing. Opus and Fable models reason harder and cost more; Haiku is the cheapest. If the model list cannot load at startup, the node falls back to a built-in list of 14 current models. The key status line under the key field shows why.

### Images

Every connected image goes to Claude as a JPEG, shrunk so its longest side fits **max_image_size**. Smaller images cost fewer tokens: 512 pixels uses roughly a quarter of the tokens of 1,024. The API scales anything larger than 1,568 pixels down anyway, which is why the setting stops there.

### Extended thinking

How thinking works depends on the model:

- **Claude 4.6 and newer** (including all 5.x, Fable, and Mythos models) think adaptively. The thinking budget sets the effort level: up to 8,192 is low, up to 32,768 is medium, and anything higher is high. Thinking uses part of max_tokens on these models, so raise max_tokens when you choose medium or high effort, or the answer can stop early.
- **Claude 4.5 and older** use a fixed thinking budget. That budget is added to max_tokens, so the request allows both.

Some newer models think on their own even with the switch off; they keep that reasoning hidden. Turning the switch on shows a summary on the **thinking** output, sets the effort level on adaptive models, and adds cost.

For models with a known output limit, the node checks the request before sending it. A request that would exceed the limit fails straight away and names the number it needed, so you never pay for a call the API would reject.

## Templates and instructions

The node decides what Claude follows in this order:

1. Text in the **instructions** field, or a node connected to the instructions input.
2. Otherwise, the selected **template**.
3. Otherwise, no system prompt at all.

Selecting a template copies its text into **instructions**, so you can read it and edit it for one run. Your edit applies to that node only and leaves the template file alone. Select **None** to clear the field.

### Saving your own templates

1. Write or edit the text in **instructions**.
2. Click **Save Instructions as Template** and give it a name.
3. The template appears in the dropdown.

Saved templates are Markdown files in `<ComfyUI input folder>/comfyui_anthropic_claude/user_templates/`. You can also copy `.md` files into that folder and click **Refresh Templates**. Names keep letters, digits, spaces, `_` and `-`; other punctuation is dropped, so "My v2.1 (draft)" saves as "My v21 draft". Names that match a built-in template are refused, because the built-in would hide your file.

A workflow keeps the template text it was saved with. After a node update, select the template again to load its new version.

## Outputs

| Output | Contains |
| --- | --- |
| response | Claude's answer. With a template, this is the finished prompt for your image or video model. On failure it carries the error text. |
| thinking | The reasoning summary when extended thinking is on. Empty otherwise. |

## Where your key is stored

The key is saved on the machine running ComfyUI, in `.anthropic_claude/api_key` inside the node's folder. It loads and is checked automatically at startup. Environment variables are not used.

The key never enters workflows, API prompts, copied nodes, browser storage, or history, so sharing a workflow file is safe. The file itself is plain text, so:

- Keep that folder readable only by the account that runs ComfyUI.
- Leave `.anthropic_claude/` out when you zip or share your ComfyUI folder.
- When you update the node by hand, copy `.anthropic_claude/` into the new folder, or enter the key again.

To replace the key, paste a new one and click **Save & validate**. If the new key fails, the old one keeps working.

## History

Every call to Claude is saved automatically, failed calls included. Cached repeats, and errors caught before a call (such as an empty prompt), are not saved. Click **History** on the node to browse.

Each entry records the prompt, model, seed, template, settings, response, thinking, token counts, cost, duration, any error, and small thumbnails of the input images. The top of the panel totals your runs, cost, and tokens, and names your most-used model.

- **Search** matches prompt text, response text, model, and template.
- **From** and **To** narrow the date range.
- **Sort** by newest, oldest, highest cost, or most tokens.
- The **star** marks favorites, and the favorites filter shows only those.
- Click an entry to see everything, including copy buttons for the prompt and the response.
- **Load Settings** puts that run's prompt, model, seed, template, and settings back on the node. A renamed template maps to its new name. A model or template that no longer exists is skipped, and a notice says so.
- The **X** deletes an entry and its thumbnails, after you confirm.

History lives in `<ComfyUI input folder>/comfyui_anthropic_claude/history/`, one JSON file per run, organized by date. Twenty entries show per page.

## Footer

The strip at the bottom of the node shows the latest run.

- **Status dot**: the health of the Claude API, read from [status.claude.com](https://status.claude.com/) every minute. Green is operational; yellow, orange, and red mean degraded, partial outage, and major outage; indigo is maintenance; gray means the status page could not be reached. Hover for the full text. All nodes share one check.
- **Cost**: in dollars, or cents under one cent. The node has exact prices for the 14 models in its built-in list and for older Claude models. A newer model it does not know gets a family-rate estimate marked `~` and `(est.)`. A cached repeat costs nothing, but the footer shows the first run's cost and tokens again.
- **Tokens**: input and output counts.

Errors show in red in the footer as well as on the response output. A failed run shows no cost.
