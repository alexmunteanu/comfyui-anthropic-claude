# Models and templates

A template turns Claude into a prompt writer for one specific image or video model. It knows that model's prompt grammar: how it wants references tagged, whether it reads dialogue in quotes or braces, how an edit should name what changes and what stays. Pick the template for the model you will run next, type your idea in plain words, and the node returns a prompt ready to paste or wire into that model's node.

Version 1.8.0 ships 97 built-in templates. This page covers the families most people use, then the rest in short. The template dropdown always holds the complete list.

## Choosing a template

Match the exact model and version you will run. Prompting changes between versions, sometimes a lot: Seedance 2.5 accepts a 30-second, 50-reference brief that Seedance 2.0 cannot follow. When a template name lists two versions, such as "Wan 2.5 & 2.6", the versions share one documented prompt format.

Use an **Edit** template when you are changing an existing image or video. Edit templates write an instruction that names what changes and, where the model needs it, what must stay as it was. Generation templates write a full description of a new result, and pointing one at an edit job usually rebuilds the whole frame.

Some names carry a label:

| Label | Meaning |
| --- | --- |
| (Preview) | Announced or preview model. Its behavior or availability can still change. |
| (Legacy) | An older version that still runs. A newer template exists for the same family. |
| (Retiring *date*) | Runs today. The vendor has announced a shutdown on that date. |
| (Retired) | The service is gone. Selecting it returns an error instead of calling Claude. |
| (Availability varies) | Offered by some platforms and regions, not all. |

Templates never write model settings into the prompt. Duration, resolution, aspect ratio, audio on or off, and reference uploads belong in the generation node's own settings. If your brief says "make it 10 seconds", the template treats that as a timing instruction for the story, not as an API field.

## Image models

### Nano Banana (Google)

The default pick for general image work. Every Nano Banana template has a matching Edit template.

| Template | Use it for |
| --- | --- |
| Nano Banana 2.1 | Google's current main model for generation and editing. Strong with many reference images and detailed scene direction. |
| Nano Banana Pro | Professional asset work: product shots, layouts, 4K output, style references. |
| Nano Banana 2 | The previous Flash generation, with extra-wide and extra-tall ratios and a 512-pixel tier. |
| Nano Banana 2 Lite | Fast, simple 1K jobs. It does not do search grounding or multi-image fusion well, so keep briefs direct. |

### GPT Image (OpenAI)

| Template | Use it for |
| --- | --- |
| GPT Image 2.5 Flare | Fast, high-quality everyday generation. Exact on-screen text goes in quotation marks. |
| GPT Image 2.5 Sunburst Edit | Precision edits that must protect identity, layout, labels, and lighting. One material change per pass. |
| GPT Image 2 / GPT Image 2 Edit | The previous generation, still widely used. |

Repeated edits drift. The edit templates restate what must survive on every pass, but no prompt can promise pixel-identical areas, so composite the final result when an exact region matters.

### FLUX (Black Forest Labs)

**FLUX 3 Image** and **FLUX 3 Image Edit** cover the current generation. **FLUX.2** and **FLUX.2 Edit** cover the earlier one, which many local workflows still run.

### Seedream (ByteDance)

**Seedream 5.0 Pro** for top quality, **Seedream 5.0 Flash** for speed, and **Seedream 5.0 / Lite** with its Edit template. The 4.0 and 4.5 templates remain as legacy.

### Other image models

- **Qwen Image 3.0**, **2.1 & 2.1 Turbo**, and **2.0**, each with an Edit template.
- **Ideogram 4.5** for posters, labels, signs, and other text-heavy images. It writes structured JSON only when you ask for a supported layout.
- **Grok Imagine Image 2.0**, **Recraft V4 & V4.1**, **Reve 2.1**, **HunyuanImage 3.0**, **Krea 2**, and **Luma Uni-1** (with Edit and Image Layering).
- **Bria FIBO VGL** always returns one JSON object, because JSON is that model's native prompt format. **Bria FIBO** and **Bria FIBO Edit** use plain prompts.
- **P-Image** (Pruna), **Z-Image & Turbo**, **Stable Image & Stable Diffusion 3.5**, and the Topaz enhancement models **Bloom 2** and **Redefine**.

## Video models

### Seedance (ByteDance)

| Template | Use it for |
| --- | --- |
| Seedance 2.5 | Clips of 4 to 30 seconds from text, first and last frames, or up to 50 references across images, video, and audio, with native speech. |
| Seedance 2.5 Edit | Editing or extending an existing video: swap a subject, restyle, relight, remove a watermark, change the dialogue. |
| Seedance 2.0 | Clips of 4 to 15 seconds. One template covers 2.0, 2.0 Fast, and 2.0 Mini. |
| Seedance 1.5 (Retiring 2026-11-11) | Still runs until the vendor shuts it down. |
| Seedance 1.0 (Legacy) | The original model. |

Seedance 2.5 keeps your reference wording exactly as you wrote it, in any language. Write "@Image1 is the jacket" and that phrase reaches the model untouched. Give Seedance 2.5 an edit or extension brief and it replies with one line pointing you to Seedance 2.5 Edit instead of a prompt.

### Kling (Kuaishou)

| Template | Use it for |
| --- | --- |
| Kling 4.0 (Preview) | Kling's newest model, announced 2026-09-30. As of 2026-10-15 it had no public API and no ComfyUI node, so use its prompts in Kling's own app. It follows Kling's official order: subject, action, setting, camera, lighting, pacing, sound. |
| Kling 3.0 | Text and image to video with native audio, start and end frames, and multi-shot. Also covers Kling 3.0 Turbo. |
| Kling 3.0 Omni | Generation and editing with reusable elements (characters and objects built from images or video) and bound voices. |
| Kling VIDEO 3.0 Motion Control | Moving a character image with the motion of a reference video. |
| Kling Avatar 2.0 | A talking or singing performance from one image and a voiceover. |
| Kling O1, Kling 2.6 | Earlier models still in use. Kling 2.1 & 2.5 is legacy. |

Multi-shot is a setting in the Kling node, not something a prompt can switch on. The templates write labelled shots only when you say you have that mode enabled.

### Google

**Gemini Omni Flash 1.1** is Google's current video model: generation, edits, interpolation between a first and last frame, and extending a clip from its end. It writes the official reference blocks (`[# Sources ...]`, `[# References ...]`) and time ranges such as `[0-3s]` when your brief needs them. Google names it as the replacement for the Veo 3.1 preview models. Workflows saved with the earlier name "Gemini Omni Flash" open under the new one.

**Veo 3.1** covers Veo 3.1, Veo 3.1 Fast, and Veo 3.1 Lite. ComfyUI calls Google's stable Veo 3.1 versions, which are not affected by the 2026-10-22 shutdown of the preview versions. Lite has no 4K option.

### Wan and HappyHorse (Alibaba)

**Wan 3.0** (including Wan 3.0 Prime) is the current Wan release. **Wan 2.7**, **Wan 2.5 & 2.6**, and **Wan 2.1 & 2.2** cover the earlier releases, which matter if you run Wan locally.

**HappyHorse 1.0 & 1.1** handles text, image, and reference-to-video and writes multi-scene briefs with `[Image N]` references. **HappyHorse 1.0 Video Edit** changes an existing clip.

### Other video models

- **MiniMax H3** (also H3 Max and H3 Max Turbo) and **MiniMax Hailuo 2.3**.
- **Grok Imagine Video 1.5** (also Lite, reference, and extend routes) and **Grok Imagine Video Edit**.
- **Runway Gen-4.5** and **Runway Aleph 2 Edit**.
- **Luma Ray 3.2**, plus **Video Edit** and **Video Reframe**.
- **LTX 2.5**, **PixVerse V6**, **Pika 2.5**, **Vidu Q4 (Preview)**, and **Vidu Q3**.
- **FLUX 3 Video** and **FLUX Video Edit**, **HeyGen Video 1.0**, **Pruna P-Video-2**, **Higgsfield Genjutsu Motion Transfer**, **Marey Realism 1.5**, **Hunyuan Video 1.5**, and the **Topaz Astra 2** upscaler.

## Old names and retired models

Saved workflows keep working after a template is renamed. The old name resolves to its replacement when the workflow loads: "Kling V3" opens as "Kling 3.0", and "Veo 3.1 (Retiring 2026-10-22)" opens as "Veo 3.1".

A workflow also stores the template's text in its **instructions** field and runs that saved text. To pick up a template that changed in a node update, select the template again (or select **None**, then the template).

Sora 2 and Sora 2 Edit are retired, because OpenAI shut down the Sora API on 2026-09-24. They stay in the list so old workflows open, but running one returns an error asking you to choose another template.

## When no template fits

Leave the template at **None** and write your own instructions, or save your own template (see [Saving your own templates](usage.md#saving-your-own-templates)). A connected **instructions** input always wins over the template dropdown.
