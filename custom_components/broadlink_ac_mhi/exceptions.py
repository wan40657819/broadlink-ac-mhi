"""Exceptions for the Broadlink AC MHI integration."""

from __future__ import annotations


class BroadlinkACError(Exception):
    """Base error for Broadlink AC MHI communication."""


class BroadlinkACConnectionError(BroadlinkACError):
    """Broadlink AC MHI connection error."""


class BroadlinkACTimeoutError(BroadlinkACConnectionError):
    """Broadlink AC MHI connection timeout."""
