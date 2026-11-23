#!/usr/bin/env python3
"""Shared, finite result-source diagnostic codes for daily and historical holds.

No raw errors, source HTML or credentials are returned. No PASS or write actions.
"""

def classify_result_hold(exc, phase):
    """Return a finite, non-sensitive diagnostic code, never raw source text."""
    message = str(exc)
    rules = (
        ("Robots rules prohibit", "SOURCE_ROBOTS_DISALLOWED"),
        ("robots disallows", "SOURCE_ROBOTS_DISALLOWED"),
        ("robots access", "SOURCE_ROBOTS_UNAVAILABLE"),
        ("Unable to confirm robots", "SOURCE_ROBOTS_UNAVAILABLE"),
        ("Race date/venue not found", "SOURCE_HEADING_MISMATCH"),
        ("Venue/date not established", "SOURCE_HEADING_MISMATCH"),
        ("Requested R not proven", "SOURCE_RACE_HEADING_MISMATCH"),
        ("Exactly one complete", "SOURCE_INCOMPLETE_OR_AMBIGUOUS_TABLE"),
        ("Name/prefecture/period not fully visible", "SOURCE_RIDER_FIELDS_MISSING"),
        ("Missing rider identity", "SOURCE_RIDER_FIELDS_MISSING"),
        ("Rider class conflicts", "SOURCE_RIDER_CLASS_MISMATCH"),
        ("Unsupported race class", "SOURCE_UNSUPPORTED_RACE_CLASS"),
        ("Invalid finish", "SOURCE_RESULT_STATUS_INVALID"),
        ("Unknown finish", "SOURCE_RESULT_STATUS_INVALID"),
        ("Two result publications do not agree", "TWO_SOURCE_CONTENT_MISMATCH"),
        ("Rider identity does not match pre-race sheet", "ENTRY_RIDER_IDENTITY_MISMATCH"),
        ("Incomplete pair result", "SOURCE_CAR_COUNT_MISMATCH"),
        ("Missing daily Sheets", "SHEETS_READ_INCOMPLETE"),
        ("Daily sheet header mismatch", "SHEETS_HEADER_MISMATCH"),
        ("Saved result row count differs", "SHEETS_SAVE_COUNT_MISMATCH"),
    )
    for fragment, reason in rules:
        if fragment in message:
            return reason
    if phase.startswith("SHEETS"):
        return "SHEETS_OTHER_ERROR"
    if type(exc).__name__ in ("Timeout", "ConnectTimeout", "ReadTimeout"):
        return "SOURCE_TIMEOUT"
    if type(exc).__name__ in ("HTTPError", "ConnectionError", "SSLError"):
        return "SOURCE_NETWORK_ERROR"
    return "SOURCE_OTHER_ERROR"




def self_test():
    assert classify_result_hold(ValueError("Rider class conflicts with requested race class"), "COLLECT_COMPARE") == "SOURCE_RIDER_CLASS_MISMATCH"
    assert classify_result_hold(ValueError("Rider identity does not match pre-race sheet"), "COLLECT_COMPARE") == "ENTRY_RIDER_IDENTITY_MISMATCH"
    assert classify_result_hold(ValueError("Unexpected Sheet response"), "SHEETS_DRY_RUN") == "SHEETS_OTHER_ERROR"
    assert classify_result_hold(ValueError("confidential unknown text"), "COLLECT_COMPARE") == "SOURCE_OTHER_ERROR"
    print("SELF_TEST_OK: finite shared result hold reason codes")


if __name__ == "__main__":
    self_test()
