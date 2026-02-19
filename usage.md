# Usage Guide

## Inputs

### prompt (required)

The text you're sending to Claude. Multiline. This is the main input.

### model (required)

Dropdown of available Claude models. The list is fetched from the Anthropic API when ComfyUI starts (cached for 1 hour). If the API is unreachable or the key isn't set, it falls back to a built-in list and shows a toast notification.

Default: Sonnet 4.5.

### seed (required)

Controls response caching. When you keep the same seed and don't change any other input, the node returns the cached response without making an API call. Change the seed (or set it to randomize) to force a new API call.

Default behavior: seed is set to "fixed" mode, so re-running the workflow reuses the cached response. Switch to "randomize" in the control widget to get a fresh response every run.

This saves money during iterative workflows where you're changing downstream nodes but not the prompt itself.

### images (optional)

Connect any ComfyUI IMAGE output here. Supports batched images (multiple frames). Each image is converted to JPEG and sent to Claude's vision API.

Images are automatically resized so neither dimension exceeds `max_image_size` (default 1024px). The resizing preserves aspect ratio.

### template (optional)

Dropdown with 31 built-in instruction templates and any user-saved templates. Selecting a template loads its content into the instructions field.

Templates come in two categories:

**Generation templates** produce rich, descriptive prompts optimized for each model's text-to-image or text-to-video pipeline. They encode the prompting style, structure, and vocabulary that the target model responds to best.

**Editing templates** produce surgical, action-based prompts for image/video editing workflows. They focus on precise modifications rather than full scene descriptions.

#### Generation Templates

| Template | Target |
|----------|--------|
| FLUX | FLUX image generation |
| Grok | Grok image generation |
| Ideogram 3 | Ideogram 3 image generation |
| Kling 2.1 & 2.5 | Kling 2.1/2.5 video generation |
| Kling 2.6 | Kling 2.6 video generation (with audio) |
| Kling 2.6 Motion Control | Kling 2.6 motion-controlled video |
| Kling V3 | Kling V3 video generation |
| Kling O1 | Kling O1 video editing |
| Kling V3 Omni | Kling V3 Omni multimodal |
| LTX 2 Pro | LTX video generation |
| Luma Ray 2 & 3 | Luma Ray 2/3 video generation |
| Minimax | Minimax video generation |
| Nano Banana Pro | Nano Banana Pro (Gemini 3 Pro Image) |
| Pika 2.2 & 2.5 | Pika video generation |
| Qwen Image | Qwen image generation |
| Runway Gen-4 & 4.5 | Runway Gen-4/4.5 video generation |
| Seedance 1.0 & 1.5 | Seedance 1.0/1.5 video generation |
| Seedance 2.0 | Seedance 2.0 video generation |
| Seedream 4.0 / 4.5 | Seedream image generation |
| Sora 2 & 2 Pro | Sora video generation |
| Veo 3 & 3.1 | Veo video generation |
| Wan 2.1 & 2.2 | Wan 2.1/2.2 video generation |
| Wan 2.5 & 2.6 | Wan 2.5/2.6 video generation |

#### Editing Templates

| Template | Target |
|----------|--------|
| FLUX Kontext Edit | FLUX Kontext image editing |
| Grok Edit | Grok image editing |
| Nano Banana Pro Edit | Nano Banana Pro image editing |
| Qwen Image Edit | Qwen image editing |
| Runway Aleph Edit | Runway Aleph video editing |
| Seedance 2.0 Edit | Seedance 2.0 video editing |
| Seedream Edit | Seedream image editing |
| Sora 2 Edit | Sora video editing |

All templates were verified against each model's official documentation.

The template dropdown is disabled when the instructions input is connected to another node (the connected value takes priority).

### instructions (optional)

System-level instructions that guide Claude's behavior. This is the `system` parameter in the API call.

Priority order:
1. If another node is connected to the instructions input, that value is used
2. If not connected, the selected template content is used
3. If template is "None" and nothing is connected, no system instructions are sent

### temperature (optional)

Controls randomness. Range: 0.0 (deterministic) to 1.0 (most creative). Default: 1.0.

When extended thinking is enabled, temperature is forced to 1.0 regardless of this setting (API requirement).

### max_tokens (optional)

Maximum tokens in Claude's response. Range: 1 to 128,000. Default: 4,096.

Higher values allow longer responses but cost more. When extended thinking is on, the actual max_tokens sent to the API is `max_tokens + thinking_budget`.

### extended_thinking (optional)

Enables Claude's chain-of-thought reasoning. When on, Claude "thinks through" the problem before responding. The thinking text appears on the second output.

Useful for complex reasoning, math, coding tasks, or anything where showing the work helps.

### thinking_budget (optional)

Maximum tokens for the thinking process. Range: 1,024 to 128,000. Default: 4,096. Only used when extended thinking is enabled.

### max_image_size (optional)

Maximum pixel dimension for image resizing. Range: 64 to 1,568. Default: 1,024.

The API limit is 1,568px. Lower values reduce token count (and cost) for image inputs. Images are resized proportionally so the largest dimension fits within this limit.

## Outputs

### response

Claude's text response. This is the main output you'll connect to other nodes or preview.

### thinking

Claude's internal reasoning when extended thinking is enabled. Empty string when extended thinking is off.

## Saving Custom Templates

1. Write your instructions in the instructions field
2. Click "Save Instructions as Template"
3. Enter a name in the dialog
4. Your template appears in the dropdown

Names that match a built-in template are rejected to prevent collisions.

User templates are saved as `.md` files in `<ComfyUI input folder>/comfyui_anthropic_claude/user_templates/`. You can also drop `.md` files there manually and click "Refresh Templates".

## History

Every execution is recorded automatically. Click the **History** button on the node to open the history modal.

### What Gets Recorded

Each entry saves: prompt, model, seed, template, temperature, max_tokens, extended thinking settings, max_image_size, the full response, thinking text, input/output token counts, USD cost, duration, error messages, and thumbnail copies of any input images.

### Stats Header

The top of the modal shows aggregate stats: total runs, total cost, total tokens, and your most-used model.

### Search and Filters

The toolbar gives you:

- **Search**: type to filter by prompt text, response text, model name, or template name
- **Date range**: From/To date pickers to narrow down by time
- **Sort**: newest first, oldest first, highest cost, or most tokens
- **Favorites**: toggle to show only starred entries

### Entry Cards

Each entry shows a single row: star button, timestamp, model name, cost, token counts, template badge (purple, if one was used), image indicator (green frame icon), and error badge (red, if the call failed). Below that, a one-line preview of the prompt and response.

### Expanding an Entry

Click any entry to expand it. The detail view shows:

- **Settings row**: seed, temperature, max tokens, thinking on/off, image size, duration. Plus a **Load Settings** button.
- **Input images**: thumbnail previews of any images that were sent with the prompt.
- **Prompt**: full text with a copy button (hover to reveal).
- **Response**: full text with a copy button.
- **Thinking**: collapsible section (click the label to expand/collapse). Only appears when extended thinking was on.
- **Error**: displayed in red if the API call failed.

### Load Settings

Click **Load Settings** on any expanded entry to restore that run's configuration to the node: prompt, model, seed, template, temperature, max_tokens, extended_thinking, thinking_budget, and max_image_size. The modal closes and the node updates immediately.

If the model from the history entry isn't available in your current model list, that field is skipped and you'll see a toast notification.

### Deleting Entries

Click the X on any entry card. A confirmation prompt appears inline ("Delete? Yes / No"). Deletion removes the JSON file and any associated image thumbnails. Empty date folders are cleaned up automatically.

### Pagination

20 entries per page. Navigation buttons at the bottom show the current page, total pages, and total entry count.

### Storage

History files are stored in `<ComfyUI input folder>/comfyui_anthropic_claude/history/`, organized by date: `YYYY/MM/DD/HHMMSS_uuid.json`.

## Node Footer

The bar at the bottom of the node shows three things at a glance:

### API Status Dot

The colored circle on the left reflects the current health of the Claude API, pulled from [status.claude.com](https://status.claude.com/) every 60 seconds.

| Color | Meaning |
|-------|---------|
| Green | Operational |
| Yellow | Degraded performance |
| Orange | Partial outage |
| Red | Major outage |
| Indigo | Under maintenance |
| Gray | Unknown (checking or unreachable) |

Hover over the dot to see the full status text in a tooltip.

This polling is shared across all Anthropic Claude nodes, so adding more nodes doesn't mean more requests. It costs nothing (hits Atlassian Statuspage, not the Anthropic API).

### Cost Display

After each execution, the cost appears in gold text (USD, formatted as dollars or cents).

Pricing is calculated from built-in rates per model family:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Haiku 3 | $0.25 | $1.25 |
| Haiku 4.5 | $1.00 | $5.00 |
| Sonnet | $3.00 | $15.00 |
| Opus | $15.00 | $75.00 |

### Token Usage

Input and output token counts, shown on the right side of the footer after each run.

## Error Display

If something goes wrong (bad API key, rate limit, empty prompt), the error message appears in red in the node footer and is also returned as the response output text.

Startup errors (like failing to fetch the model list) appear as red toast notifications in the bottom-right corner of the ComfyUI window.
