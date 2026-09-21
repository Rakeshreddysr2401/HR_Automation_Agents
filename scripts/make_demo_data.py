"""Two small exports for a live demo: nine people in the old HR system, seven in
payroll, and every row carries exactly one thing worth talking about.

The bundled sample data (`data/`) is the golden test's input and is bigger than
a demo audience can follow. This pair is the same story at a size where every
row can be pointed at on screen.

    python scripts/make_demo_data.py      # writes data/demo/

What each person is for:

  E1001 Aarav Sharma    messy spacing and casing - fixed silently, shown in Preview
  E1002 Priya Nair      reports to Rohan ...
  E1003 Rohan Mehta     ... who reports to Priya: a reporting loop
  E1004 Diya Patel      department "Engg" - close to Engineering, not close enough
  E1005 Vikram Rao      Inactive with no exit date - fails validation twice
  E1006 Meera Joshi     PAN "MEERA123" - malformed, fails validation twice
  E1007 Sana Qureshi    also in payroll as "Sana Q.", code P100 - duplicate?
  E1021 Arjun Iyer      reports to someone who has left; the target refuses the code
  E0910 Rakesh Reddy    left in 2019; payroll has him back in 2023 under E1031 - rehire
  E1015 Nikhil Agarwal  payroll only; the target times out once, then accepts
  E1031 Rakesh Reddy    the rehire's second employment record

The old HR file has two email columns that both look like the work address
(a contest), and payroll's joining dates all have day and month at 12 or below
(nothing settles day-first from month-first).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "data" / "demo"

OLD_HR_COLUMNS = [
    "Emp No", "Full Name", "Official Email", "Mail ID", "DOB", "Date of Joining",
    "Dept", "Designation", "Reports To", "Mobile", "Status", "Gender", "Location", "PAN",
    "Exit Date",
]

OLD_HR_ROWS = [
    # code, full name, official email, mail id, dob, joined, dept, title, reports to,
    # mobile, status, gender, location, pan, exit date
    ["E1001", "  aarav  SHARMA ", "AARAV.SHARMA@ACME.IN", "aarav88@gmail.com", "15/03/1988",
     "02/01/2019", "engineering  ", "Senior Engineer", "priya.nair@acme.in", "+91 98765 43210",
     "Active", "M", "Bengaluru", "ABCDE1234F", ""],
    ["E1002", "Priya Nair", "priya.nair@acme.in", "priya.nair@acme.in", "22/07/1982",
     "14/06/2015", "Engineering", "Engineering Manager", "rohan.mehta@acme.in", "9876500002",
     "Active", "F", "Bengaluru", "FGHIJ5678K", ""],
    ["E1003", "Rohan Mehta", "rohan.mehta@acme.in", "rohan.m@gmail.com", "30/11/1979",
     "01/04/2012", "Finance", "Chief Financial Officer", "priya.nair@acme.in", "9876500003",
     "Active", "M", "Mumbai", "KLMNO9012P", ""],
    ["E1004", "Diya Patel", "diya.patel@acme.in", "diya.patel@acme.in", "18/09/1991",
     "20/08/2021", "Engg", "Software Engineer", "priya.nair@acme.in", "9876500004",
     "Active", "F", "Pune", "PQRST3456U", ""],
    ["E1005", "Vikram Rao", "vikram.rao@acme.in", "vikram.rao@acme.in", "05/05/1985",
     "17/02/2016", "Sales", "Account Executive", "rohan.mehta@acme.in", "9876500005",
     "Inactive", "M", "Hyderabad", "UVWXY7890Z", ""],
    ["E1006", "Meera Joshi", "meera.joshi@acme.in", "meera.j@gmail.com", "25/12/1993",
     "23/09/2022", "Operations", "Operations Executive", "rohan.mehta@acme.in", "9876500006",
     "Active", "F", "Pune", "MEERA123", ""],
    ["E1007", "Sana Qureshi", "sana.qureshi@acme.in", "sana.qureshi@acme.in", "25/04/1990",
     "16/03/2020", "Marketing", "Brand Manager", "rohan.mehta@acme.in", "9876500007",
     "Active", "F", "Mumbai", "ZABCD1122E", ""],
    ["E1021", "Arjun Iyer", "arjun.iyer@acme.in", "arjun.iyer@acme.in", "14/08/1987",
     "28/10/2018", "Finance", "Financial Analyst", "former.manager@acme.in", "9876500021",
     "Active", "M", "Mumbai", "EFGHI3344J", ""],
    ["E0910", "Rakesh Reddy", "rakesh.r@acme.in", "rakesh.r@acme.in", "14/08/1982",
     "03/02/2014", "Engineering", "Senior Engineer", "priya.nair@acme.in", "9876500910",
     "Inactive", "M", "Hyderabad", "RAKES1110S", "2019-06-30"],
]

PAYROLL_COLUMNS = [
    "emp_cd", "first_name", "surname", "birth_date", "company_email", "joining_dt", "pan_no",
    "uan_no", "bank_ac", "ifsc_code", "division", "role_title", "worker_category", "grade_band",
    "ctc_annual", "supervisor", "employment_status", "exit_date",
]

PAYROLL_ROWS = [
    # code, first, surname, birth date (ISO), work email, joined (ambiguous), pan, uan,
    # bank account, ifsc, division, title, category, grade, ctc, supervisor, status, exit
    ["E1001", "Aarav", "Sharma", "1988-03-15", "aarav.sharma@acme.in", "02/01/2019", "ABCDE1234F",
     "100000001001", "50100002094580", "HDFC0001234", "Engineering", "Senior Engineer", "FTE", "L4", "2400000",
     "priya.nair@acme.in", "A", ""],
    ["E1002", "Priya", "Nair", "1982-07-22", "priya.nair@acme.in", "06/06/2015", "FGHIJ5678K",
     "100000001002", "50100002199309", "HDFC0001234", "Engineering", "Engineering Manager", "FTE", "L6", "4200000",
     "rohan.mehta@acme.in", "A", ""],
    ["E1004", "Diya", "Patel", "1991-09-18", "diya.patel@acme.in", "08/08/2021", "PQRST3456U",
     "100000001004", "50100002304038", "ICIC0001429", "Engineering", "Software Engineer", "FTE", "L3", "1500000",
     "priya.nair@acme.in", "A", ""],
    ["P100", "Sana", "Q.", "1990-04-25", "sana.q@acme.in", "03/03/2020", "",
     "100000001007", "50100002408767", "ICIC0001429", "Marketing", "Brand Manager", "Contractor", "L4", "1800000",
     "rohan.mehta@acme.in", "A", ""],
    ["E1031", "Rakesh", "Reddy", "1982-08-14", "rakesh.reddy@acme.in", "10/07/2023", "RAKES1110S",
     "100000001031", "50100002513496", "HDFC0001234", "Engineering", "Staff Engineer", "FTE", "L5", "3000000",
     "priya.nair@acme.in", "A", ""],
    ["E1015", "Nikhil", "Agarwal", "1995-01-30", "nikhil.agarwal@acme.in", "11/12/2022", "NIKHI5566L",
     "100000001015", "50100002618225", "SBIN0000456", "Finance", "Payroll Specialist", "FTE", "L3", "1400000",
     "rohan.mehta@acme.in", "A", ""],
    ["E1021", "Arjun", "Iyer", "1987-08-14", "arjun.iyer@acme.in", "10/10/2018", "EFGHI3344J",
     "100000001021", "50100002722954", "SBIN0000456", "Finance", "Financial Analyst", "FTE", "L4", "2000000",
     "former.manager@acme.in", "A", ""],
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    with (OUT / "old_hr_system.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(OLD_HR_COLUMNS)
        writer.writerows(OLD_HR_ROWS)

    pd.DataFrame(PAYROLL_ROWS, columns=PAYROLL_COLUMNS).to_excel(
        OUT / "payroll_export.xlsx", index=False
    )
    print(f"wrote {OUT / 'old_hr_system.csv'} ({len(OLD_HR_ROWS)} people)")
    print(f"wrote {OUT / 'payroll_export.xlsx'} ({len(PAYROLL_ROWS)} people)")


if __name__ == "__main__":
    main()
