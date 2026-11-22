# Manual evidence intake (candidate only)

Inputs: existing 選手ID照合台帳 is read-only.
Manual writes: KI｜手動照合受付 (sheetId 2101100505).
Automatic writes: KI｜公式照合証拠 (sheetId 2101100503).
Never write to the other stream, test sheet, verified feeds, or production DB.

Before each batch, verify metadata, exact 19 headers and read both streams in bounded ranges.
Use only directly viewed KEIRIN.JP official profile text. Record the source URL, actual JST retrieval time, original text and original/official identity values separately.
Do not infer registration numbers. No official access means no match candidate.
Use appendCells with explicit stringValue for every field. MANUAL records must have a unique MANUAL-prefixed record ID. Preserve leading zeros. Read back all 19 cells by record ID after each append.
Set method direct_official_profile only for actual direct viewing. Use MATCH_CANDIDATE, REJECTED, ERROR or PENDING; independent approval always PENDING.
Record corrections as new rows referencing the old record ID. Never overwrite evidence.
Run audit_dual_intake.py on complete JSON row arrays from both streams before treating records as review candidates. Quarantine duplicates across streams, including repeated registration numbers.
No approval, publication or AI training is authorized by this intake process.
Separate streams prevent cross-stream overwrites but do not provide transactional locking. Concurrent candidate duplicates must be quarantined. Manual operations should be serial.
A readiness decision requires a successful real official-source append/readback and cross-stream audit, not merely this document.
