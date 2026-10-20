# v1.9.1
2026-10-20

Eight templates now tag reference images, videos and audio the way each vendor documents it.

## Why
A check of every template's reference tags against the vendors' own documentation found two wrong defaults and four gaps. Seedance 2.5 wrote `@Image1`, while ByteDance's guide (updated 2026-10-16) numbers references as "Image 1 / Video 1 / Audio 1" with the `@` optional. Kling O1 and Kling 3.0 Omni gave no default tag and removed `@` tags, although ComfyUI's Kling Omni nodes send Kling's `<<<image_1>>>` form and rewrite only lowercase `@image1` into it.

## Changed
- Seedance 2.5 and Seedance 2.5 Edit: default tags are "Image 1", "Video 1", "Audio 1" ("图片 1" for a Chinese brief). First and last frames use the vendor sentence "Image 1 is the first frame." Tags you write yourself are still kept exactly.
- Kling O1 and Kling 3.0 Omni: references follow the route. ComfyUI (default): `<<<image_1>>>`, `<<<video_1>>>`. Kling's current API: `@image_1` and element names. Kling app: `@Image1`. In the first-and-last-frame node the frames count as images 1 and 2.
- Wan 2.7: reference-to-video uses "Image 1", "Video 1" with a space and a capital letter; the Wan 2.6 `character1` form is gone.
- HeyGen Video 1.0: a prompt sent straight to HeyGen's API uses its native `<Picture 1>`, `<Video 1>`, `<Audio 1>` tags; ComfyUI still uses `@Image1`.
- MiniMax H3: a prompt for MiniMax's own hosted API names references in plain words ("reference image 1"); ComfyUI keeps `<Picture N>`.
- Vidu Q3: the no-space bracket form is described as what the official examples show, not as a stated rule.
- User docs in docs/v1.9.1 explain the Seedance 2.5 and Kling Omni defaults.

## Verification
- 170 Python and 82 JavaScript tests pass on this version.
- Live Claude Sonnet 5.5 check through the shipped node: 9 of 9 cases pass on the first sample (Seedance 2.5 default tags, first and last frame, Chinese brief; Seedance 2.5 Edit; Kling 3.0 Omni through ComfyUI; Kling O1 through Kling's API; Wan 2.7; HeyGen through its API; MiniMax H3 through its API). USD 0.1635 of the approved USD 0.30.
- The oracles reject every mutation of their compliant answers, and the fake run and the paid-path dry run pass.
- Runtime: template list, load and validation 8.18 ms against v1.9.0's 8.09 ms (58.09 ms ceiling).

## Notes
- Workflows store template text in their instructions field, so the new text reaches an old workflow after the template is selected again.
- Release packaging must ship README.md, node.png and docs/ from docs/v1.9.1.

Run: 20261020-v191-reference-tags
