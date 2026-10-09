"""Seed a rich, entirely fictional demo dataset for evaluation.

Not for production use - this creates a fake congregation (Grace Community
Church, ~500 members: men, women and youth) in its second quarter of using
the app. 25 members hold a leadership or service role and have logins; the
rest of the congregation shows up only in the numbers (attendance, giving).

Teams: Leadership Council, Men's Ministry, Women's Ministry, Youth Ministry.
Q3 2026 (Jul 6 - Oct 4) is finished, with a full 13-week scorecard and rocks
graded done / off-track. Q4 2026 began Oct 4; scorecard weeks start on Monday
(week 1 = Mon Oct 5).

Every login is <prefix>-<role>@myemail.com (admin@myemail.com for the org
admin), password demo1234.

Usage:
    python scripts/seed_demo_data.py [--reset]

--reset truncates all app tables first. Destructive - only ever run this
against a local/dev/evaluation database.
"""
import argparse
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Issue,
    IssueStatus,
    Measurable,
    Meeting,
    MeetingStatus,
    Organization,
    PeopleAnalyzerEntry,
    Rock,
    RockStatus,
    Scorecard,
    ScorecardEntry,
    Seat,
    Team,
    TeamMembership,
    Todo,
    TodoStatus,
    User,
    UserRole,
    VTO,
)

DEMO_TABLES = [
    "activity_log",
    "people_analyzer_entries",
    "vtos",
    "seats",
    "todos",
    "issues",
    "scorecard_entries",
    "measurables",
    "scorecards",
    "rocks",
    "meetings",
    "team_memberships",
    "users",
    "teams",
    "organizations",
]

DEMO_PASSWORD = "demo1234"
DOMAIN = "myemail.com"

Q3, Q4 = "2026-Q3", "2026-Q4"
Q3_START = date(2026, 7, 6)  # Monday
Q4_START = date(2026, 10, 5)  # Monday
TODAY = date.today()

OPEN, RESOLVED, DROPPED = IssueStatus.OPEN, IssueStatus.RESOLVED, IssueStatus.DROPPED
DONE = TodoStatus.DONE
ON, OFF, FIN = RockStatus.ON_TRACK, RockStatus.OFF_TRACK, RockStatus.DONE


def d(days: int) -> date:
    """A date relative to today."""
    return TODAY + timedelta(days=days)


def reset(db) -> None:
    existing = {
        r[0] for r in db.execute(text("select tablename from pg_tables where schemaname='public'"))
    }
    tables = [t for t in DEMO_TABLES if t in existing]
    db.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    db.commit()


# (key, name, email-local, role, home team, [other teams], team-admin-of-home)
PEOPLE = [
    ("pastor", "Pastor Daniel Reyes", "admin", UserRole.ADMIN, "council", [], False),
    ("linda", "Linda Whitfield", "woman-team-admin-council", UserRole.MEMBER, "council", [], True),
    ("bob", "Robert Sanders", "man-team-admin-men", UserRole.MEMBER, "men", ["council"], True),
    ("carol", "Carol Menendez", "woman-team-admin-women", UserRole.MEMBER, "women", ["council"], True),
    ("marcus", "Marcus Tran", "youth-team-admin-youth", UserRole.MEMBER, "youth", ["council"], True),
    ("harold", "Harold Peterson", "man-elder-treasurer", UserRole.MEMBER, "council", ["men"], False),
    ("esther", "Esther Williams", "woman-deaconess-benevolence", UserRole.MEMBER, "council", ["women"], False),
    ("tom", "Tom Kowalski", "man-grounds-landscaping", UserRole.MEMBER, "men", [], False),
    ("eddie", "Eddie Alvarez", "man-parking-lot", UserRole.MEMBER, "men", [], False),
    ("frank", "Frank Okafor", "man-building-maintenance", UserRole.MEMBER, "men", [], False),
    ("steve", "Steve Martinez", "man-events-bbq", UserRole.MEMBER, "men", [], False),
    ("greg", "Greg Hamilton", "man-sports-coach", UserRole.MEMBER, "men", ["youth"], False),
    ("walter", "Walter Nguyen", "man-bible-study", UserRole.MEMBER, "men", ["women", "youth"], False),
    ("beth", "Beth Anderson", "woman-hospital-visits", UserRole.MEMBER, "women", [], False),
    ("ruth", "Ruth Callahan", "woman-nursing-home", UserRole.MEMBER, "women", [], False),
    ("maria", "Maria Santos", "woman-youth-counseling", UserRole.MEMBER, "women", ["youth"], False),
    ("dolores", "Dolores Washington", "woman-kitchen-meals", UserRole.MEMBER, "women", [], False),
    ("grace", "Grace Kim", "woman-music-ministry", UserRole.MEMBER, "women", ["youth"], False),
    ("naomi", "Naomi Fischer", "woman-bible-study", UserRole.MEMBER, "women", ["men"], False),
    ("patricia", "Patricia Lopez", "woman-school-supplies", UserRole.MEMBER, "women", [], False),
    ("kayla", "Kayla Brooks", "youth-multimedia", UserRole.MEMBER, "youth", [], False),
    ("isaiah", "Isaiah Johnson", "youth-music-ministry", UserRole.MEMBER, "youth", [], False),
    ("sophia", "Sophia Delgado", "youth-event-planning", UserRole.MEMBER, "youth", [], False),
    ("noah", "Noah Bennett", "youth-photo-logging", UserRole.MEMBER, "youth", [], False),
    ("tyler", "Tyler Reed", "youth-sports", UserRole.MEMBER, "youth", ["men"], False),
    ("elena", "Elena Ruiz", "youth-bible-study", UserRole.MEMBER, "youth", [], False),
    # Read-only congregant, for testing the viewer role.
    ("helen", "Helen Carter", "woman-viewer-congregant", UserRole.VIEWER, "women", [], False),
]

TEAMS = [
    ("council", "Leadership Council", "Monday"),
    ("men", "Men's Ministry", "Tuesday"),
    ("women", "Women's Ministry", "Wednesday"),
    ("youth", "Youth Ministry", "Thursday"),
]

# --- Rocks: (team, owner, title, status Q3 / Q4) -----------------------------
# Q3 is finished (done / off-track); Q4 only just started.
ROCKS_Q3 = [
    ("council", "pastor", "Complete building fund campaign phase 1 ($85,000 pledged)", FIN),
    ("council", "pastor", "Preach 'Foundations' series and track first-time guest follow-up", FIN),
    ("council", "linda", "Hire a part-time worship administrator", OFF),
    ("council", "harold", "Move giving to online / text-to-give with 25% adoption", FIN),
    ("council", "esther", "Write the benevolence fund policy and application form", FIN),
    ("men", "tom", "Re-sod the front lawn and replace failing sprinkler zones", FIN),
    ("men", "eddie", "Recruit 10 parking-team volunteers for a Sunday rotation", FIN),
    ("men", "frank", "Repair the fellowship hall roof leak", OFF),
    ("men", "steve", "Host the Men's Summer Cookout with 100 attendees", FIN),
    ("men", "bob", "Re-establish the men's ministry leadership huddle monthly", FIN),
    ("women", "beth", "Build a roster of 8 trained hospital visitors", FIN),
    ("women", "dolores", "Re-launch Wednesday fellowship suppers (avg 100 meals)", FIN),
    ("women", "patricia", "Distribute 200 school supply kits before August 15", FIN),
    ("women", "grace", "Recruit 6 new choir and praise-team members", OFF),
    ("women", "carol", "Staff the nursery on every Sunday with trained volunteers", OFF),
    ("youth", "kayla", "Stream every Sunday service with no more than 1 dropout", FIN),
    ("youth", "sophia", "Run the Summer Kickoff Bash with 70 youth", FIN),
    ("youth", "isaiah", "Form a youth worship band and lead one service", FIN),
    ("youth", "marcus", "Complete background checks for all youth volunteers", FIN),
]
ROCKS_Q4 = [
    ("council", "pastor", "Launch 'Year of Hospitality' series and visitor follow-up plan", ON),
    ("council", "pastor", "Recruit and train 2 new elders", ON),
    ("council", "linda", "Verify and update the 500-member directory (contact info, ministries)", ON),
    ("council", "linda", "Finalize the 2027 ministry and facility calendar", ON),
    ("council", "harold", "Present the 2027 budget for congregational approval by Nov 22", ON),
    ("council", "harold", "Prepare year-end giving statements and audit packet", ON),
    ("council", "esther", "Match 30 families for Thanksgiving and Christmas adoption", ON),
    ("men", "tom", "Complete fall cleanup: aerate, overseed, leaves and hedges by Nov 15", ON),
    ("men", "tom", "Winterize the irrigation system before the first freeze", ON),
    ("men", "eddie", "Re-stripe the parking lot and add 4 ADA spaces", ON),
    ("men", "eddie", "Train 12 parking volunteers for Christmas Eve traffic flow", ON),
    ("men", "frank", "Repair the fellowship hall roof leak (3 bids, work done)", OFF),
    ("men", "frank", "Service all HVAC units before cold weather", ON),
    ("men", "steve", "Host Men's BBQ Night on Oct 24 with 120 men", ON),
    ("men", "greg", "Launch Thursday open-gym basketball with 16 regular players", ON),
    ("men", "walter", "Run 'Proverbs for Men': 8-week Tuesday 6am Bible study", ON),
    ("men", "bob", "Recruit a snow and ice removal lead and 6-man crew", ON),
    ("women", "beth", "Train 6 new hospital-visit volunteers; log every visit", ON),
    ("women", "ruth", "Schedule a monthly hymn sing at Maplewood Care and Pine Ridge", ON),
    ("women", "maria", "Recruit a second certified counselor for the youth counseling room", ON),
    ("women", "dolores", "Serve Wednesday suppers at 120 meals avg and Thanksgiving for 250", ON),
    ("women", "grace", "Prepare the Christmas cantata: 30-voice choir", ON),
    ("women", "naomi", "Launch 'Women of the Word' with 3 table groups of 10", ON),
    ("women", "patricia", "Collect 150 winter coats for the coat drive", ON),
    ("women", "carol", "Recruit 8 nursery volunteers to cover every Sunday", OFF),
    ("youth", "kayla", "Add a second camera and lower-third graphics to the livestream", ON),
    ("youth", "isaiah", "Youth band leads 2 Sunday services a month with 8 new songs", ON),
    ("youth", "sophia", "Plan and run Fall Fest on Oct 31 (80 kids, 20 volunteers)", ON),
    ("youth", "noah", "Build the shared photo archive: every event posted within 48 hours", ON),
    ("youth", "tyler", "Run flag football season: 2 teams, 6 games", ON),
    ("youth", "elena", "Wednesday 'Real Talk' youth Bible study averaging 15", ON),
    ("youth", "marcus", "Onboard 6 new 6th graders and assign a mentor to each", ON),
]

# --- Scorecards -----------------------------------------------------------
# (owner, name, unit, goal, direction, lo, hi, q4_week1)
# Q3 weekly values are generated between goal*lo and goal*hi (seeded, so a
# reseed is stable). Explicit lists override. q4_week1 is what's been
# recorded so far this week (None = still blank).
SCORECARDS = {
    "council": [
        ("pastor", "Sunday worship attendance", "number", 320, "gte", None, None, None,
         [298, 305, 276, 262, 281, 299, 318, 324, 331, 342, 336, 348, 351]),
        ("harold", "Weekly giving", "currency", 12500, "gte", 0.84, 1.14, None, None),
        ("linda", "First-time guests", "number", 5, "gte", 0.4, 1.8, None, None),
        ("linda", "Members serving in a ministry", "percent", 60, "gte", 0.88, 1.08, None, None),
        ("esther", "Benevolence requests answered within 48 hours", "percent", 90, "gte", 0.8, 1.1, None, None),
    ],
    "men": [
        ("tom", "Grounds volunteer hours", "number", 12, "gte", 0.5, 1.5, 9, None),
        ("eddie", "Sunday parking shifts staffed", "percent", 90, "gte", 0.8, 1.1, None, None),
        ("frank", "Open maintenance requests", "number", 6, "lte", 0.5, 1.9, 8, None),
        ("walter", "Men's Bible study attendance", "number", 18, "gte", 0.6, 1.25, None, None),
        ("greg", "Open gym attendance", "number", 14, "gte", 0.5, 1.3, 11, None),
    ],
    "women": [
        ("beth", "Hospital visits made", "number", 6, "gte", 0.3, 1.8, 4, None),
        ("ruth", "Nursing home visits", "number", 4, "gte", 0.5, 1.75, 2, None),
        ("maria", "Youth counseling sessions held", "number", 5, "gte", 0.4, 1.6, 3, None),
        ("dolores", "Fellowship supper meals served", "number", 120, "gte", 0.75, 1.15, None, None),
        ("grace", "Choir and praise team rehearsal attendance", "number", 12, "gte", 0.6, 1.25, None, None),
        ("naomi", "Women's Bible study attendance", "number", 28, "gte", 0.7, 1.2, None, None),
        ("patricia", "School supply kits distributed", "number", 15, "gte", None, None, None,
         [0, 4, 9, 18, 24, 41, 62, 38, 22, 12, 6, 3, 1]),
    ],
    "youth": [
        ("kayla", "Livestream viewers", "number", 90, "gte", 0.7, 1.25, None, None),
        ("kayla", "Services streamed without a dropout", "percent", 95, "gte", 0.88, 1.05, None, None),
        ("isaiah", "Youth band rehearsal attendance", "number", 8, "gte", 0.5, 1.4, 6, None),
        ("sophia", "Youth night attendance", "number", 35, "gte", 0.65, 1.3, None, None),
        ("noah", "Event photo albums posted within 48 hours", "number", 1, "gte", 0.0, 2.0, 1, None),
        ("tyler", "Sports practice attendance", "number", 18, "gte", 0.6, 1.3, 15, None),
        ("elena", "Youth Bible study attendance", "number", 15, "gte", 0.6, 1.3, None, None),
    ],
}
# Q4 swaps a seasonal Q3 row for a Q4 one: team -> {old name: replacement row}.
Q4_SWAPS = {
    "women": {
        "School supply kits distributed": (
            "patricia", "Winter coats collected", "number", 10, "gte", 0.5, 1.5, 5, None),
    },
}

# --- Issues (and the to-dos that come out of them) --------------------------
# (team, title, status, priority, notes, [(owner, todo title, due offset, status)])
ISSUES = [
    # Leadership Council
    ("council", "Sunday attendance dipped below 280 in July", RESOLVED, 2,
     "Summer travel. Recovered by September; plan a 'Welcome Back Sunday' next year.",
     [("pastor", "Schedule Welcome Back Sunday for September 2027", -20, DONE)]),
    ("council", "Sanctuary is full at the 10:30 service; consider a second service", OPEN, 1,
     "Averaging 340-350 in a room that seats 380. Need volunteer capacity for a second service before deciding.",
     [("linda", "Survey members on 9:00 vs 8:30 start times", 6, TodoStatus.OPEN),
      ("pastor", "Draft a second-service staffing proposal for the elders", 20, TodoStatus.OPEN)]),
    ("council", "Giving is ahead of budget but the building fund is behind", OPEN, 2,
     "General giving +6% vs budget. Building fund pledges collected at 71%.",
     [("harold", "Send gentle pledge reminders to open building fund pledges", 4, TodoStatus.OPEN)]),
    ("council", "Worship administrator position still unfilled", OPEN, 2,
     "Missed Q3 rock. Choir director and AV volunteers are covering bulletin and slides.",
     [("linda", "Post the job description and ask the elders for referrals", -2, TodoStatus.OPEN)]),
    ("council", "No clear process for hospital and nursing home visit requests", OPEN, 3,
     "Requests come in by text, email and hallway. Pastor hears about some of them late.",
     [("esther", "Meet Beth and Ruth to design a single request form", 10, TodoStatus.OPEN)]),
    ("council", "Church website and online directory are out of date", OPEN, 3, None, []),
    ("council", "Elder candidates are all over 55", DROPPED, 3,
     "Discussed and moved to the Q4 'recruit 2 elders' rock.", []),
    # Men's Ministry
    ("men", "Fellowship hall roof still leaks in heavy rain", OPEN, 1,
     "Two bids so far ($6,800 and $9,400). Third roofer has not returned calls. Buckets are out for now.",
     [("frank", "Get the third roofing bid and present all three to the council", 3, TodoStatus.OPEN),
      ("frank", "Tarp the north corner before the next storm", -3, DONE)]),
    ("men", "Parking lot flow jams after the 10:30 service", OPEN, 1,
     "Cars leaving through the north exit conflict with the children's pickup line.",
     [("eddie", "Draw up a one-way traffic plan and review it with the pastor", 5, TodoStatus.OPEN),
      ("eddie", "Order 6 cones and 2 'Do Not Enter' signs", 8, TodoStatus.OPEN)]),
    ("men", "Lawn mower needs replacing; the 2014 zero-turn keeps breaking", OPEN, 2,
     "$480 in repairs this year. A replacement runs about $3,900.",
     [("tom", "Get 2 quotes and ask Harold what the equipment budget can cover", 7, TodoStatus.OPEN)]),
    ("men", "Not enough volunteers for fall leaf cleanup Saturday", OPEN, 2,
     "Only 5 signed up of the 12 needed.",
     [("bob", "Announce leaf-cleanup Saturday at the men's breakfast and in the bulletin", 2, TodoStatus.OPEN),
      ("tom", "Borrow two leaf blowers from the Hendersons", 3, TodoStatus.OPEN)]),
    ("men", "Men's BBQ Night: grill, meat order and a rain plan", OPEN, 2,
     "Oct 24. Smoker is available, but the fellowship hall roof leaks if it rains.",
     [("steve", "Confirm the meat order (brisket and sausage) with Martinez Meats", 9, TodoStatus.OPEN),
      ("steve", "Reserve the backup tent from the rental yard", 12, TodoStatus.OPEN)]),
    ("men", "Snow removal plan: no one owns it yet", OPEN, 3,
     "Last winter the walks were cleared by whoever showed up.",
     [("bob", "Ask Tom and Eddie for names of possible crew leads", 6, TodoStatus.OPEN)]),
    ("men", "Gutters clogged on the education wing", RESOLVED, 3, "Cleared in September.",
     [("frank", "Clean gutters and downspouts on the education wing", -12, DONE)]),
    # Women's Ministry
    ("women", "No volunteer for the nursery on 2 of the last 4 Sundays", OPEN, 1,
     "Parents are being pulled from the service. Need at least 8 trained volunteers.",
     [("carol", "Send a nursery sign-up sheet around after the women's Bible study", 3, TodoStatus.OPEN),
      ("carol", "Schedule background checks for 3 new volunteers", 10, TodoStatus.OPEN)]),
    ("women", "Fellowship supper count is 20+ over what we prep for", OPEN, 1,
     "Wednesday suppers hit 140 last week and ran out of casserole. Need a sign-up count by Monday.",
     [("dolores", "Add a Monday RSVP line to the bulletin and the text list", 3, TodoStatus.OPEN),
      ("dolores", "Ask the Garcia family to cover the second oven", 5, TodoStatus.OPEN)]),
    ("women", "Hospital visit requests reach us too late", OPEN, 2,
     "Heard about a surgery after the patient was already home. Need one number to text.",
     [("beth", "Set up a shared text line for visit requests", 8, TodoStatus.OPEN)]),
    ("women", "Nursing home visits: Pine Ridge needs a fresh volunteer background form", OPEN, 2,
     "Pine Ridge requires updated forms for every visitor each year.",
     [("ruth", "Collect updated forms from the 6 visitors", -1, TodoStatus.OPEN),
      ("ruth", "Drop off the signed forms at the Pine Ridge front desk", 7, TodoStatus.OPEN)]),
    ("women", "Youth counseling room needs privacy: door window and sound machine", OPEN, 2,
     "Required by the counseling safety policy before the second counselor starts.",
     [("maria", "Ask the men's team to install a door window film", 10, TodoStatus.OPEN)]),
    ("women", "Choir is short on tenors and basses for the cantata", OPEN, 3, None,
     [("grace", "Invite the men's Bible study to a tenor-bass call", 6, TodoStatus.OPEN)]),
    ("women", "School supply leftovers: where do we store 40 backpacks?", RESOLVED, 3,
     "Stored in the education wing closet.",
     [("patricia", "Label and shelve the leftover backpacks", -9, DONE)]),
    # Youth Ministry
    ("youth", "Livestream drops in the last 10 minutes of the sermon", OPEN, 1,
     "Wi-Fi congestion when everyone is in the building. Need a wired connection at the media desk.",
     [("kayla", "Ask Frank about running a network cable to the media desk", 4, TodoStatus.OPEN)]),
    ("youth", "Fall Fest: booth volunteers and candy supply not confirmed", OPEN, 1,
     "Oct 31, 5-8 pm. Need 20 volunteers, 4 booths and parent permission slips.",
     [("sophia", "Finalize booth assignments and send to all volunteers", 3, TodoStatus.OPEN),
      ("sophia", "Collect permission slips from every registered youth", 14, TodoStatus.OPEN),
      ("marcus", "Get the candy donation from the Reed family", 6, TodoStatus.OPEN)]),
    ("youth", "Event photos are scattered across phones; no consent tracking", OPEN, 2,
     "Need a single shared album and a consent list for minors before anything goes public.",
     [("noah", "Create the shared album and ask the council about a consent policy", 7, TodoStatus.OPEN)]),
    ("youth", "Flag football field conflicts with the men's open gym night", OPEN, 2, None,
     [("tyler", "Meet Greg and agree on Thursday gym time", 2, TodoStatus.OPEN)]),
    ("youth", "Band needs a better monitor mix and in-ear packs", OPEN, 3,
     "Estimated $620. Ask the council whether the youth budget can absorb it.",
     [("isaiah", "Write a one-page equipment request for the council", 11, TodoStatus.OPEN)]),
    ("youth", "Youth Bible study attendance dropped in September", OPEN, 3,
     "School schedules and homework. Try moving to Sunday evenings?",
     [("elena", "Poll youth on best day and time", 5, TodoStatus.OPEN)]),
    ("youth", "Summer Kickoff Bash budget overrun", RESOLVED, 3, "Overran $240; covered by the donations.",
     [("sophia", "Reconcile receipts with the treasurer", -25, DONE)]),
]

# --- VTO per team ---------------------------------------------------------
VTOS = {
    "council": dict(
        core_values=[
            {"name": "Love God, Love People", "description": "Everything we do flows from the two great commandments"},
            {"name": "Everyone Serves", "description": "Every member has a place to use their gifts"},
            {"name": "Stewardship", "description": "We handle people, time and money with care and transparency"},
        ],
        purpose="Help people follow Jesus and serve their neighbors",
        niche="A close-knit congregation of about 500 where everyone is known by name",
        ten=("A church where 75% of members serve and every family belongs to a small group", "2036-12-31"),
        three=("2029-12-31", ["600 members", "A second worship service", "Debt-free building"]),
        one=("2027-12-31", ["Add a second service", "Raise the building fund to $250,000", "Seat 2 new elders"]),
    ),
    "men": dict(
        core_values=[
            {"name": "Show Up", "description": "We keep our word and arrive when we say we will"},
            {"name": "Serve Quietly", "description": "The work matters more than the credit"},
            {"name": "Iron Sharpens Iron", "description": "We build each other up in faith and friendship"},
        ],
        purpose="Equip men to lead and serve their families and church",
        niche="Practical service: grounds, parking, buildings and brotherhood",
        ten=("A men's ministry with 150 men serving regularly", "2036-12-31"),
        three=("2029-12-31", ["Every building system on a maintenance schedule", "60 men in weekly Bible study"]),
        one=("2027-12-31", ["Complete the roof repair", "Staff all parking shifts", "Run 4 men's events"]),
    ),
    "women": dict(
        core_values=[
            {"name": "Compassion", "description": "We go where people are hurting"},
            {"name": "Hospitality", "description": "Our table and our doors are open"},
            {"name": "Faithfulness", "description": "We follow through"},
        ],
        purpose="Care for our church and community with the love of Christ",
        niche="Visits, meals, music and mentoring",
        ten=("A caring network where no member goes unvisited", "2036-12-31"),
        three=("2029-12-31", ["25 trained visitors", "Fully staffed nursery", "Two Bible study groups per season"]),
        one=("2027-12-31", ["Every Sunday nursery staffed", "Monthly care-center visits", "200 supper meals at Thanksgiving"]),
    ),
    "youth": dict(
        core_values=[
            {"name": "Belong", "description": "Every student is welcome and known"},
            {"name": "Grow", "description": "We help students own their faith"},
            {"name": "Lead", "description": "Students lead worship, media and service"},
        ],
        purpose="Help students know Jesus and lead now, not later",
        niche="Student-led media, music, events and sports",
        ten=("A youth ministry that sends leaders into every area of church life", "2036-12-31"),
        three=("2029-12-31", ["60 regular students", "Student-run media team", "A student mission trip each year"]),
        one=("2027-12-31", ["Add a second camera and livestream", "Run 3 retreats", "Mentor every new 6th grader"]),
    ),
}

# --- Accountability charts: (key, title, holder, parent key, [duties], team)
SEATS = [
    ("visionary", "council", "Senior Pastor (Visionary)", "pastor", None,
     ["Preach and set vision", "Shepherd the elders", "Final call on doctrine"]),
    ("integrator", "council", "Church Administrator (Integrator)", "linda", "visionary",
     ["Run the weekly Council meeting", "Calendar, facility and staff coordination", "Hold ministry leaders accountable"]),
    ("treasurer", "council", "Treasurer", "harold", "integrator",
     ["Budget and reporting", "Count and bank giving", "Year-end statements"]),
    ("benevolence", "council", "Benevolence Lead", "esther", "integrator",
     ["Process help requests", "Run adoption programs"]),
    ("comms", "council", "Communications Lead", None, "integrator",
     ["Website, bulletin and email list", "Social media"]),
    ("men_dir", "men", "Men's Ministry Director", "bob", "integrator",
     ["Run the Men's team meeting", "Coordinate service teams"]),
    ("grounds", "men", "Grounds Lead", "tom", "men_dir", ["Lawn, landscaping, irrigation"]),
    ("parking", "men", "Parking Lot Lead", "eddie", "men_dir", ["Parking volunteers, traffic flow, striping"]),
    ("facilities", "men", "Building Maintenance Lead", "frank", "men_dir", ["Roof, HVAC, repairs"]),
    ("bbq", "men", "Men's Events Lead", "steve", "men_dir", ["BBQ night and men's events"]),
    ("snow", "men", "Snow and Ice Lead", None, "men_dir", ["Clear walks and lots in winter"]),
    ("women_dir", "women", "Women's Ministry Director", "carol", "integrator",
     ["Run the Women's team meeting", "Coordinate service teams"]),
    ("hospital", "women", "Hospital Visits Lead", "beth", "women_dir", ["Hospital visitor schedule"]),
    ("nursing", "women", "Nursing Home Lead", "ruth", "women_dir", ["Care-center visits"]),
    ("counsel", "women", "Youth Counseling Lead", "maria", "women_dir", ["Counseling intake and scheduling"]),
    ("kitchen", "women", "Kitchen and Meals Lead", "dolores", "women_dir", ["Wednesday suppers, church meals"]),
    ("music", "women", "Music Ministry Lead", "grace", "women_dir", ["Choir and praise team"]),
    ("supplies", "women", "School Supplies Lead", "patricia", "women_dir", ["Drive and distribution"]),
    ("youth_dir", "youth", "Youth Director", "marcus", "integrator",
     ["Run the Youth team meeting", "Volunteer screening"]),
    ("media", "youth", "Multimedia Lead", "kayla", "youth_dir", ["Livestream, slides, video"]),
    ("youthmusic", "youth", "Youth Music Lead", "isaiah", "youth_dir", ["Youth band"]),
    ("events", "youth", "Event Planning Lead", "sophia", "youth_dir", ["Youth events and retreats"]),
    ("photos", "youth", "Photo Logging Lead", "noah", "youth_dir", ["Event photos and archive"]),
    ("sports", "youth", "Sports Lead", "tyler", "youth_dir", ["Sports teams and schedule"]),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="Truncate all app tables first (destructive)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.reset:
            reset(db)

        org = Organization(name="Grace Community Church")
        db.add(org)
        db.flush()

        teams: dict[str, Team] = {}
        for key, name, day in TEAMS:
            teams[key] = Team(org_id=org.id, name=name, meeting_day=day)
            db.add(teams[key])
        db.flush()

        password_hash = hash_password(DEMO_PASSWORD)
        users: dict[str, User] = {}
        for key, name, local, role, home, others, is_admin in PEOPLE:
            user = User(
                org_id=org.id,
                team_id=teams[home].id,
                name=name,
                email=f"{local}@{DOMAIN}",
                role=role,
                hashed_password=password_hash,
                memberships=[
                    TeamMembership(team_id=teams[home].id, is_team_admin=is_admin),
                    *[TeamMembership(team_id=teams[t].id) for t in others],
                ],
            )
            db.add(user)
            users[key] = user
        db.flush()

        # --- Accountability charts ---
        seats: dict[str, Seat] = {}
        for key, team, title, holder, parent, duties in SEATS:
            seat = Seat(
                team_id=teams[team].id,
                user_id=users[holder].id if holder else None,
                parent_seat_id=seats[parent].id if parent else None,
                title=title,
                responsibilities=duties,
            )
            db.add(seat)
            db.flush()
            seats[key] = seat

        # --- VTOs ---
        for key, v in VTOS.items():
            db.add(
                VTO(
                    org_id=org.id,
                    team_id=teams[key].id,
                    core_values=v["core_values"],
                    core_focus_purpose=v["purpose"],
                    core_focus_niche=v["niche"],
                    ten_year_target={"description": v["ten"][0], "target_date": v["ten"][1]},
                    three_year_picture={"target_date": v["three"][0], "looks_like": v["three"][1]},
                    one_year_plan={"target_date": v["one"][0], "goals": v["one"][1]},
                )
            )

        # --- Rocks ---
        for quarter, rows in ((Q3, ROCKS_Q3), (Q4, ROCKS_Q4)):
            for team, owner, title, status in rows:
                db.add(
                    Rock(
                        team_id=teams[team].id,
                        owner_id=users[owner].id,
                        title=title,
                        quarter=quarter,
                        status=status,
                    )
                )

        # --- Scorecards: Q3 finished (13 weeks), Q4 just started ---
        def build(team: str, name: str, start: date, rows, week_values) -> None:
            scorecard = Scorecard(
                org_id=org.id, team_id=teams[team].id, name=name, start_date=start
            )
            db.add(scorecard)
            db.flush()
            for position, row in enumerate(rows, start=1):
                owner, m_name, unit, goal, direction = row[:5]
                measurable = Measurable(
                    scorecard_id=scorecard.id,
                    owner_id=users[owner].id,
                    name=m_name,
                    unit=unit,
                    goal_value=goal,
                    goal_direction=direction,
                    position=position,
                )
                db.add(measurable)
                db.flush()
                for week, value in week_values(row):
                    db.add(
                        ScorecardEntry(
                            measurable_id=measurable.id, week_number=week, actual_value=value
                        )
                    )

        def q3_values(row):
            owner, m_name, unit, goal, direction, lo, hi, _w1, explicit = row
            if explicit is not None:
                return list(enumerate(explicit, start=1))
            rng = random.Random(f"{owner}-{m_name}")
            out = []
            for week in range(1, 14):
                value = goal * rng.uniform(lo, hi)
                if unit == "currency":
                    value = round(value, -1)
                elif unit == "percent":
                    value = min(100, round(value, 1))
                else:
                    value = max(0, round(value))
                out.append((week, value))
            return out

        def q4_values(row):
            w1 = row[7]
            return [(1, w1)] if w1 is not None else []

        for team, rows in SCORECARDS.items():
            build(team, "Q3 2026 Scorecard", Q3_START, rows, q3_values)
            swaps = Q4_SWAPS.get(team, {})
            q4_rows = [swaps.get(r[1], r) for r in rows]
            build(team, "Q4 2026 Scorecard", Q4_START, q4_rows, q4_values)

        # --- Issues + to-dos ---
        for team, title, status, priority, notes, todos in ISSUES:
            issue = Issue(
                team_id=teams[team].id, title=title, status=status, priority=priority, notes=notes
            )
            db.add(issue)
            db.flush()
            for owner, todo_title, due, todo_status in todos:
                db.add(
                    Todo(
                        team_id=teams[team].id,
                        owner_id=users[owner].id,
                        issue_id=issue.id,
                        title=todo_title,
                        due_date=d(due),
                        status=todo_status,
                    )
                )
        # A few to-dos that came straight out of a meeting, no issue behind them.
        loose = [
            ("council", "pastor", "Send the elder retreat agenda to all elders", 2, TodoStatus.OPEN),
            ("council", "harold", "Deposit the October 4 offering", -4, DONE),
            ("men", "bob", "Book the pavilion for Men's BBQ Night", -6, DONE),
            ("women", "carol", "Confirm the Thanksgiving dinner date with the pastor", 4, TodoStatus.OPEN),
            ("youth", "marcus", "Email parents the Fall Fest details", 1, TodoStatus.OPEN),
        ]
        for team, owner, title, due, status in loose:
            db.add(
                Todo(team_id=teams[team].id, owner_id=users[owner].id, title=title,
                     due_date=d(due), status=status)
            )

        # --- Meetings: weekly L10s, last few completed, next one scheduled ---
        weekday = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3}
        for key, _name, day in TEAMS:
            last = TODAY - timedelta(days=(TODAY.weekday() - weekday[day]) % 7)
            for weeks_back in range(5, -1, -1):
                held = last - timedelta(weeks=weeks_back)
                start_at = datetime.combine(held, time(18, 30), tzinfo=timezone.utc)
                steps = [300, 285, 320, 2400 + weeks_back * 90, 540, 180]
                db.add(
                    Meeting(
                        team_id=teams[key].id,
                        scheduled_date=held,
                        status=MeetingStatus.COMPLETED,
                        started_at=start_at,
                        finished_at=start_at + timedelta(seconds=sum(steps)),
                        stopped_at=start_at + timedelta(seconds=sum(steps)),
                        current_step=5,
                        step_seconds=steps,
                    )
                )
            db.add(
                Meeting(
                    team_id=teams[key].id,
                    scheduled_date=last + timedelta(weeks=1),
                    status=MeetingStatus.SCHEDULED,
                )
            )

        # --- People Analyzer ---
        def values(team: str, *ratings: bool) -> dict:
            return {v["name"]: r for v, r in zip(VTOS[team]["core_values"], ratings)}

        evaluated = TODAY - timedelta(days=25)
        analyzer = [
            ("linda", "integrator", "council", True, True, True, (True, True, True), None),
            ("harold", "treasurer", "council", True, True, True, (True, True, True), None),
            ("esther", "benevolence", "council", True, True, False, (True, True, True),
             "Stretched thin with Thanksgiving adoptions"),
            ("bob", "men_dir", "men", True, True, True, (True, True, True), None),
            ("frank", "facilities", "men", True, False, True, (True, True, False),
             "Slow to close out the roof repair; pursue a bid decision"),
            ("carol", "women_dir", "women", True, True, False, (True, True, True),
             "Nursery coverage is dragging on capacity"),
            ("dolores", "kitchen", "women", True, True, True, (True, True, True), None),
            ("marcus", "youth_dir", "youth", True, True, True, (True, True, True), None),
            ("kayla", "media", "youth", True, True, True, (True, True, True), "Great growth this year"),
        ]
        for person, seat, team, gets, wants, cap, ratings, notes in analyzer:
            db.add(
                PeopleAnalyzerEntry(
                    user_id=users[person].id,
                    seat_id=seats[seat].id,
                    evaluated_at=evaluated,
                    gets_it=gets,
                    wants_it=wants,
                    has_capacity=cap,
                    core_values_ratings=values(team, *ratings),
                    notes=notes,
                )
            )

        db.commit()

        print(f"Demo data seeded for {org.name} ({org.id})")
        print("Teams: " + ", ".join(t.name for t in teams.values()))
        print(f"\nLog in as any of these (password: {DEMO_PASSWORD}):")
        for key, _n, local, role, *_ in PEOPLE:
            print(f"  {local}@{DOMAIN}  [{role.value}]")
    finally:
        db.close()


if __name__ == "__main__":
    main()
