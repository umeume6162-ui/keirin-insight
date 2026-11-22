# Race result manual intake v1

The spreadsheet tab KI｜レース結果手動照合 (sheetId 2101100506) is an append-only evidence intake, not a verified results database.

- Read V99選手結果蓄積 and V100収集状態台帳 without modifying them.
- Identify a race by ISO date, two-digit venue code and race number. Preserve original result rows and the source range.
- Compare all entrants and their original finish status, number, name, grade, time, margin, winning tactic, S/B, and exceptional statuses. Preserve missing values; do not infer zero or a finish rank.
- Third-party crosschecks are allowed as PENDING with acquisition method secondary_crosscheck. Put exact source URLs and the secondary transcription in the evidence reference column L. Never populate official-only columns K/M/N with third-party data.
- Official source evidence requires an actually retrieved source, exact URL, observed timestamp and attributable original text or durable reference. A search cache is not a direct observation.
- A source URL or a matching transcription by itself is not independent approval. Never fabricate missing official evidence or use an earlier assistant claim as evidence.
- Retain original records; a repeated observation should reference its predecessor and be reviewed for duplicates. Do not overwrite.
- Record source conflicts, including payout conflicts, rather than silently select one value.
- No PENDING row may be published or used in training. Independent official review and the existing verified release guard remain required.
- Keep score data in race-card records, not rider profiles.

Initial rollout: secondary comparison is supported in the intake sheet. Automated validation, official approval and publication integration remain separate work items.
