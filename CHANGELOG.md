# v1.9.0
2026-10-16

GPT Image 2.5 now has one generation template and one edit template, and each works with both Flare and Sunburst.

## Why
The node offered only "GPT Image 2.5 Flare" for new images and "GPT Image 2.5 Sunburst Edit" for edits, which implied each model could do only one job. OpenAI's model pages list image generation and image editing for both gpt-image-2.5-flare and gpt-image-2.5-sunburst. Its prompting guide gives one method for both models, and ComfyUI's OpenAI GPT Image 2.5 node gives them identical inputs. The earlier split came from OpenAI's "best for" advice (Flare for fast everyday generation, Sunburst when editing precision matters most), not from a limit.

## Changed
- "GPT Image 2.5 Flare" is now "GPT Image 2.5": new images with either model. It follows OpenAI's guide: labeled sections for complex briefs, explicit photorealism, people framing, quoted text with letter-by-letter spelling for unusual words, numbered reference roles.
- "GPT Image 2.5 Sunburst Edit" is now "GPT Image 2.5 Edit": edits with either model, including masked edits (masking is prompt-based; in ComfyUI a mask needs exactly one reference image) and up to 16 reference images. Existing logos and labels stay protected; no new text, logos or watermarks are added unless asked.
- The old names keep working: saved workflows, API prompts and history entries open them as the new templates (97 builtins, 39 aliases).
- GPT Image 2 templates point to the new names.
- User docs in docs/v1.9.0 explain the choice of model on the OpenAI node.

## Verification
- 170 Python and 82 JavaScript tests pass, including new contract tests with mutation checks for both templates and the two old names.
- Live Claude Sonnet 5.5 check through the shipped node: 9 of 9 cases pass on the first sample (poster text, two-reference composite, single edit, masked edit, logo kept, transparent background, simple brief, both old names). USD 0.1285 of the approved USD 0.30.
- An isolated ComfyUI host with this exact source passed the journey: picker lists the two new names only, selecting the edit template loads its text, saved workflows and an API prompt with the old names run, a misspelled name is rejected, history restore lands on the new name.
- Independent review is clean after one repair round.
- Runtime: template list, load and validation 7.10 ms against v1.8.0's 7.11 ms (50 ms ceiling).

## Notes
- Workflows store template text in their instructions field, so the new text reaches an old workflow after the template is selected again.
- A user template file named exactly "GPT Image 2.5" or "GPT Image 2.5 Edit" is now hidden behind the builtin; rename the file to keep it.
- Release packaging must ship README.md, node.png and docs/ from docs/v1.9.0.

Run: 20261016-010138-gpt25-pair
