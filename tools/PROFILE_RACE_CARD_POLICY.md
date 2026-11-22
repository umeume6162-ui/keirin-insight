# Profile and race-card data separation

## UI contract
- Rider profiles show independently verified identity and basic biographical fields.
- Grade transitions may be shown as dated history; never infer a current grade from a stale snapshot.
- Do not display competition scores, current-term scores, rolling scores, win rates or other volatile race-card metrics on the profile.
- Competition scores and other race-card metrics are displayed only on the corresponding race card, with its race identity, observation timestamp, source and aggregation scope.
- Do not replace missing race-card scores with profile scores, a different race's values, or zeros.
- Preserve prior evidence, including previously captured scores, in the research layer. Do not delete or rewrite it.
- Review scores remain internal and separate from race-card display scores.
- The immutable rider registration number is the join key. Changes to scores do not trigger identity revalidation.
- A periodic grade/history refresh is separate from race-card collection. No automatic refresh is claimed until deployed and verified.
- Unapproved records are excluded from public feeds and training.
