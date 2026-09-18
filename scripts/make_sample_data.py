"""Generate the client's "raw exports".

Every defect in here is deliberate and exists to exercise exactly one branch of
the escalation policy in app/policy.py. The mapping from defect to expected agent
behaviour is asserted in tests/test_golden_run.py, so if the policy drifts, the
tests fail.

    uv run python scripts/make_sample_data.py

Emits:
    data/legacy_hris_export.csv   - old HRMS export, comma separated
    data/payroll_system.xlsx      - payroll team's spreadsheet
    data/broken_export.csv        - wrong file entirely; used to demo the circuit breaker
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"

# --------------------------------------------------------------------------
# Canonical roster. This is ground truth; the exports below corrupt it in
# specific, documented ways.
# --------------------------------------------------------------------------
# (code, first, last, dept, designation, grade, city, gender, emp_type, doj, dob)
ROSTER = [
    ("E1001", "Aarav",    "Sharma",     "Engineering",      "Senior Software Engineer", "L4", "Bengaluru", "Male",   "Permanent", (15, 3, 2021), (23, 7, 1990)),
    ("E1002", "Diya",     "Patel",      "Engineering",      "Software Engineer",        "L3", "Bengaluru", "Female", "Permanent", (2, 11, 2022), (14, 2, 1995)),
    ("E1003", "Rohan",    "Mehta",      "Sales",            "Account Executive",        "S3", "Mumbai",    "Male",   "Permanent", (21, 6, 2020), (30, 9, 1988)),
    ("E1004", "Ananya",   "Iyer",       "Human Resources",  "HR Business Partner",      "M2", "Hyderabad", "Female", "Permanent", (5, 4, 2019),  (17, 5, 1987)),
    ("E1005", "Vikram",   "Nair",       "Finance",          "Financial Analyst",        "L3", "Mumbai",    "Male",   "Permanent", (18, 8, 2021), (2, 12, 1992)),
    ("E1006", "Sneha",    "Reddy",      "Marketing",        "Marketing Manager",        "M1", "Hyderabad", "Female", "Permanent", (9, 1, 2020),  (26, 3, 1991)),
    ("E1007", "Arjun",    "Kulkarni",   "Engineering",      "Engineering Manager",      "M3", "Pune",      "Male",   "Permanent", (14, 7, 2018), (8, 8, 1985)),
    ("E1008", "Ishita",   "Bose",       "Customer Success", "Customer Success Manager", "M1", "Kolkata",   "Female", "Permanent", (23, 2, 2022), (19, 11, 1993)),
    ("E1009", "Karthik",  "Subramanian","Engineering",      "Staff Engineer",           "L5", "Chennai",   "Male",   "Permanent", (30, 5, 2017), (4, 6, 1984)),
    ("E1010", "Meera",    "Joshi",      "Operations",       "Operations Executive",     "L2", "Pune",      "Female", "Permanent", (11, 9, 2023), (21, 1, 1997)),
    ("E1011", "Siddharth","Rao",        "Sales",            "Regional Sales Manager",   "M2", "Bengaluru", "Male",   "Permanent", (25, 10, 2019),(13, 4, 1986)),
    ("E1012", "Priya",    "Menon",      "Legal",            "Legal Counsel",            "M2", "Mumbai",    "Female", "Permanent", (7, 3, 2021),  (29, 8, 1989)),
    ("E1013", "Nikhil",   "Agarwal",    "Finance",          "Finance Manager",          "M2", "Delhi",     "Male",   "Permanent", (16, 12, 2018),(11, 10, 1986)),
    ("E1014", "Tanvi",    "Desai",      "Marketing",        "Content Strategist",       "L3", "Bengaluru", "Female", "Permanent", (3, 7, 2022),  (24, 2, 1994)),
    ("E1015", "Aditya",   "Verma",      "Engineering",      "Software Engineer",        "L3", "Pune",      "Male",   "Permanent", (19, 4, 2023), (7, 7, 1996)),
    ("E1016", "Kavya",    "Krishnan",   "Customer Success", "Support Specialist",       "L2", "Chennai",   "Female", "Permanent", (28, 1, 2021), (15, 5, 1995)),
    ("E1017", "Rahul",    "Chopra",     "Operations",       "Operations Manager",       "M1", "Delhi",     "Male",   "Permanent", (22, 8, 2019), (3, 3, 1988)),
    ("E1018", "Neha",     "Gupta",      "Human Resources",  "Talent Acquisition Lead",  "M1", "Hyderabad", "Female", "Permanent", (6, 6, 2020),  (18, 9, 1990)),
    ("E1019", "Manish",   "Pillai",     "Engineering",      "DevOps Engineer",          "L4", "Bengaluru", "Male",   "Permanent", (13, 11, 2021),(27, 12, 1991)),
    ("E1020", "Shreya",   "Banerjee",   "Engineering",      "QA Engineer",              "L3", "Kolkata",   "Female", "Permanent", (1, 2, 2023),  (9, 4, 1996)),
    ("E1021", "Varun",    "Malhotra",   "Sales",            "Sales Development Rep",    "S2", "Delhi",     "Male",   "Contract",  (17, 5, 2023), (22, 6, 1998)),
    ("E1022", "Pooja",    "Shetty",     "Marketing",        "Growth Marketer",          "L3", "Mumbai",    "Female", "Permanent", (24, 9, 2022), (5, 11, 1994)),
    ("E1023", "Akash",    "Trivedi",    "Engineering",      "Data Engineer",            "L4", "Hyderabad", "Male",   "Permanent", (8, 10, 2020), (16, 1, 1992)),
    ("E1024", "Ritu",     "Saxena",     "Finance",          "Accounts Payable Analyst", "L2", "Delhi",     "Female", "Permanent", (12, 12, 2022),(28, 7, 1995)),
    ("E1025", "Sanjay",   "Kapoor",     "Operations",       "Facilities Lead",          "L3", "Pune",      "Male",   "Permanent", (20, 7, 2017), (2, 2, 1983)),
    ("E1026", "Divya",    "Raman",      "Customer Success", "Onboarding Specialist",    "L2", "Chennai",   "Female", "Intern",    (4, 8, 2024),  (12, 10, 2001)),
    ("E1027", "Harsh",    "Bhatia",     "Engineering",      "Frontend Engineer",        "L3", "Bengaluru", "Male",   "Permanent", (26, 3, 2022), (20, 5, 1994)),
    ("E1028", "Lakshmi",  "Venkatesh",  "Human Resources",  "HR Operations Executive",  "L2", "Chennai",   "Female", "Permanent", (10, 5, 2021), (6, 9, 1993)),
    ("E1029", "Imran",    "Sheikh",     "Sales",            "Enterprise AE",            "S4", "Mumbai",    "Male",   "Permanent", (29, 11, 2018),(1, 1, 1987)),
    ("E1030", "Gauri",    "Deshmukh",   "Legal",            "Compliance Analyst",       "L3", "Pune",      "Female", "Permanent", (15, 6, 2023), (23, 3, 1996)),
    ("E1031", "Rakesh",   "Reddy",      "Engineering",      "Principal Engineer",       "L6", "Hyderabad", "Male",   "Permanent", (7, 9, 2016),  (14, 8, 1982)),
    ("E1032", "Sana",     "Qureshi",    "Marketing",        "Brand Manager",            "M1", "Mumbai",    "Female", "Permanent", (19, 2, 2020), (25, 4, 1990)),
    ("E1033", "Deepak",   "Yadav",      "Operations",       "Logistics Coordinator",    "L2", "Delhi",     "Male",   "Contract",  (2, 4, 2023),  (10, 6, 1997)),
    ("E1034", "Nandini",  "Rege",       "Finance",          "Payroll Specialist",       "L3", "Pune",      "Female", "Permanent", (21, 1, 2021), (8, 12, 1992)),
    ("E1035", "Vivek",    "Thakur",     "Engineering",      "Backend Engineer",         "L4", "Bengaluru", "Male",   "Permanent", (5, 5, 2021),  (30, 10, 1991)),
    ("E1036", "Anjali",   "Prasad",     "Customer Success", "CS Team Lead",             "M1", "Kolkata",   "Female", "Permanent", (27, 7, 2019), (17, 2, 1989)),
    ("E1037", "Suresh",   "Babu",       "Operations",       "Warehouse Supervisor",     "L2", "Chennai",   "Male",   "Permanent", (14, 10, 2018),(3, 5, 1985)),
    ("E1038", "Ritika",   "Jain",       "Engineering",      "Mobile Engineer",          "L3", "Bengaluru", "Female", "Permanent", (23, 4, 2023), (11, 11, 1995)),
    ("E1039", "Farhan",   "Ali",        "Sales",            "Inside Sales Rep",         "S2", "Hyderabad", "Male",   "Permanent", (9, 8, 2022),  (19, 7, 1996)),
    ("E1040", "Swati",    "Kulthe",     "Human Resources",  "L&D Manager",              "M1", "Pune",      "Female", "Permanent", (18, 3, 2019), (26, 6, 1988)),
]

COMPANY = "novatech.in"


def work_email(first: str, last: str) -> str:
    return f"{first.lower()}.{last.lower()}@{COMPANY}"


def pan_for(idx: int) -> str:
    """Deterministic, structurally valid fake PAN: [A-Z]{5}[0-9]{4}[A-Z]."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    a = "".join(letters[(idx * 7 + i * 3) % 26] for i in range(5))
    digits = f"{(idx * 137) % 10000:04d}"
    return f"{a}{digits}{letters[(idx * 11) % 26]}"


def uan_for(idx: int) -> str:
    return f"{100000000000 + idx * 7919:012d}"


def ifsc_for(idx: int) -> str:
    banks = ["HDFC", "ICIC", "SBIN", "UTIB"]
    return f"{banks[idx % 4]}0{(1000 + idx * 13) % 10000:06d}"


def bank_for(idx: int) -> str:
    return f"{50100000000000 + idx * 104729:014d}"


# Managers: who reports to whom (by roster index). Deliberate defects flagged.
MANAGER = {
    1: 0, 14: 6, 18: 6, 19: 6, 26: 6, 34: 6, 37: 6,     # engineering under Arjun (idx 6)
    2: 10, 20: 10, 28: 10, 38: 10,                       # sales under Siddharth (idx 10)
    4: 12, 23: 12, 33: 12,                               # finance under Nikhil (idx 12)
    5: 31, 13: 31, 21: 31,                               # marketing under Sana (idx 31)
    7: 35, 15: 35, 25: 35,                               # CS under Anjali (idx 35)
    9: 16, 24: 16, 32: 16, 36: 16,                       # ops under Rahul (idx 16)
    3: 39, 17: 39, 27: 39,                               # HR
    11: 29,                                              # legal
    22: 6, 30: 6,
    # DEFECT: reporting cycle. Vikram (idx 4) reports to Nikhil (idx 12) and
    # Nikhil reports back to Vikram. Both sit below index 20, so they exist only
    # in the legacy export - a cycle planted in someone who also appears in
    # payroll would be silently broken when the two records merge and payroll's
    # manager value wins.
    12: 4,
}


def fmt(d: tuple[int, int, int], style: str) -> str:
    day, month, year = d
    if style == "dd-mm-yyyy":
        return f"{day:02d}-{month:02d}-{year}"
    if style == "dd/mm/yyyy":
        return f"{day:02d}/{month:02d}/{year}"
    if style == "iso":
        return f"{year}-{month:02d}-{day:02d}"
    raise ValueError(style)


def build_legacy_csv() -> list[dict]:
    """System A: the old HRMS. Ships full names, DD/MM dates, messy departments."""
    rows: list[dict] = []
    # first 30 people live in the legacy system
    for idx in range(30):
        code, first, last, dept, desig, grade, city, gender, etype, doj, dob = ROSTER[idx]

        # DEFECT: whitespace and casing noise sprayed through the file
        dept_raw = dept
        if idx % 7 == 0:
            dept_raw = f"  {dept.upper()} "
        elif idx % 5 == 0:
            dept_raw = dept.lower()
        # DEFECT: "Engg" is a grey-band enum match -> must ESCALATE, not guess
        if idx in (14, 19):
            dept_raw = "Engg"
        # "Human Resource" (singular) is a high-confidence fuzzy match -> auto-fix
        if dept == "Human Resources" and idx % 2 == 1:
            dept_raw = "Human Resource"

        mgr_idx = MANAGER.get(idx)
        mgr = work_email(ROSTER[mgr_idx][1], ROSTER[mgr_idx][2]) if mgr_idx is not None else ""
        # DEFECT: orphan manager - points at someone who is in no source file
        if idx == 24:
            mgr = "former.manager@novatech.in"

        pan = pan_for(idx)
        # DEFECT: malformed PAN survives auto-repair -> validation escalation
        if idx == 9:
            pan = "ABCD1234XY"

        rows.append({
            "Emp ID": code,
            # DEFECT: one source column feeds two target fields (needs a split)
            "Employee Name": f"{first} {last}" if idx % 6 else f"  {first}  {last} ",
            "Official Email": work_email(first, last).upper() if idx % 8 == 0 else work_email(first, last),
            # DEFECT: ambiguous column - values are a mix of company and public
            # domains, so neither the name nor the data says work vs personal
            "Mail ID": (
                f"{first.lower()}{idx}@gmail.com" if idx % 2 == 0
                else work_email(first, last)
            ),
            "DOB": fmt(dob, "dd-mm-yyyy"),
            # DD/MM with enough day>12 anchors to infer the convention safely
            "Date of Joining": fmt(doj, "dd/mm/yyyy"),
            "Dept": dept_raw,
            "Designation": desig,
            "Reporting To": mgr,
            "Mobile": f"+91 {90000 + idx:05d} {10000 + idx * 7:05d}",
            "Status": "Active" if idx % 11 else "active ",
            "PAN No": pan,
            "Emp Type": etype,
            "Gender": {"Male": "M", "Female": "F"}[gender],
            "Office": city,
            # DEFECT: junk column with no target field -> ignored, not escalated
            "Remarks": "" if idx % 3 else "verified by HR ops",
        })

    # DEFECT: exact duplicate rows (classic copy-paste in a spreadsheet) -> auto-merge
    rows.append(dict(rows[3]))
    rows.append(dict(rows[11]))

    # DEFECT: an employee who left in 2019 and was rehired later (see payroll file).
    # Same human, same PAN, different employee code, non-overlapping tenure.
    rows.append({
        "Emp ID": "E0910",
        "Employee Name": "Rakesh Reddy",
        # Different address from the current record: the old mailbox was reissued
        # when he rejoined, which is exactly why email cannot settle identity here.
        "Official Email": "rakesh.reddy.2014@novatech.in",
        "Mail ID": "rakesh.reddy1982@gmail.com",
        "DOB": fmt((14, 8, 1982), "dd-mm-yyyy"),
        "Date of Joining": fmt((3, 2, 2014), "dd/mm/yyyy"),
        "Dept": "Engineering",
        "Designation": "Senior Engineer",
        "Reporting To": "",
        "Mobile": "+91 98200 11223",
        "Status": "Inactive",
        "PAN No": pan_for(30),          # same PAN as roster idx 30 (Rakesh Reddy)
        "Emp Type": "Permanent",
        "Gender": "M",
        "Office": "Hyderabad",
        "Remarks": "resigned 2019",
    })
    return rows


def build_payroll_rows() -> list[dict]:
    """System B: payroll. Ships split names, ISO birth dates, statutory IDs.

    Its joining-date column is the nasty one: every value is day<=12 AND
    month<=12, so there is no unambiguous row to infer DD/MM vs MM/DD from.
    That is a genuine coin flip, so the agent must escalate rather than guess.
    """
    rows: list[dict] = []
    # payroll covers people 20..39 -> overlaps the legacy file on 20..29
    for idx in range(20, 40):
        code, first, last, dept, desig, grade, city, gender, etype, doj, dob = ROSTER[idx]

        # force every joining date into the ambiguous zone (day<=12, month<=12)
        amb_doj = (min(doj[0], 12), min(doj[1], 12), doj[2])

        exit_date = ""
        status = "Active"
        # DEFECT: inactive employee missing an exit date -> business-rule failure
        if idx == 33:
            status = "Inactive"

        row = {
            "employee_number": code,
            "first_name": first,
            "surname": last,
            "company_email_id": work_email(first, last),
            "birth_date": fmt(dob, "iso"),
            "joining_dt": fmt(amb_doj, "dd/mm/yyyy"),
            "division": dept,
            "role_title": desig,
            "worker_category": {"Permanent": "FTE", "Contract": "Contractor", "Intern": "Intern"}[etype],
            "ctc_annual": str(800000 + idx * 45000),   # no target field -> ignored
            "pan_number": pan_for(idx),
            "uan_number": uan_for(idx),
            "bank_ac": bank_for(idx),
            "ifsc_code": ifsc_for(idx),
            "base_city": city,
            "supervisor": "",
            "exit_date": exit_date,
            "employment_status": status,
            "grade_band": grade,
        }

        mgr_idx = MANAGER.get(idx)
        if mgr_idx is not None:
            row["supervisor"] = work_email(ROSTER[mgr_idx][1], ROSTER[mgr_idx][2])

        # DEFECT: required fields missing, and nothing in the row lets us derive
        # them -> survives one auto-repair pass -> escalate
        if idx == 22:
            row["role_title"] = ""
        if idx == 24:
            row["division"] = ""

        rows.append(row)

    # DEFECT: near-duplicate. Same human as roster idx 31 (Sana Qureshi):
    # same DOB, name shortened, different email. Could be a duplicate or could
    # be a different person - a coin flip, so escalate.
    rows.append({
        "employee_number": "P2201",
        "first_name": "Sana",
        "surname": "Q.",
        "company_email_id": "sana.q@novatech.in",
        "birth_date": fmt((25, 4, 1990), "iso"),
        "joining_dt": "02/02/2020",
        "division": "Marketing",
        "role_title": "Brand Manager",
        "worker_category": "FTE",
        "ctc_annual": "1450000",
        # No PAN on this record, so there is no identifier to settle it either
        # way - only the name and date of birth, which is precisely the kind of
        # evidence that supports a suspicion but not a merge.
        "pan_number": "",
        "uan_number": uan_for(31),
        "bank_ac": bank_for(31),
        "ifsc_code": ifsc_for(31),
        "base_city": "Mumbai",
        "supervisor": "",
        "exit_date": "",
        "employment_status": "Active",
        "grade_band": "M1",
    })
    return rows


def build_broken_csv() -> list[dict]:
    """A file the consultant grabbed by mistake: asset inventory, not employees.

    Used to demo the circuit breaker - the agent should raise ONE batch-level
    escalation saying the premise looks wrong, not 40 per-column tickets.
    """
    return [
        {
            "asset_tag": f"AST-{4000 + i}",
            "hardware_model": ["MacBook Pro 14", "Dell Latitude 5440", "ThinkPad X1"][i % 3],
            "serial_no": f"SN{900000 + i * 37}",
            "purchase_cost_inr": str(120000 + i * 2500),
            "warranty_expiry": f"2027-{(i % 12) + 1:02d}-15",
            "allocated_seat": f"{['BLR', 'MUM', 'HYD'][i % 3]}-{i + 1:03d}",
            "condition_grade": ["A", "B", "C"][i % 3],
        }
        for i in range(18)
    ]


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)

    legacy = build_legacy_csv()
    with (DATA / "legacy_hris_export.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(legacy[0].keys()))
        writer.writeheader()
        writer.writerows(legacy)

    payroll = build_payroll_rows()
    pd.DataFrame(payroll).to_excel(DATA / "payroll_system.xlsx", index=False)

    broken = build_broken_csv()
    with (DATA / "broken_export.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(broken[0].keys()))
        writer.writeheader()
        writer.writerows(broken)

    print(f"legacy_hris_export.csv  {len(legacy):>3} rows, {len(legacy[0])} columns")
    print(f"payroll_system.xlsx     {len(payroll):>3} rows, {len(payroll[0])} columns")
    print(f"broken_export.csv       {len(broken):>3} rows, {len(broken[0])} columns")


if __name__ == "__main__":
    main()
