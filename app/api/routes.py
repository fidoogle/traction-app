from fastapi import APIRouter

from app.api.crud_router import build_crud_router
from app.models import Issue, Measurable, Meeting, Organization, Rock, ScorecardEntry, Team, Todo, User
from app.schemas.issue import IssueCreate, IssueRead, IssueUpdate
from app.schemas.measurable import MeasurableCreate, MeasurableRead, MeasurableUpdate
from app.schemas.meeting import MeetingCreate, MeetingRead, MeetingUpdate
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.schemas.rock import RockCreate, RockRead, RockUpdate
from app.schemas.scorecard_entry import ScorecardEntryCreate, ScorecardEntryRead, ScorecardEntryUpdate
from app.schemas.team import TeamCreate, TeamRead, TeamUpdate
from app.schemas.todo import TodoCreate, TodoRead, TodoUpdate
from app.schemas.user import UserCreate, UserRead, UserUpdate

api_router = APIRouter()

api_router.include_router(
    build_crud_router(
        model=Organization,
        create_schema=OrganizationCreate,
        update_schema=OrganizationUpdate,
        read_schema=OrganizationRead,
        prefix="/organizations",
        tags=["organizations"],
    )
)
api_router.include_router(
    build_crud_router(
        model=Team,
        create_schema=TeamCreate,
        update_schema=TeamUpdate,
        read_schema=TeamRead,
        prefix="/teams",
        tags=["teams"],
    )
)
api_router.include_router(
    build_crud_router(
        model=User,
        create_schema=UserCreate,
        update_schema=UserUpdate,
        read_schema=UserRead,
        prefix="/users",
        tags=["users"],
    )
)
api_router.include_router(
    build_crud_router(
        model=Rock,
        create_schema=RockCreate,
        update_schema=RockUpdate,
        read_schema=RockRead,
        prefix="/rocks",
        tags=["rocks"],
    )
)
api_router.include_router(
    build_crud_router(
        model=Measurable,
        create_schema=MeasurableCreate,
        update_schema=MeasurableUpdate,
        read_schema=MeasurableRead,
        prefix="/measurables",
        tags=["measurables"],
    )
)
api_router.include_router(
    build_crud_router(
        model=ScorecardEntry,
        create_schema=ScorecardEntryCreate,
        update_schema=ScorecardEntryUpdate,
        read_schema=ScorecardEntryRead,
        prefix="/scorecard-entries",
        tags=["scorecard-entries"],
    )
)
api_router.include_router(
    build_crud_router(
        model=Issue,
        create_schema=IssueCreate,
        update_schema=IssueUpdate,
        read_schema=IssueRead,
        prefix="/issues",
        tags=["issues"],
    )
)
api_router.include_router(
    build_crud_router(
        model=Todo,
        create_schema=TodoCreate,
        update_schema=TodoUpdate,
        read_schema=TodoRead,
        prefix="/todos",
        tags=["todos"],
    )
)
api_router.include_router(
    build_crud_router(
        model=Meeting,
        create_schema=MeetingCreate,
        update_schema=MeetingUpdate,
        read_schema=MeetingRead,
        prefix="/meetings",
        tags=["meetings"],
    )
)
