"""Build an evidence digest from actual captured text; does not authenticate retrieval."""
from hashlib import sha256
from datetime import datetime,timedelta
from urllib.parse import urlsplit

def capture_record(url, observed_at, method, original_text):
    u=urlsplit(url)
    if u.scheme!="https" or not u.hostname or u.username or u.password:
        raise ValueError("invalid evidence URL")
    if datetime.fromisoformat(observed_at).utcoffset()!=timedelta(hours=9):
        raise ValueError("JST required")
    if method not in ("direct","search_cache","retained_original"):
        raise ValueError("invalid method")
    if not isinstance(original_text,str) or not original_text.strip():
        raise ValueError("missing captured text")
    return {"url":url,"observedAt":observed_at,"method":method,
            "sha256":sha256(original_text.encode("utf-8")).hexdigest(),
            "byteLength":len(original_text.encode("utf-8")),
            "publicationAllowed":False,"trainingAllowed":False}

def verify_record(record, original_text):
    """Verify the supplied original against its recorded digest and byte count."""
    expected=capture_record(record["url"],record["observedAt"],record["method"],original_text)
    return expected["sha256"]==record.get("sha256") and expected["byteLength"]==record.get("byteLength")
