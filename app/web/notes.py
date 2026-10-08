"""Shared helpers for the per-row Notes modal (Rocks, Issues, To-Dos)."""

from typing import Optional

from fastapi import HTTPException, Request

from app.web.templates import templates

MAX_NOTES_LENGTH = 5000


def clean_notes(raw: str) -> Optional[str]:
    """Trim; an empty result clears the notes (stored as NULL)."""
    notes = raw.strip()
    if len(notes) > MAX_NOTES_LENGTH:
        raise HTTPException(status_code=422)
    return notes or None


def notes_form_response(
    request: Request,
    *,
    subject: str,
    url: str,
    row_id: str,
    notes: Optional[str],
    can_edit: bool,
):
    """The modal body: an editable form, or read-only text if can_edit is false."""
    return templates.TemplateResponse(
        request,
        "_notes_form.html",
        {
            "subject": subject,
            "url": url,
            "row_id": row_id,
            "notes": notes,
            "can_edit": can_edit,
            "max_length": MAX_NOTES_LENGTH,
        },
    )
