# v1.11.0
2026-11-18

A new template for ByteDance Seedream 5.5.

## Why
Seedream 5.5 (Dola Seedream 5.5) is ByteDance's newest image model and the successor to Seedream 5.0 Pro. ComfyUI 0.45.0 (2026-11-10) added it as the "seedream 5.5" option of the "ByteDance Seedream 4.5, 5.0 & 5.5" node. It adds native transparent (RGBA) images, layer splits of up to 99 layers and steadier multi-turn edits.

## Added
- **Seedream 5.5**: one template for new images and for edits. BytePlus documents a single model and one prompting workflow for both.
  - Model ids: BytePlus `dola-seedream-5-5-261028`, Volcengine `doubao-seedream-5-5-261028`, ComfyUI `seedream-5-5-261028`.
  - Reference images are named Image 1, Image 2 and so on, in the order supplied (up to 10), each with its role.
  - An edit names the change, then ends with a "Preserve ..." sentence listing what stays unchanged, the form BytePlus uses. A follow-up edit carries the earlier changes into that sentence.
  - A transparent background is written into the prompt only when the brief asks for one. A glass or acrylic object is described as a material.
  - Exact in-image text goes in double quotes with its placement.
  - Size, background mode, layer count, seed and watermark stay node settings. Sequences, web search and streaming are not offered for 5.5.

## Changed
- 102 built-in templates (was 101). User docs in docs/v1.11.0 (models page and troubleshooting list).
- The global `/prompt_enhance` skill was rebuilt from this version: 96 templates and 96 `/pe-*` commands, including `/pe-seedream-5-5`.

## Verification
- 198 Python tests (7 new, each key rule with a mutation control) and 82 JavaScript tests pass on the final files.
- Live check through the shipped node on Claude Sonnet 5.5: 6 of 6 cases pass on every sample, USD 0.0655 of the approved USD 0.30. The cases were plain generation, three references, poster text, a transparent sticker, a single-image edit, and a brief that never mentions the background. One first-round miss was a checker error: "wash transparency" inside a watercolor style matched a pattern that was too broad. The pattern now targets transparent-background requests, was re-proved against its mutants, and the saved answers were re-scored with no new calls.
- Run: 20261118-124655-426dd187.

## Notes
- The Seedream 5.5 option needs ComfyUI 0.45.0 or later.
- Not checked: the template picker inside a running ComfyUI page. This version is not installed there, because installation is manual. The picker code is unchanged and lists templates from the registry the tests cover.
- Runtime was not re-measured. The change adds one entry to the template list, an effect too small to notice.
- A template audit on 2026-11-18 found 27 other templates with an out-of-date fact. They are listed in the run's stale_audit.md and are not changed in this version.
- Release packaging must ship README.md, node.png and docs/ from docs/v1.11.0.
