"""Validate that the web UI renders Phi-driven membership semantics."""

from __future__ import annotations

from pathlib import Path


def test_ui_no_longer_uses_active_idle_liveness_labels() -> None:
    """Assert active/idle liveness labels are removed from UI rendering logic."""
    app_js = Path("web/app.js").read_text(encoding="utf-8")
    assert "node-mark" not in app_js
    assert '"active"' not in app_js
    assert '"idle"' not in app_js


def test_ui_polls_and_renders_membership_endpoint() -> None:
    """Assert UI uses Phi-driven membership snapshot endpoint and statuses."""
    app_js = Path("web/app.js").read_text(encoding="utf-8")
    styles_css = Path("web/styles.css").read_text(encoding="utf-8")
    assert "/api/membership" in app_js
    assert ".member-status.alive" in styles_css
    assert ".member-status.suspected" in styles_css
    assert ".member-status.dead" in styles_css
