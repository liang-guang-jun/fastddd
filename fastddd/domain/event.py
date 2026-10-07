"""Facts raised by aggregate behavior; they never leave the domain directly."""

from __future__ import annotations


class DomainEvent:
    """Marker base class for internal, immutable domain facts.

    Concrete events should normally be frozen dataclasses. Their shape is an
    implementation detail of a bounded context, unlike an integration event.
    """
