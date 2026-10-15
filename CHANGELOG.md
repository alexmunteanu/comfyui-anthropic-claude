# v1.8.0
2026-10-15

Newest video model templates, corrected video templates, working legacy names in saved workflows, and rewritten user documentation.

## Why
A model refresh did not find Kling 4. Research on 2026-10-15 showed why: Kling announced Kling 4.0 on 2026-09-30 with early access in its own app, but no public API model ID or ComfyUI node exists yet. The same research found seven video models that ComfyUI v0.40.0 runs with no template here, and several existing video templates that contradicted current releases.

## Added
- Kling 4.0 (Preview), built from Kling's official prompt guidance (Subject + Action + Setting + Camera + Lighting + Pacing + Sound). It keeps release status out of generated prompts.
- HappyHorse 1.0 & 1.1, HappyHorse 1.0 Video Edit, Vidu Q4 (Preview), FLUX Video Edit, HeyGen Video 1.0, Pruna P-Video-2 and Higgsfield Genjutsu Motion Transfer.

## Changed
- Kling 3.0 now covers Kling 3.0 Turbo and 4K; it previously ruled Turbo out.
- "Veo 3.1 (Retiring 2026-10-22)" is now "Veo 3.1". Only Google's preview IDs shut down on that date; ComfyUI uses the GA -001 IDs, including Lite (no 4K).
- "Gemini Omni Flash" is now "Gemini Omni Flash 1.1", with Google's GA reference syntax ([# Sources ...], [# References ...], [0-3s] time ranges). It remains Google's newest video model on 2026-10-15.
- MiniMax H3 covers H3 Max and Max Turbo, and cites identity images as bracketed <Picture N> inside their <Subject N>, as the official guide requires. Luma Ray 3.2 covers Extend; Grok covers its reference and extend routes per model.
- Old names keep working through one-hop aliases (97 builtins, 37 aliases).
- User docs rewritten in docs/v1.8.0 (README, getting started, models and templates, usage, troubleshooting) around Nano Banana, GPT Image, Seedance and Kling, with a fresh node screenshot.

## Fixed
- Saved workflows that use a renamed template failed with "Invalid input" before the node ran, for every rename since v1.5.22. The node now remaps the name when a workflow opens and accepts legacy names in validation.
- The response cache identified an image only by its size and first 4096 bytes, so two images sharing a top region could return each other's answer. The key now hashes the whole image, and an empty batch no longer fails.
- After a failed run the footer showed the previous run's cost; it now shows none.
- Retry Connection now names the real key problem (no key, no model permission, unreadable or invalid key file) instead of a generic connection message.

## Verification
- 151 Python and 77 JavaScript tests pass, including manifest, sentinel and mutation checks for every new and changed template.
- 30 live Claude Sonnet 5.5 cases pass with every sample passing: 67 calls, USD 0.4628 of the approved USD 1.50. Every scoring rule changed after seeing outputs was audited independently; the audit exposed and fixed two template defects (HappyHorse edit scene listing, MiniMax identity labels).
- An isolated ComfyUI 0.39.1 host, staged byte-identical to this source, passed the full journey: picker, Kling 4.0 and HappyHorse runs, legacy names from saved workflows and the API, history restore, footer error state, missing-key retry text and the image cache.
- Independent code review and security review are clean.
- Runtime: template list and load 7.24 ms against v1.7.0's 6.62 ms; image cache key 19.0 ms for a 4 x 1024 x 1024 batch. Both are within the 50 ms regression ceiling.

## Notes
- A user template file named exactly like a new builtin (for example "FLUX Video Edit") is now hidden behind the builtin; rename the file to keep it.
- Workflows store template text in their instructions field, so template updates reach an old workflow after the template is selected again.
- Release packaging must ship README.md, node.png and docs/ from docs/v1.8.0.

Run: 20261015-174712-1287d825
