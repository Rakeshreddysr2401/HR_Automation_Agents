"""Generate a test kit: one file per behaviour you want to see.

The bundled sample exports exercise everything at once, which is right for a
demo and wrong for testing — when ten questions come back it is hard to tell
which input caused which. These files isolate one behaviour each, so you can
drop one in, see exactly one thing happen, and know why.

    python scripts/make_testkit.py        # writes data/testkit/

Every file is deliberately small (10-25 rows). The point is to read the
questions, not to benchmark.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.settings import ROOT

OUT = ROOT / "data" / "testkit"

DEPARTMENTS = ["Engineering", "Sales", "Marketing", "Finance", "Operations"]
FIRST = ["Aarav", "Diya", "Rohan", "Ananya", "Vikram", "Meera", "Karan", "Priya",
         "Arjun", "Sneha", "Rahul", "Nisha", "Sameer", "Tara", "Dev", "Ishita",
         "Kabir", "Riya", "Manav", "Anjali", "Varun", "Pooja", "Nikhil", "Leela",
         "Farhan"]
LAST = ["Sharma", "Patel", "Mehta", "Iyer", "Nair", "Joshi", "Reddy", "Gupta",
        "Rao", "Kapoor", "Desai", "Bose", "Khanna", "Malhotra", "Shetty",
        "Trivedi", "Chopra", "Banerjee", "Menon", "Sinha", "Qureshi", "Rege",
        "Pillai", "Ghosh", "Bhatt"]


def _person(i: int) -> dict[str, str]:
    """One clean, fully valid employee."""
    return {
        "employee_code": f"T{1000 + i}",
        "first_name": FIRST[i % len(FIRST)],
        "last_name": LAST[i % len(LAST)],
        "work_email": f"{FIRST[i % len(FIRST)].lower()}.{LAST[i % len(LAST)].lower()}@novatech.in",
        "personal_email": f"{FIRST[i % len(FIRST)].lower()}{i}@gmail.com",
        "phone": f"+9198{20000000 + i * 37:08d}",
        "date_of_birth": f"{1985 + (i % 12)}-0{1 + (i % 9)}-1{i % 9}",
        # Day deliberately above 12 on most rows: this column is meant to be
        # readable, so that 03_ambiguous_dates is the only file that asks.
        "date_of_joining": f"{2015 + (i % 8)}-0{1 + (i % 9)}-{13 + (i % 15):02d}",
        "department": DEPARTMENTS[i % len(DEPARTMENTS)],
        "designation": ["Engineer", "Analyst", "Manager", "Lead"][i % 4],
        "employment_type": "Permanent",
        "gender": ["Male", "Female"][i % 2],
        "status": "Active",
    }


def write(name: str, rows: list[dict], note: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {name:<28} {len(rows):>3} rows  {note}")


# ---------------------------------------------------------------------------
# 01 — the control. Nothing should be asked about this file at all.
# ---------------------------------------------------------------------------
def clean_file() -> None:
    write(
        "01_clean.csv",
        [_person(i) for i in range(15)],
        "expect 0 questions — the control",
    )


# ---------------------------------------------------------------------------
# 02 — different column names for the same thing. The mapping should be worked
#      out with no help, because the schema descriptions carry the concepts.
# ---------------------------------------------------------------------------
def renamed_columns() -> None:
    rows = []
    for i in range(15):
        p = _person(i)
        rows.append({
            "emp_cd": p["employee_code"],
            "fname": p["first_name"],
            "surname": p["last_name"],
            "official_email": p["work_email"],
            "mobile": p["phone"],
            "dob": p["date_of_birth"],
            "doj": p["date_of_joining"],
            "division": p["department"],       # -> department
            "job_title": p["designation"],     # -> designation
            "worker_category": "FTE",          # -> employment_type, via alias
            "gender": "M" if i % 2 == 0 else "F",   # value alias, not a mapping question
            "status": "A",                     # value alias, not a mapping question
        })
    write("02_renamed_columns.csv", rows, "expect 0 questions — mapping inferred")


# ---------------------------------------------------------------------------
# 03 — a date column where no row can settle day-first from month-first.
# ---------------------------------------------------------------------------
def ambiguous_dates() -> None:
    rows = []
    for i in range(15):
        p = _person(i)
        # Every part <= 12, so nothing in the column disambiguates it.
        p["date_of_joining"] = f"0{1 + (i % 9)}/0{1 + ((i + 3) % 9)}/201{i % 9}"
        rows.append(p)
    write("03_ambiguous_dates.csv", rows, "expect 1 date question covering all rows")


# ---------------------------------------------------------------------------
# 04 — values outside the schema's vocabulary, one close and one not.
# ---------------------------------------------------------------------------
def unknown_values() -> None:
    rows = [_person(i) for i in range(15)]
    rows[3]["department"] = "Engg"              # close to Engineering — asked
    rows[4]["department"] = "  finance  "       # spacing/casing — fixed silently
    rows[5]["employment_type"] = "FTE"          # known alias — fixed silently
    rows[6]["gender"] = "M"                     # known alias — fixed silently
    write("04_unknown_values.csv", rows, "expect 1 value question ('Engg')")


# ---------------------------------------------------------------------------
# 05 — the same person twice, and a rehire that looks identical to a duplicate.
# ---------------------------------------------------------------------------
def identity_cases() -> None:
    rows = [_person(i) for i in range(12)]

    # A true duplicate: same person, two codes, same email.
    dup = dict(rows[2])
    dup["employee_code"] = "T9001"
    rows.append(dup)

    # A rehire: same PAN, two codes, non-overlapping service. Merging this
    # destroys the service history gratuity is computed from, so it is asked.
    # Built from someone *not* otherwise in the file, so the pair is a pair.
    first_stint = dict(_person(20))
    first_stint["employee_code"] = "T9002"
    first_stint["pan"] = "ABCDE1234F"
    first_stint["work_email"] = "rehire.first@novatech.in"
    first_stint["date_of_joining"] = "2016-04-01"
    first_stint["date_of_exit"] = "2019-03-31"
    first_stint["status"] = "Inactive"

    second_stint = dict(first_stint)
    second_stint["employee_code"] = "T9003"
    second_stint["work_email"] = "rehire.second@novatech.in"
    second_stint["date_of_joining"] = "2022-07-01"
    second_stint["date_of_exit"] = ""
    second_stint["status"] = "Active"

    rows += [first_stint, second_stint]
    write("05_identity.csv", rows, "expect 1 rehire question; the exact duplicate merges silently")


# ---------------------------------------------------------------------------
# 06 — records that cannot be loaded, for reasons of different kinds.
# ---------------------------------------------------------------------------
def broken_records() -> None:
    rows = [_person(i) for i in range(12)]
    rows[1]["work_email"] = "not-an-email"          # bad format, unrepairable
    rows[2]["date_of_birth"] = ""                   # required, missing
    rows[3]["date_of_joining"] = "1980-01-01"       # before date_of_birth
    rows[4]["status"] = "Inactive"                  # inactive with no exit date
    rows[4]["date_of_exit"] = ""
    rows[5]["phone"] = " +91 98200 11122 "          # messy but repairable
    write("06_broken_records.csv", rows, "expect 4 record questions, 1 repaired silently")


# ---------------------------------------------------------------------------
# 07 — reporting lines that do not resolve.
# ---------------------------------------------------------------------------
def hierarchy() -> None:
    rows = [_person(i) for i in range(12)]
    for row in rows[:6]:
        row["manager_email"] = rows[0]["work_email"]

    # A manager who is in no file at all. Grouped by the missing manager, so
    # three reports are one question, not three.
    for row in rows[6:9]:
        row["manager_email"] = "departed.manager@novatech.in"

    # Two people reporting to each other.
    rows[10]["manager_email"] = rows[11]["work_email"]
    rows[11]["manager_email"] = rows[10]["work_email"]
    write("07_hierarchy.csv", rows, "expect 2: one orphan (covering 3 reports) + one cycle")


# ---------------------------------------------------------------------------
# 08 / 09 — two files describing the same people, disagreeing in every way.
#           Run them together to see reconciliation.
# ---------------------------------------------------------------------------
def two_files() -> None:
    people = [_person(i) for i in range(18)]

    hris = []
    for p in people:
        hris.append({
            "Employee Code": p["employee_code"],
            "Employee Name": f"  {p['first_name']}  {p['last_name']} ",
            "Official Email": p["work_email"],
            "Date of Birth": _to_dmy(p["date_of_birth"]),
            "Date of Joining": _to_dmy(p["date_of_joining"]),
            "Division": p["department"],
            "Designation": p["designation"],
            "Status": "Active",
        })

    # The payroll half carries the statutory identifiers and nothing else, and
    # names its columns differently. Overlaps on 12 of the 18 people.
    payroll = []
    for p in people[6:]:
        payroll.append({
            "emp_id": p["employee_code"],
            "first_name": p["first_name"],
            "surname": p["last_name"],
            "work_mail": p["work_email"],
            "joining_dt": _to_dmy(p["date_of_joining"]),
            "pan_number": f"ABCDE{1000 + int(p['employee_code'][1:]) % 9000}F",
            "uan_no": f"1000{int(p['employee_code'][1:]):08d}",
            "ctc_annual": "1800000",     # no home in an employee master
            "worker_category": "FTE",
            "employment_state": "A",
        })

    write("08_hris_half.csv", hris, "run these two TOGETHER →")
    write("09_payroll_half.csv", payroll, "→ 30 rows become 18 people, 12 merged")


def _to_dmy(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{int(day):02d}/{int(month):02d}/{year}"


# ---------------------------------------------------------------------------
# 10 — the wrong file entirely. Should be refused, not migrated.
# ---------------------------------------------------------------------------
def wrong_file() -> None:
    rows = [
        {
            "asset_tag": f"AST-{5000 + i}",
            "model": ["ThinkPad X1", "MacBook Pro", "Dell XPS"][i % 3],
            "serial_no": f"SN{900000 + i}",
            "purchase_cost": str(85000 + i * 1000),
            "warranty_months": "36",
            "depreciation_rate": "0.25",
            "location_code": f"LOC-{i % 5}",
            "condition": ["New", "Good", "Fair"][i % 3],
        }
        for i in range(20)
    ]
    write("10_wrong_file.csv", rows, "expect 1 question: not employee data")


# ---------------------------------------------------------------------------
# 11 — required field with no source column anywhere.
# ---------------------------------------------------------------------------
def missing_required_field() -> None:
    rows = []
    for i in range(20):
        p = _person(i)
        p.pop("work_email")     # the schema requires it; nothing provides it
        rows.append(p)
    write("11_no_email_column.csv", rows, "expect 1 field question, not 20")


# ---------------------------------------------------------------------------
# 12 — surname-first names, the convention real payroll exports use.
# ---------------------------------------------------------------------------
def surname_first_names() -> None:
    rows = []
    for i in range(15):
        p = _person(i)
        rows.append({
            "employee_code": p["employee_code"],
            # "Last, First" — handled silently, and recorded in the audit trail.
            "full_name": f"{p['last_name']}, {p['first_name']}",
            "work_email": p["work_email"],
            "date_of_birth": p["date_of_birth"],
            "date_of_joining": p["date_of_joining"],
            "department": p["department"],
            "designation": p["designation"],
            "employment_type": p["employment_type"],
            "status": p["status"],
        })
    write("12_surname_first.csv", rows, "expect 1 question confirming the name column")


# ---------------------------------------------------------------------------
# A blank template: the shape the target schema wants, for reference.
# ---------------------------------------------------------------------------
def template() -> None:
    from app.schema import get_schema

    schema = get_schema()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "00_target_template.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([f.name for f in schema.fields])
        writer.writerow(
            [
                "REQUIRED" if f.required else ("one of: " + "|".join(f.enum) if f.enum else "")
                for f in schema.fields
            ]
        )
        writer.writerow([_example(f) for f in schema.fields])
    print(f"  {'00_target_template.csv':<28}   3 rows  the shape the schema wants")


def _example(field) -> str:
    samples = {
        "employee_code": "E1001",
        "first_name": "Aarav",
        "last_name": "Sharma",
        "work_email": "aarav.sharma@company.com",
        "personal_email": "aarav@gmail.com",
        "phone": "+919820011122",
        "date_of_birth": "1990-04-17",
        "date_of_joining": "2019-06-03",
        "date_of_exit": "",
        "department": "Engineering",
        "designation": "Senior Engineer",
        "employment_type": "Permanent",
        "grade": "L4",
        "location": "Bengaluru",
        "gender": "Male",
        "manager_email": "priya.rao@company.com",
        "pan": "ABCDE1234F",
        "uan": "100000158380",
        "bank_account": "50100123456789",
        "ifsc": "HDFC0001234",
        "status": "Active",
    }
    return samples.get(field.name, "")


def main() -> None:
    print(f"Writing test kit to {OUT}\n")
    template()
    clean_file()
    renamed_columns()
    ambiguous_dates()
    unknown_values()
    identity_cases()
    broken_records()
    hierarchy()
    two_files()
    wrong_file()
    missing_required_field()
    surname_first_names()
    print(f"\nDone. See docs/TESTING.md for what each one should do.")


if __name__ == "__main__":
    main()
