from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import User, UserRole, VTO
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/vto")


def _parse_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_core_values(text: str) -> list[dict[str, str]]:
    values = []
    for line in _parse_lines(text):
        if ":" in line:
            name, description = line.split(":", 1)
            values.append({"name": name.strip(), "description": description.strip()})
        else:
            values.append({"name": line, "description": ""})
    return values


def _format_core_values(values: Optional[list[Any]]) -> str:
    lines = []
    for v in values or []:
        name = v.get("name", "") if isinstance(v, dict) else str(v)
        description = v.get("description", "") if isinstance(v, dict) else ""
        lines.append(f"{name}: {description}" if description else name)
    return "\n".join(lines)


def _get_vto(db: Session, org_id) -> Optional[VTO]:
    return db.scalar(select(VTO).where(VTO.org_id == org_id))


def _vto_context(db: Session, current_user: User, saved: bool = False) -> dict:
    vto = _get_vto(db, current_user.org_id)
    return {
        "current_user": current_user,
        "vto": vto,
        "core_values_text": _format_core_values(vto.core_values) if vto else "",
        "looks_like_text": "\n".join((vto.three_year_picture or {}).get("looks_like", []))
        if vto
        else "",
        "goals_text": "\n".join((vto.one_year_plan or {}).get("goals", [])) if vto else "",
        "saved": saved,
    }


@router.get("")
def get_vto_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    return templates.TemplateResponse(request, "vto/edit.html", _vto_context(db, current_user))


@router.put("")
def save_vto(
    request: Request,
    core_values: str = Form(default=""),
    core_focus_purpose: str = Form(default=""),
    core_focus_niche: str = Form(default=""),
    ten_year_target_description: str = Form(default=""),
    ten_year_target_date: str = Form(default=""),
    three_year_target_date: str = Form(default=""),
    three_year_looks_like: str = Form(default=""),
    one_year_target_date: str = Form(default=""),
    one_year_goals: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)

    vto = _get_vto(db, current_user.org_id)
    if vto is None:
        vto = VTO(org_id=current_user.org_id)
        db.add(vto)

    vto.core_values = _parse_core_values(core_values)
    vto.core_focus_purpose = core_focus_purpose.strip() or None
    vto.core_focus_niche = core_focus_niche.strip() or None

    vto.ten_year_target = (
        {"description": ten_year_target_description.strip(), "target_date": ten_year_target_date}
        if (ten_year_target_description.strip() or ten_year_target_date)
        else None
    )
    vto.three_year_picture = (
        {"target_date": three_year_target_date, "looks_like": _parse_lines(three_year_looks_like)}
        if (three_year_target_date or three_year_looks_like.strip())
        else None
    )
    vto.one_year_plan = (
        {"target_date": one_year_target_date, "goals": _parse_lines(one_year_goals)}
        if (one_year_target_date or one_year_goals.strip())
        else None
    )

    db.commit()
    db.refresh(vto)
    return templates.TemplateResponse(
        request, "vto/_form.html", _vto_context(db, current_user, saved=True)
    )
