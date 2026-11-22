# KEIRIN INSIGHT — Public-release evidence exposure audit
Audit date (JST): 2026-11-22. GitHub repository reads only; live GitHub Pages fetch and actual deployment status not confirmed.

## Actual repository inspection

| Root-level asset | Records | Literal https URL occurrences | Notes |
| --- | ---: | ---: | --- |
| verified-rider-ids-feed-v1.json | 93 rider identities | 378 | Internal provider evidence URLs appear in source, two-site verification metadata and notes. |
| comparison-races-v1.json | 6 research-only races | 36 | Result, forecast, and per-race provenance source links are present; some URLs repeated in text. |
| verified-results-feed-v1.json | 0 formally published results | 0 | Empty formally verified result index. |

Literal URL counts are string-occurrence counts, **not** counts of unique links, independent sources or violations.

## Public-facing page review

- `race-index-live.html` and `race-result-detail.html` currently have no hard-coded third-party provider brand names identified by the targeted string scan.
- Both currently invoke the shared version 13.8 official publication guard. A code read is not a complete rendered-browser security audit.
- Public HTML brand omission **does not protect** metadata in root-level JSON served as static site assets. Do not describe these JSON source details as confidential solely because the HTML UI hides them.
- Source URLs, provider identity, original wording, timestamps and evidence must remain traceable for legitimate independent comparison and possible attribution.

## Release blockers / prioritized engineering path

1. Determine whether the repository and associated static JSON URL paths are publicly retrievable. Verify GitHub Pages deployment, access scope and distribution obligations with a real browser.
2. Before a general-public launch, split **internal receipt/evidence ledger** from a **minimal public data representation**. Never put restricted evidence in a publicly served static folder; file renaming or moving under `tools/` in the same public repo does not itself make data private.
3. Implement separate server-side or controlled validation and signed/generated public-only output as appropriate. The current browser-side `verified-publication-guard-v138.js` requires original profile source URLs for two-provider validation, so simply deleting those fields would break the current guard and weaken provenance. Design and test the replacement validator first.
4. Confirm source licenses, legally required attribution, permitted reuse and original-analysis/no-copy requirements; hiding provider names alone is not permission.
5. Verify user-facing iPhone results, counts, de-duplication, navigation and correct handling of PENDING versus formal PASS before launch. Preserve the existing 93 distinct rider IDs and 0 verified race results.
6. Keep multi-meeting evidence collection and research data separate from the formal published result feed; source search snippets are not original full-field agreement.

This audit is diagnostic only. It does not alter existing feeds, evidence ledgers, public entitlements, data verification outcomes or sync-only scheduled task scope.
