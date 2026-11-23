#!/usr/bin/env python3
"""Conservative per-process robots gate for public result source adapters.

Cache a host's *successfully fetched robots policy*, not unrestricted access.
Every requested URL is checked with can_fetch against that same policy.
The cache exists only in the current short-lived GitHub Actions process.
"""
from functools import lru_cache
from urllib.robotparser import RobotFileParser

import requests


@lru_cache(maxsize=8)
def _policy(host, user_agent):
    response = requests.get("https://" + host + "/robots.txt",
                            headers={"User-Agent": user_agent}, timeout=15)
    if response.status_code == 200:
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser
    if response.status_code in (404, 410):
        return None
    raise ValueError("Unable to confirm robots access; no fetch")


def require_robots_access(url, host, user_agent):
    """Fail closed for unverified robots; never cache permission for a new URL."""
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != host:
        raise ValueError("Result URL does not match approved source host")
    policy = _policy(host, user_agent)
    if policy is not None and not policy.can_fetch(user_agent, url):
        raise ValueError("Robots rules prohibit this page")


def self_test():
    from types import SimpleNamespace
    from unittest.mock import patch
    agent = "KEIRIN-INSIGHT-Research/1.0"
    host = "verified.example"
    rule = "User-agent: *\nDisallow: /private/\nAllow: /public/\n"
    try:
        with patch.object(requests, "get", return_value=SimpleNamespace(
                status_code=200, text=rule)) as get:
            require_robots_access("https://" + host + "/public/r1", host, agent)
            require_robots_access("https://" + host + "/public/r2", host, agent)
            assert get.call_count == 1
            try:
                require_robots_access("https://" + host + "/private/r3", host, agent)
            except ValueError:
                pass
            else:
                raise AssertionError("Cached robots policy bypassed for blocked path")
            assert get.call_count == 1
    finally:
        _policy.cache_clear()
    with patch.object(requests, "get", return_value=SimpleNamespace(
            status_code=503, text="")):
        try:
            require_robots_access("https://" + host + "/public/r1", host, agent)
        except ValueError:
            pass
        else:
            raise AssertionError("Unverifiable robots policy accepted")
    _policy.cache_clear()
    print("SELF_TEST_OK: per-job policy reuse preserves per-URL robots checks")


if __name__ == "__main__":
    self_test()
