"""
KFUPM Dean's List with Distinction - Extracurricular Submission & Review
Streamlit version 2 (supervisor comments applied).

Run with:   streamlit run app.py

Pages (chosen in the sidebar):
  1. Student Form       - students submit activities + upload evidence
  2. Reviewer Dashboard - password protected; verify activities, see summary

Points are NOT shown to students. They are still stored and used by the
Reviewer Dashboard to calculate the 5-point result (Committee Report, s.3.3).
"""

import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ----------------------------------------------------------------------------
# 1. SETTINGS  (change things here, not deep in the code)
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Dean's List with Distinction", page_icon="🎓")

DB_PATH = "deanslist.db"          # SQLite database file (created automatically)
UPLOAD_DIR = Path("uploads")      # evidence files are saved here
UPLOAD_DIR.mkdir(exist_ok=True)

TERM = "Term 261"                 # saved automatically with every submission
THRESHOLD = 5                     # minimum verified points
MAX_FILE_MB = 10
MAX_ENTRIES = 5                   # max entries a student can add per section

DEPARTMENTS = [
    "Architectural Engineering and Construction Management Department",
    "Architecture and City Design Department",
    "Civil and Environmental Engineering Department",
    "Integrated Design Department",
]

# Maximum points counted per category per semester (Committee Report, s.3.3)
CAPS = {
    "Leadership": 3,
    "Active Engagement": 2,
    "Participation": 2,
    "Competitions & Achievements": 3,
    "Community Service": 2,
    "Research & Innovation": 3,
}

DECISIONS = ["Pending", "Verified", "Further evidence required", "Rejected"]

OTHER = "Other (please specify)"   # added to the end of every dropdown

# --- Dropdown lists ---------------------------------------------------------
# Options containing "(specify" make a text box appear so the student can type
# the exact name. Edit these lists freely (keep the quotes and commas).

# Same list everywhere "Verifying university unit" is used (Report s.3.3:
# only evidence issued or confirmed by a University unit is accepted).
VERIFYING_UNITS = [
    "Deanship of Student Affairs",
    "Relevant Academic Department",
    "Faculty Advisor of a Recognized Student Organization",
    "Coach of an Official University Sports Team",
    "Supervising Faculty Member",
    "Organizing University Unit",
]

PROFESSIONAL_CHAPTERS = [
    "ASCE Student Chapter",
    "ASHRAE Student Chapter",
    "ACI Student Chapter",
    "PMI Student Chapter",
    "IEEE Student Branch",
    "AIAS Chapter (Architecture Students)",
    "IIDA Student Chapter (Interior Design)",
    "CIOB Student Chapter",
    "RICS Student Chapter",
]

MAJOR_ROLES = ["President", "Vice President", "Team Captain", "Student Council Member"]
SUPPORT_ROLES = ["Committee Lead", "Event Organizer", "Project Lead"]

MAJOR_ORGS = (
    ["Student Council"] + PROFESSIONAL_CHAPTERS + [
        "University-recognized student club (specify name)",
        "Official University sports team (specify sport)",
        "University committee (specify name)",
    ]
)
SUPPORT_ORGS = (
    ["Student Council"] + PROFESSIONAL_CHAPTERS + [
        "University-recognized student club (specify name)",
        "University event or initiative (specify name)",
        "University committee (specify name)",
        "University project team (specify name)",
    ]
)
ENGAGEMENT_ORGS = PROFESSIONAL_CHAPTERS + [
    "University-recognized student club (specify name)",
    "Department student club or society (specify name)",
    "Official University sports team (specify sport)",
]

LEADERSHIP_RESPONSIBILITIES = [
    "Leading or supervising a team",
    "Planning activities or events",
    "Coordinating committee work",
    "Managing a project",
    "Representing students or an organization",
    "Making or implementing decisions",
]
ENGAGEMENT_TYPES = ["University-recognized club", "Student organization",
                    "Official University sports team"]
ENGAGEMENT_ROLES = ["Active member", "Team member", "Club member", "Regular participant"]
ENGAGEMENT_PARTICIPATION = [
    "Attended regular meetings or training",
    "Participated in organized activities",
    "Contributed to club or team tasks",
    "Represented the organization or team",
]
PARTICIPATION_TYPES = ["Event", "Workshop", "Seminar", "Exhibition",
                       "Competition participation", "Delegation"]
PARTICIPATION_ROLES = ["Attendee", "Participant", "Presenter", "Delegate"]
COMP_TYPES = ["Competition placement", "Academic award", "Extracurricular award"]
COMP_TITLES = {
    "Competition placement": [
        "ASHRAE Student Design Competition",
        "ASCE Concrete Canoe Competition",
        "ASCE Steel Bridge Competition",
        "ACI Student Concrete Competition",
        "ASC Student Competition (construction management)",
        "Architecture or Urban Design Competition",
        "Interior Design Competition",
        "Sustainability or Green Building Competition",
        "Hackathon or Innovation Challenge",
        "Case Study or Business Competition",
    ],
    "Academic award": [
        "University Academic Excellence Award",
        "College Academic Excellence Award",
        "Departmental Academic Award",
        "Best Design or Capstone Project Award",
    ],
    "Extracurricular award": [
        "University Student Activities Award",
        "Outstanding Student Leader Award",
        "Outstanding Volunteer Award",
        "Sports Achievement Award",
    ],
}
COMP_RESULTS = ["Winner", "Runner-up", "Recognized placement", "Formal award recipient"]
COMMUNITY_TYPES = ["Volunteering", "Outreach programme", "Social initiative"]
COMMUNITY_ROLES = ["Volunteer", "Organizer", "Team member", "Coordinator"]
COMMUNITY_CONTRIBUTIONS = [
    "Direct community service", "Event or activity support", "Coordination",
    "Awareness or outreach", "Logistical support",
]
RESEARCH_TYPES = ["Research project", "Innovation challenge",
                  "Publication (journal or conference paper)"]
RESEARCH_CONTRIBUTIONS = [
    "Literature review", "Data collection", "Data analysis",
    "Design or development", "Experimentation or testing",
    "Report or manuscript preparation", "Presentation",
]

# Descriptions reused in every section (keeps wording consistent)
UNIT_DESC = ("Select the University unit that issued or confirmed your evidence. "
             "Self-declared activities without confirmation are not counted.")
VERIFIER_DESC = ("Name or email of the person who can confirm this activity. "
                 "Example: your faculty advisor or a Student Affairs officer.")
VERIFIER_PLACEHOLDER = "e.g., Dr. Ahmed Ali or name@kfupm.edu.sa"


def admin_password() -> str:
    """Reviewer password: from environment variable, secrets file, or default."""
    pw = os.environ.get("ADMIN_PASSWORD")
    if pw:
        return pw
    try:
        return st.secrets["ADMIN_PASSWORD"]
    except Exception:
        return "admin123"  # CHANGE THIS before real use


# ----------------------------------------------------------------------------
# 2. DATABASE
# ----------------------------------------------------------------------------
def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                name TEXT,
                student_id TEXT,
                email TEXT,
                department TEXT,
                semester TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id TEXT,
                category TEXT,
                role TEXT,
                title TEXT,
                details TEXT,
                verifier TEXT,
                evidence_path TEXT,
                points INTEGER,
                decision TEXT DEFAULT 'Pending',
                comments TEXT DEFAULT '',
                reviewed_by TEXT DEFAULT '',
                review_date TEXT DEFAULT ''
            )"""
        )


init_db()


# ----------------------------------------------------------------------------
# 3. WIDGET HELPERS  (every field = bold label + short description + input)
# ----------------------------------------------------------------------------
if "form_n" not in st.session_state:
    st.session_state.form_n = 0  # bumping this number resets every widget


def k(name: str) -> str:
    """Unique widget key. Changing form_n gives a fresh, empty form."""
    return f"{name}_{st.session_state.form_n}"


def lbl(label: str, desc: str = None):
    st.markdown(f"**{label}**")
    if desc:
        st.caption(desc)


def yes_no(question: str, key: str) -> bool:
    st.markdown(f"**{question}**")
    return st.radio(question, ["No", "Yes"], horizontal=True, key=k(key),
                    label_visibility="collapsed") == "Yes"


def text(label, desc, key, placeholder=None) -> str:
    lbl(label, desc)
    return st.text_input(label, key=k(key), placeholder=placeholder,
                         label_visibility="collapsed").strip()


def dropdown(label, desc, options, key) -> str:
    """Dropdown that always ends with 'Other'. Returns '' if incomplete."""
    lbl(label, desc)
    picked = st.selectbox(label, list(options) + [OTHER], index=None,
                          placeholder="Select...", key=k(key),
                          label_visibility="collapsed")
    if picked is None:
        return ""
    if picked == OTHER:
        return st.text_input("Please specify", key=k(key + "_x"),
                             placeholder="Type here").strip()
    if "(specify" in picked:
        base = picked.split(" (specify")[0]
        hint = picked.split("(specify")[1].rstrip(")").strip()
        extra = st.text_input(f"Please specify the {hint or 'name'}", key=k(key + "_x"),
                              placeholder="Type here").strip()
        return f"{base}: {extra}" if extra else ""
    return picked


def multiselect(label, desc, options, key) -> str:
    lbl(label, desc)
    picked = st.multiselect(label, list(options) + [OTHER], key=k(key),
                            placeholder="Select one or more...",
                            label_visibility="collapsed")
    values = [p for p in picked if p != OTHER]
    if OTHER in picked:
        extra = st.text_input("Please specify", key=k(key + "_x"),
                              placeholder="Type here").strip()
        if extra:
            values.append(extra)
    return ", ".join(values)


def date_field(label, desc, key):
    lbl(label, desc)
    return st.date_input(label, value=None, key=k(key), label_visibility="collapsed")


def evidence_field(desc, key):
    lbl(f"Evidence (PDF or image, max {MAX_FILE_MB} MB)", desc)
    return st.file_uploader("Evidence", type=["pdf", "png", "jpg", "jpeg"], key=k(key),
                            label_visibility="collapsed")


def join(*parts) -> str:
    return " | ".join(str(p) for p in parts if p)


def make_activity(category, where, points, title, role, details, verifier,
                  evidence, req, hours=None) -> dict:
    """req = {field label: value}; used to say exactly what is missing."""
    return dict(category=category, where=where, points=points, title=title.strip(),
                role=role, details=details, verifier=verifier, evidence=evidence,
                req=req, hours=hours)


def repeat_entries(key, first_q, more_q, entry_title, block_fn) -> list:
    """Ask first_q. If Yes, show the block; then ask more_q (add another or move on)."""
    entries = []
    question = first_q
    for n in range(1, MAX_ENTRIES + 1):
        if not yes_no(question, f"{key}_gate{n}"):
            break
        with st.container(border=True):
            if n > 1:
                st.markdown(f"#### {entry_title} - entry {n}")
            entries.append(block_fn(f"{key}{n}", f"{entry_title} (entry {n})"))
        question = more_q
    return entries


# ----------------------------------------------------------------------------
# 4. ONE BLOCK OF FIELDS PER CATEGORY
# ----------------------------------------------------------------------------
def leadership_block(p, where, major: bool):
    if major:
        role = dropdown("Your role",
                        "Select the major position you held during " + TERM +
                        ". Example: Club President.", MAJOR_ROLES, f"{p}_role")
        org = dropdown("Organization, team, committee or event",
                       "Select the exact official body where you held this role. "
                       "Example: ASCE Student Chapter. If it is not listed, choose "
                       "Other and type its exact official name.", MAJOR_ORGS, f"{p}_org")
    else:
        role = dropdown("Your role",
                        "Select the supporting position you held during " + TERM +
                        ". Example: Event Organizer.", SUPPORT_ROLES, f"{p}_role")
        org = dropdown("Organization, team, committee or event",
                       "Select the exact official body or event where you held this "
                       "supporting role. Example: ASHRAE Student Chapter. If it is not "
                       "listed, choose Other and type its exact official name.",
                       SUPPORT_ORGS, f"{p}_org")
    resp = multiselect("Responsibilities",
                       "Select what you actually did in this role. "
                       "Example: Planning activities or events.",
                       LEADERSHIP_RESPONSIBILITIES, f"{p}_resp")
    unit = dropdown("Verifying university unit", UNIT_DESC, VERIFYING_UNITS, f"{p}_unit")
    ver = text("Verifier name or email", VERIFIER_DESC, f"{p}_ver", VERIFIER_PLACEHOLDER)
    ev = evidence_field("Appointment or election letter, or confirmation from the faculty "
                        "advisor or the Deanship of Student Affairs, stating your role and "
                        "the semester.", f"{p}_ev")
    return make_activity(
        "Leadership", where, 3 if major else 2, org, role, resp, join(unit, ver), ev,
        {"Role": role, "Organization, team, committee or event": org,
         "Responsibilities": resp, "Verifying university unit": unit,
         "Verifier name or email": ver})


def engagement_block(p, where):
    atype = dropdown("Active engagement type",
                     "Select the kind of group you belong to. Examples: Student "
                     "organization (ASCE Student Chapter), Official University sports team.",
                     ENGAGEMENT_TYPES, f"{p}_type")
    org = dropdown("Club, organization or team name",
                   "Select the exact official name of the group. If it is not listed, "
                   "choose Other and type its exact official name.",
                   ENGAGEMENT_ORGS, f"{p}_org")
    role = dropdown("Membership or role",
                    "Select your registered status. Example: Active member.",
                    ENGAGEMENT_ROLES, f"{p}_role")
    part = multiselect("Regular participation",
                       "Select how you took part throughout the semester. "
                       "Example: Attended regular meetings or training.",
                       ENGAGEMENT_PARTICIPATION, f"{p}_part")
    unit = dropdown("Verifying university unit", UNIT_DESC, VERIFYING_UNITS, f"{p}_unit")
    ver = text("Verifier name or email", VERIFIER_DESC, f"{p}_ver", VERIFIER_PLACEHOLDER)
    ev = evidence_field("Membership record or letter from the faculty advisor, coach or the "
                        "Deanship of Student Affairs confirming regular participation "
                        "during the semester.", f"{p}_ev")
    return make_activity(
        "Active Engagement", where, 2, org, join(atype, role), part, join(unit, ver), ev,
        {"Active engagement type": atype, "Club, organization or team name": org,
         "Membership or role": role, "Regular participation": part,
         "Verifying university unit": unit, "Verifier name or email": ver})


def participation_block(p, where):
    ptype = dropdown("Participation type",
                     "Select the kind of activity. Examples: Workshop, Seminar, Exhibition.",
                     PARTICIPATION_TYPES, f"{p}_type")
    title = text("Activity title",
                 "Write the title exactly as it appears on your certificate or attendance "
                 "record. Example: BIM Fundamentals Workshop.", f"{p}_title",
                 "Activity title")
    d = date_field("Date", "Date of the activity. It must fall within " + TERM + ".",
                   f"{p}_date")
    involvement = dropdown("Involvement",
                           "Select how you took part. Examples: Attendee (listened at a "
                           "seminar), Participant (joined workshop activities), Presenter "
                           "(presented a poster), Delegate (represented the University).",
                           PARTICIPATION_ROLES, f"{p}_role")
    unit = dropdown("Verifying university unit", UNIT_DESC, VERIFYING_UNITS, f"{p}_unit")
    ev = evidence_field("Certificate of attendance or participation, or the organizer's "
                        "official attendance record.", f"{p}_ev")
    return make_activity(
        "Participation", where, 1, title, join(ptype, involvement), str(d) if d else "",
        unit, ev,
        {"Participation type": ptype, "Activity title": title, "Date": d,
         "Involvement": involvement, "Verifying university unit": unit})


def competition_block(p, where):
    ctype = dropdown("Type",
                     "Select what you achieved. Examples: Competition placement (first "
                     "place in a design competition), Academic award (College excellence "
                     "award).", COMP_TYPES, f"{p}_type")
    if ctype:
        title = dropdown("Official title",
                         "Select the official name of the competition or award. If it is "
                         "not listed, choose Other and type the official title.",
                         COMP_TITLES.get(ctype, []), f"{p}_title")
    else:
        lbl("Official title", "Select the type above first.")
        title = ""
    result = dropdown("Result or achievement received",
                      "Select your result. Examples: Winner, Runner-up, Formal award "
                      "recipient.", COMP_RESULTS, f"{p}_result")
    d = date_field("Date", "Date of the competition result or award. It must fall within "
                   + TERM + ".", f"{p}_date")
    unit = dropdown("Verifying university unit", UNIT_DESC, VERIFYING_UNITS, f"{p}_unit")
    ev = evidence_field("Official results list, award letter or certificate from the "
                        "organizing body, confirmed by the department or the Deanship of "
                        "Student Affairs.", f"{p}_ev")
    return make_activity(
        "Competitions & Achievements", where, 3, title, join(ctype, result),
        str(d) if d else "", unit, ev,
        {"Type": ctype, "Official title": title, "Result or achievement": result,
         "Date": d, "Verifying university unit": unit})


def community_block(p, where):
    ctype = dropdown("Type",
                     "Select the kind of service. Examples: Volunteering at a University "
                     "event, Outreach programme in a school, Social initiative such as a "
                     "charity drive.", COMMUNITY_TYPES, f"{p}_type")
    title = text("Activity title",
                 "Write the official name of the activity as it appears on your letter or "
                 "certificate. Example: Ramadan Food Distribution Campaign.", f"{p}_title",
                 "Activity title")
    unit = dropdown("Verifying university unit", UNIT_DESC, VERIFYING_UNITS, f"{p}_unit")
    role = dropdown("Your role",
                    "Select your role in the activity. Example: Volunteer.",
                    COMMUNITY_ROLES, f"{p}_role")
    contrib = multiselect("Contribution",
                          "Select what you did. Examples: Direct community service "
                          "(serving beneficiaries), Logistical support (preparing materials).",
                          COMMUNITY_CONTRIBUTIONS, f"{p}_contrib")
    period = text("Date or service period",
                  "Write the date or period exactly as stated in your evidence. "
                  "Example: 10-12 November.", f"{p}_period", "Date or period")
    lbl("Service hours", "Total hours as stated in your evidence. Example: 6.")
    hours = st.number_input("Service hours", min_value=0.0, step=0.5, key=k(f"{p}_hours"),
                            label_visibility="collapsed")
    ev = evidence_field("Letter or certificate from the organizing unit stating the activity, "
                        "dates and hours of service.", f"{p}_ev")
    return make_activity(
        "Community Service", where, 2, title, join(ctype, role),
        join(contrib, period, f"{hours:g} hours"), unit, ev,
        {"Type": ctype, "Activity title": title, "Verifying university unit": unit,
         "Your role": role, "Contribution": contrib, "Date or service period": period},
        hours=hours)


def research_block(p, where):
    rtype = dropdown("Type",
                     "Select the kind of activity. Examples: Research project, Innovation "
                     "challenge, Publication.", RESEARCH_TYPES, f"{p}_type")
    title = text("Official title",
                 "Write the official title of the project, challenge or publication. "
                 "Example: Thermal Performance of Recycled Aggregate Concrete.",
                 f"{p}_title", "Official title")
    contrib = multiselect("Your contribution",
                          "Select what you contributed. Examples: Data collection, "
                          "Experimentation or testing.", RESEARCH_CONTRIBUTIONS,
                          f"{p}_contrib")
    sup = text("Supervising faculty member (name or email)",
               "The faculty member who supervised this work and can confirm your "
               "contribution.", f"{p}_sup", VERIFIER_PLACEHOLDER)
    d = date_field("Research activity or submission date",
                   "Date of the activity or of the publication/submission. It must fall "
                   "within " + TERM + ".", f"{p}_date")
    ev = evidence_field("Letter from the supervising faculty member describing your "
                        "contribution, or the publication or submission record.", f"{p}_ev")
    return make_activity(
        "Research & Innovation", where, 3, title, rtype,
        join(contrib, str(d) if d else ""), join("Supervising Faculty Member", sup), ev,
        {"Type": rtype, "Official title": title, "Your contribution": contrib,
         "Supervising faculty member": sup, "Date": d})


# ----------------------------------------------------------------------------
# 5. STUDENT FORM PAGE
# ----------------------------------------------------------------------------
def student_form_page():
    st.title(f"Dean's List with Distinction — Extracurricular Activity Submission Form — {TERM}")
    st.info(
        "Use this form to report verified extracurricular activities completed during the "
        "academic semester selected below. All activities must relate to that same semester "
        "and be supported by official evidence. Each activity may be counted once only, under "
        "the single category that best describes it. A minimum of 5 verified extracurricular "
        "points is required for the extracurricular component; academic eligibility is "
        "assessed separately."
    )

    if st.session_state.get("submitted_id"):
        st.success("Your submission has been received. All activities and evidence remain "
                   "subject to official review and verification.")
        st.code(st.session_state.submitted_id, language=None)
        st.caption("Keep this reference number.")
        if st.button("Submit another response"):
            st.session_state.submitted_id = None
            st.rerun()
        return

    activities = []

    # ---- Student information ------------------------------------------------
    st.header("Student Information")
    st.caption("Enter the information exactly as shown in your University record. All "
               "reported activities must relate to the relevant semester.")
    name = text("Student full name", None, "name")
    student_id = text("Student ID", "Digits only.", "sid")
    email = text("KFUPM email address", "Must end with @kfupm.edu.sa.", "email")
    lbl("Academic department")
    department = st.selectbox("Academic department", DEPARTMENTS, index=None,
                              placeholder="Select...", key=k("dept"),
                              label_visibility="collapsed")

    # ---- 1. Leadership ------------------------------------------------------
    st.header("1. Leadership")
    st.caption("Leadership means an elected or appointed position with defined "
               "responsibilities in a University-recognized organization, team, committee "
               "or event (Example: Club President, Vice President, Team Captain).  \n"
               "If you held more than one role in the same activity (for example, club "
               "president and club member), report only the highest role.")

    st.subheader("Major Leadership Role")
    st.caption("A top elected or appointed position with overall responsibility. "
               "Examples: Club President, Vice President, Team Captain, Student Council "
               "Member.")
    activities += repeat_entries(
        "major", "Do you have a major leadership role to report?",
        "Do you have any additional major leadership role to report?",
        "Major Leadership Role", lambda p, w: leadership_block(p, w, True))

    st.subheader("Supporting Leadership Role")
    st.caption("Report a separate supporting role only. If it is the same activity as the "
               "major role, it will not receive additional points. Examples: Committee "
               "Lead, Event Organizer, Project Lead.")
    activities += repeat_entries(
        "support", "Do you have a supporting leadership role to report?",
        "Do you have any additional supporting leadership role to report?",
        "Supporting Leadership Role", lambda p, w: leadership_block(p, w, False))

    # ---- 2. Active engagement -------------------------------------------------
    st.header("2. Active Engagement")
    st.caption("Registered membership in a University-recognized club, student organization "
               "or official University sports team, with regular participation throughout "
               "the semester. Examples: active member of the ASCE Student Chapter, member "
               "of an official University football team.  \n"
               "If you also held a leadership role in the same group, report it under "
               "1. Leadership only.")
    activities += repeat_entries(
        "active", "Do you have an active engagement to report?",
        "Do you have any additional active engagement to report?",
        "Active Engagement", engagement_block)

    # ---- 3. Participation -------------------------------------------------------
    st.header("3. Participation")
    st.caption("Attendance at, or one-time participation in, a University-recognized event, "
               "workshop, seminar, exhibition or competition. Examples: attending a BIM "
               "workshop, visiting a design exhibition, taking part in a competition "
               "without placing.  \nIf you won or placed in a competition, report it "
               "under 4. Competitions and Achievements instead.")
    activities += repeat_entries(
        "part", "Do you have a participation activity to report?",
        "Do you have any additional participation activity to report?",
        "Participation Activity", participation_block)

    # ---- 4. Competitions --------------------------------------------------------
    st.header("4. Competitions and Achievements")
    st.caption("Winning or placing in a recognized academic or extracurricular competition, "
               "or receiving a formal award. Examples: first place in the ASHRAE Student "
               "Design Competition, a College academic excellence award.")
    activities += repeat_entries(
        "comp", "Do you have a competition or achievement to report?",
        "Do you have any additional competition or achievement to report?",
        "Competition or Achievement", competition_block)

    # ---- 5. Community service ---------------------------------------------------
    st.header("5. Community Service")
    st.caption("Volunteering in a service, outreach or social initiative organized or "
               "endorsed by the University. Examples: volunteering at a University "
               "community event, a school outreach programme, a charity drive endorsed by "
               "Student Affairs.")
    activities += repeat_entries(
        "comm", "Do you have a community service activity to report?",
        "Do you have any additional community service activity to report?",
        "Community Service Activity", community_block)

    # ---- 6. Research ------------------------------------------------------------
    st.header("6. Research and Innovation")
    st.caption("A contribution to a research project, innovation challenge or publication "
               "under the supervision of a faculty member. Examples: assisting a faculty "
               "member's research project, joining an innovation challenge team, "
               "co-authoring a conference paper.")
    activities += repeat_entries(
        "res", "Do you have a research or innovation activity to report?",
        "Do you have any additional research or innovation activity to report?",
        "Research or Innovation Activity", research_block)

    # ---- Declaration & submit ---------------------------------------------------
    st.header("Declaration")
    declared = st.checkbox(
        f"I certify that the information and supporting evidence are accurate, relate to "
        f"{TERM}, and have not been claimed under another category. I understand that "
        f"points remain provisional until official verification.",
        key=k("declare"))

    if st.button("Submit", type="primary"):
        errors = validate(name, student_id, email, department, activities, declared)
        if errors:
            st.error("Please fix the following before submitting:")
            for e in errors:
                st.write(f"- {e}")
        else:
            sub_id = save_submission(name, student_id, email, department, activities)
            st.session_state.submitted_id = sub_id
            st.session_state.form_n += 1  # next time, form is blank
            st.rerun()


def validate(name, sid, email, dept, activities, declared) -> list:
    errors = []
    if not name.strip():
        errors.append("Student full name is required.")
    if not re.fullmatch(r"[0-9]{6,12}", sid.strip()):
        errors.append("Student ID must be 6-12 digits.")
    if not re.fullmatch(r"[A-Za-z0-9._%+-]+@kfupm\.edu\.sa", email.strip()):
        errors.append("Enter a valid @kfupm.edu.sa email address.")
    if not dept:
        errors.append("Academic department is required.")

    for a in activities:
        w = a["where"]
        for label, value in a["req"].items():
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{w}: '{label}' is required.")
        if a["evidence"] is None:
            errors.append(f"{w}: evidence file is required.")
        elif a["evidence"].size > MAX_FILE_MB * 1024 * 1024:
            errors.append(f"{w}: file is larger than {MAX_FILE_MB} MB.")
        if a.get("hours") is not None and a["hours"] <= 0:
            errors.append(f"{w}: service hours must be greater than zero.")

    if not activities:
        errors.append("Report at least one activity (answer Yes in at least one section).")
    if not declared:
        errors.append("You must accept the declaration.")
    return errors


def save_submission(name, sid, email, dept, activities) -> str:
    sub_id = uuid.uuid4().hex[:10].upper()
    folder = UPLOAD_DIR / sub_id
    folder.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO submissions VALUES (?,?,?,?,?,?,?)",
            (sub_id, datetime.now().isoformat(timespec="seconds"), name.strip(), sid.strip(),
             email.strip().lower(), dept, TERM))
        for i, a in enumerate(activities, start=1):
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", a["evidence"].name)
            path = folder / f"{i}_{safe}"
            path.write_bytes(a["evidence"].getbuffer())
            conn.execute(
                """INSERT INTO activities
                   (submission_id, category, role, title, details, verifier, evidence_path, points)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (sub_id, a["category"], a["role"], a["title"], a["details"], a["verifier"],
                 str(path), a["points"]))
    return sub_id


# ----------------------------------------------------------------------------
# 6. REVIEWER DASHBOARD
# ----------------------------------------------------------------------------
def build_summary() -> pd.DataFrame:
    """One row per student submission, with capped points and eligibility result."""
    with get_conn() as conn:
        subs = pd.read_sql("SELECT * FROM submissions ORDER BY timestamp DESC", conn)
        acts = pd.read_sql("SELECT * FROM activities", conn)
    rows = []
    for _, s in subs.iterrows():
        a = acts[acts.submission_id == s["id"]]
        row = {"Submission ID": s["id"], "Timestamp": s["timestamp"], "Student Name": s["name"],
               "Student ID": s["student_id"], "Email": s["email"],
               "Department": s["department"], "Term": s["semester"]}
        total = 0
        for cat, cap in CAPS.items():
            verified = a[(a.category == cat) & (a.decision == "Verified")].points.sum()
            row[cat] = min(cap, int(verified))
            total += row[cat]
        row["Total Verified Points"] = total
        decisions = set(a.decision)
        if "Pending" in decisions:
            status = "Pending review"
        elif "Further evidence required" in decisions:
            status = "Further evidence required"
        else:
            status = "Review complete"
        row["Review Status"] = status
        if status != "Review complete":
            row["Eligibility Result"] = status
        elif total >= THRESHOLD:
            row["Eligibility Result"] = "Extracurricular requirement satisfied"
        else:
            row["Eligibility Result"] = "Extracurricular requirement not satisfied"
        rows.append(row)
    return pd.DataFrame(rows)


def reviewer_page():
    st.title("🧑‍🏫 Reviewer Dashboard")

    if not st.session_state.get("is_reviewer"):
        pw = st.text_input("Reviewer password", type="password")
        if st.button("Log in"):
            if pw == admin_password():
                st.session_state.is_reviewer = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        return

    if st.sidebar.button("Log out"):
        st.session_state.is_reviewer = False
        st.rerun()

    reviewer = st.text_input("Your name / email (recorded with each decision)")
    tab_review, tab_summary = st.tabs(["Review activities", "Student summary"])

    summary = build_summary()

    # ---- Tab 1: review each activity -------------------------------------------
    with tab_review:
        if summary.empty:
            st.info("No submissions yet.")
        else:
            options = {
                f"{r['Student Name']} ({r['Student ID']}) - {r['Term']} - {r['Review Status']}":
                    r["Submission ID"] for _, r in summary.iterrows()
            }
            choice = st.selectbox("Select a submission", list(options))
            sub_id = options[choice]
            with get_conn() as conn:
                acts = pd.read_sql("SELECT * FROM activities WHERE submission_id=?", conn,
                                   params=(sub_id,))
            # Committee Report s.3.2: an activity earns points once, under one
            # category; if the same activity has several roles, only the highest counts.
            name_counts = acts.title.str.strip().str.lower().value_counts()
            for _, a in acts.iterrows():
                with st.expander(f"{a['category']} - {a['title']}  [{a['decision']}]",
                                 expanded=a["decision"] == "Pending"):
                    if name_counts.get(a["title"].strip().lower(), 0) > 1:
                        st.warning("The same name appears in more than one entry of this "
                                   "submission. If it is the same activity, only the "
                                   "highest-scoring role/category may be verified.")
                    st.write(f"**Role/Type:** {a['role']}")
                    st.write(f"**Details:** {a['details']}")
                    st.write(f"**Verification source:** {a['verifier']}")
                    st.write(f"**Available points:** {a['points']}")
                    path = Path(a["evidence_path"])
                    if path.exists():
                        st.download_button("📎 Download evidence", path.read_bytes(),
                                           file_name=path.name, key=f"dl_{a['id']}")
                    else:
                        st.warning("Evidence file not found on disk.")
                    decision = st.selectbox("Review decision", DECISIONS,
                                            index=DECISIONS.index(a["decision"]),
                                            key=f"dec_{a['id']}")
                    comment = st.text_area("Reviewer comments", value=a["comments"],
                                           key=f"com_{a['id']}")
                    if st.button("Save decision", key=f"save_{a['id']}"):
                        if not reviewer.strip():
                            st.error("Enter your name/email at the top first.")
                        else:
                            stamp = (datetime.now().isoformat(timespec="seconds")
                                     if decision != "Pending" else "")
                            with get_conn() as conn:
                                conn.execute(
                                    """UPDATE activities SET decision=?, comments=?,
                                       reviewed_by=?, review_date=? WHERE id=?""",
                                    (decision, comment,
                                     reviewer.strip() if decision != "Pending" else "",
                                     stamp, int(a["id"])))
                            st.success("Saved.")
                            st.rerun()

    # ---- Tab 2: summary ----------------------------------------------------------
    with tab_summary:
        if summary.empty:
            st.info("No submissions yet.")
        else:
            st.caption(f"Points are capped per category. Threshold: {THRESHOLD} verified points.")
            st.dataframe(summary, hide_index=True)
            st.download_button("⬇️ Download summary (CSV)",
                               summary.to_csv(index=False).encode("utf-8-sig"),
                               file_name="student_summary.csv", mime="text/csv")


# ----------------------------------------------------------------------------
# 7. NAVIGATION
# ----------------------------------------------------------------------------
page = st.sidebar.radio("Go to", ["Student Form", "Reviewer Dashboard"])
if page == "Student Form":
    student_form_page()
else:
    reviewer_page()