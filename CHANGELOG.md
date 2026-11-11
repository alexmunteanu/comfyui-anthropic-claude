# v1.10.0
2026-11-11

Four new templates for OpenAI GPT Image 2.6, released 2026-11-04.

## Why
GPT Image 2.6 adds markup-guided edits, a planning "complexity" setting, animated GIF output and SVG output. ComfyUI 0.45.0 ships an "OpenAI GPT Image 2.6" node plus separate GIF and SVG nodes, and OpenAI's guide gives GIF and SVG their own prompting rules.

## Added
- **GPT Image 2.6**: new still images with gpt-image-2.6-flare or gpt-image-2.6-sunburst (one prompting method, so one template serves both).
- **GPT Image 2.6 Edit**: edits, including markup edits. When the brief says a mark is drawn on the first image, the prompt names the object through that mark ("the vase inside the red circle") and asks for the mark to be removed from the result. Without markup, no mark is mentioned. Markup and a mask are never combined.
- **GPT Image 2.6 GIF**: short animations. By default the motion starts from a pose, returns to it and ends with "Make the motion loop smoothly."; a brief that asks for a one-shot gets its final state instead. Frame count, frame length and size stay node settings.
- **GPT Image 2.6 SVG**: logos, icons and simple graphics in OpenAI's vector wording (clean, vector-like shapes, a strong silhouette, balanced negative space, flat design, no gradients unless essential).

## Changed
- GPT Image 2.5 Edit: the same markup rules (OpenAI documents markup for 2.5, and the ComfyUI 2.6 node offers it for the 2.5 models).
- GPT Image 2.5, 2.5 Edit, 2 and 2 Edit: point to the 2.6 templates; the renamed "OpenAI GPT Image 2.5" node is no longer named.
- 101 built-in templates (was 97). User docs in docs/v1.10.0.

## Verification
- 191 Python tests (21 new, each key rule with a mutation control) and 82 JavaScript tests pass.
- Live Claude Sonnet 5.5 check through the shipped node: 9 of 9 cases pass on every sample (two per new template, a markup and a no-markup edit, a loop and a one-shot GIF, plus a GPT Image 2.5 Edit markup case). USD 0.1131 of the approved USD 0.30. Two first-round misses were checker errors (a paraphrased return-to-start; a correct flat-facet translation of "texture"); the checkers were corrected, re-proved against their mutants and the saved answers re-scored with no new calls.
- Runtime: template list, load and validation 7.18 ms against v1.9.1's 6.56 ms (56.56 ms ceiling).

## Notes
- The GPT Image 2.6 nodes need ComfyUI 0.44.1 or later.
- Not checked: the template picker inside a running ComfyUI page (this version is not installed there; installation is manual). The picker code is unchanged and lists templates from the registry the tests cover.
- Workflows store template text in their instructions field, so updated 2.5 text reaches an old workflow after the template is selected again.
- Release packaging must ship README.md, node.png and docs/ from docs/v1.10.0.

Run: 20261111-130918-a82eab53
