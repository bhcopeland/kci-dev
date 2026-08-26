#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from kcidev.api import KciDevError

STATUS_CHOICES = ("all", "pass", "fail", "inconclusive")


def checked_status(status):
    normalised = status.strip().lower()
    if normalised not in STATUS_CHOICES:
        raise KciDevError(
            f"Unknown status {status!r}: expected one of {', '.join(STATUS_CHOICES)}"
        )
    return normalised
