#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from kcidev.api import KciDevError

STATUS_CHOICES = ("all", "pass", "fail", "inconclusive")

MAX_PAGE_LIMIT = 200

MAX_NODE_LIMIT = 100


def checked_status(status):
    normalised = status.strip().lower()
    if normalised not in STATUS_CHOICES:
        raise KciDevError(
            f"Unknown status {status!r}: expected one of {', '.join(STATUS_CHOICES)}"
        )
    return normalised


def check_page_bounds(limit, offset, max_limit=MAX_PAGE_LIMIT):
    if limit < 0:
        raise KciDevError(f"Invalid limit {limit}: must be zero or greater")
    if limit > max_limit:
        raise KciDevError(
            f"Invalid limit {limit}: must be at most {max_limit}. Page through "
            "results with offset, and use fields to narrow each entry"
        )
    if offset < 0:
        raise KciDevError(f"Invalid offset {offset}: must be zero or greater")


def checked_filters(filters):
    for entry in filters or []:
        if "=" not in entry:
            raise KciDevError(
                f"Invalid filter {entry!r}: expected 'field=value', "
                "for example 'state=done'"
            )
    return list(filters or [])
