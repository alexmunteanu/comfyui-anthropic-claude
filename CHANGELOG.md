# v1.7.0
2026-10-15

Package-local API-key entry and persistence.

## Changed
- Added a masked, nonserializing key control with explicit Save & validate. Credentials stay outside workflows, prompts, cloned/copied nodes, browser storage and history.
- Validate through Models with a fixed official endpoint and bounded retries/timeouts, then atomically store the key at <running-package>/.anthropic_claude/api_key. Automatically validate the saved key after restart. Removed environment-key fallback.
- Preserve the working credential and caches on invalid replacement, provider outage or storage failure. Bound concurrent saves and keep status responsive through coalesced background bootstrap.
- Pin final outgoing authentication headers and isolate response caches by credential generation with typed, length-prefixed fields.
- Added Git/Comfy archive exclusions for the credential directory. Preserved all 89 templates, examples, V3 registration and frozen predecessor source.

## Verification
- 320 Python passes: 277 inherited plus 43 current contract tests. 57 JavaScript passes. 517 source-artifact checks.
- Both real hidden ComfyUI first-run/restart journeys pass 15 steps, including actual copy/paste, serialization checks, execution/history, failed replacements and autoload. No credential leaks or runtime exceptions were observed. Independent source/security/visual reviews pass.
- Local workload median 9.2804ms versus predecessor 8.5941ms, below paired 58.5941ms and immutable 59.2243ms ceilings.
- Six inherited missing-real-store fixture skips and one documented Windows share-delete expected failure remain explicit. Installed SDK 0.75.0 was exercised; SDK 0.122.0 was source-reviewed; the declared >=0.122.0 range was not executed.

## Registry and limits
The public v1.5.25 Registry flag points to the removed environment-key read. A newly published archive must still pass scanning; acceptance is not automatic.

The saved file is plaintext on the server machine. Ignore rules prevent managed Git/Comfy archive inclusion; arbitrary whole-folder copies can still include it. No paid requests, installation or publication were made for this task.

Evidence: .claude/runs/20261015-154345-local-key/.
