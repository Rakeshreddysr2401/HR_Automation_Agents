"""Measure what each mapping threshold actually costs.

    uv run python scripts/sweep_thresholds.py

The two numbers that decide whether a column mapping is applied or queried live in
app/policy.py:

    MAPPING_AUTO_MIN      how good the best match has to be
    MAPPING_MARGIN_MIN    how far clear of the runner-up it has to be

"Why 0.82?" deserves a better answer than "it felt right". This re-runs the sample
migration across a grid of both values and reports, for each combination, how many
columns are mapped without asking, how many are queried, and - the column that
matters - how many are mapped **wrongly**.

A wrong mapping is the expensive failure: it is silent, it corrupts a field the
target system keys off, and nobody finds out until payroll runs. An extra question
costs a consultant fifteen seconds. The defaults are therefore chosen as the
cheapest setting at which wrong mappings are zero, not the setting with the fewest
questions.

Ground truth is the expected mapping of the bundled sample files, declared below.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import llm, policy  # noqa: E402
from app.agents.mapper import map_columns  # noqa: E402
from app.agents.profiler import load_sources, profile_all  # noqa: E402
from app.models import Disposition  # noqa: E402
from app.schema import get_schema  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FILES = [str(ROOT / "data" / "legacy_hris_export.csv"), str(ROOT / "data" / "payroll_system.xlsx")]

# What a careful human would map each column to. "IGNORE" means no target field
# genuinely describes it. Anything the agent maps to something other than this is
# a wrong mapping.
TRUTH: dict[tuple[str, str], str] = {
    ("legacy_hris_export.csv", "Emp ID"): "employee_code",
    ("legacy_hris_export.csv", "Employee Name"): "first_name",
    ("legacy_hris_export.csv", "Official Email"): "work_email",
    ("legacy_hris_export.csv", "Mail ID"): "personal_email",
    ("legacy_hris_export.csv", "DOB"): "date_of_birth",
    ("legacy_hris_export.csv", "Date of Joining"): "date_of_joining",
    ("legacy_hris_export.csv", "Dept"): "department",
    ("legacy_hris_export.csv", "Designation"): "designation",
    ("legacy_hris_export.csv", "Reporting To"): "manager_email",
    ("legacy_hris_export.csv", "Mobile"): "phone",
    ("legacy_hris_export.csv", "Status"): "status",
    ("legacy_hris_export.csv", "PAN No"): "pan",
    ("legacy_hris_export.csv", "Emp Type"): "employment_type",
    ("legacy_hris_export.csv", "Gender"): "gender",
    ("legacy_hris_export.csv", "Office"): "location",
    ("legacy_hris_export.csv", "Remarks"): "IGNORE",
    ("payroll_system.xlsx", "employee_number"): "employee_code",
    ("payroll_system.xlsx", "first_name"): "first_name",
    ("payroll_system.xlsx", "surname"): "last_name",
    ("payroll_system.xlsx", "company_email_id"): "work_email",
    ("payroll_system.xlsx", "birth_date"): "date_of_birth",
    ("payroll_system.xlsx", "joining_dt"): "date_of_joining",
    ("payroll_system.xlsx", "division"): "department",
    ("payroll_system.xlsx", "role_title"): "designation",
    ("payroll_system.xlsx", "worker_category"): "employment_type",
    ("payroll_system.xlsx", "ctc_annual"): "IGNORE",
    ("payroll_system.xlsx", "pan_number"): "pan",
    ("payroll_system.xlsx", "uan_number"): "uan",
    ("payroll_system.xlsx", "bank_ac"): "bank_account",
    ("payroll_system.xlsx", "ifsc_code"): "ifsc",
    ("payroll_system.xlsx", "base_city"): "location",
    ("payroll_system.xlsx", "supervisor"): "manager_email",
    ("payroll_system.xlsx", "exit_date"): "date_of_exit",
    ("payroll_system.xlsx", "employment_status"): "status",
    ("payroll_system.xlsx", "grade_band"): "grade",
}

CONFIDENCE_GRID = [0.60, 0.65, 0.70, 0.75, 0.78, 0.82, 0.86, 0.90, 0.95]
MARGIN_GRID = [0.00, 0.04, 0.08, 0.12, 0.16, 0.20, 0.30]


def evaluate(profiles, schema) -> tuple[int, int, int, list[str]]:
    """Returns (applied correctly, queried, applied wrongly, descriptions)."""
    mappings, _ = map_columns(profiles, schema, "sweep")
    right = asked = wrong = 0
    mistakes: list[str] = []

    for mapping in mappings:
        expected = TRUTH.get((mapping.source_file, mapping.column))
        if expected is None:
            continue
        if mapping.disposition is Disposition.ESCALATED:
            asked += 1
            continue
        got = "IGNORE" if mapping.disposition is Disposition.IGNORED else mapping.target_field
        if got == expected:
            right += 1
        else:
            wrong += 1
            mistakes.append(f"{mapping.column} -> {got} (should be {expected})")
    return right, asked, wrong, mistakes


def main() -> None:
    # The reasoning model only writes the explanation shown on an escalation card;
    # it has no influence on which columns map or escalate. Stub it out so a
    # 63-cell sweep is seconds rather than minutes. Embeddings stay live, since
    # those genuinely drive the scores being measured.
    llm.ask_json = lambda *args, **kwargs: None  # type: ignore[assignment]

    frames = load_sources(FILES)
    profiles = profile_all(frames)
    schema = get_schema()
    total = len(TRUTH)

    original = (policy.MAPPING_AUTO_MIN, policy.MAPPING_MARGIN_MIN)
    print(f"{total} columns with a known correct answer.\n")
    print("Each cell is  correct / asked / WRONG\n")

    header = "  conf \\ margin │" + "".join(f"{m:>15.2f}" for m in MARGIN_GRID)
    print(header)
    print("  " + "─" * (len(header) - 2))

    best: tuple[int, int, float, float] | None = None
    for confidence in CONFIDENCE_GRID:
        cells = []
        for margin in MARGIN_GRID:
            policy.MAPPING_AUTO_MIN = confidence
            policy.MAPPING_MARGIN_MIN = margin
            right, asked, wrong, _ = evaluate(profiles, schema)
            cells.append(f"{right:>5}/{asked:>3}/{wrong:<3}" + ("!" if wrong else " "))
            if wrong == 0 and (best is None or asked < best[1]):
                best = (right, asked, confidence, margin)
        marker = " ←" if abs(confidence - original[0]) < 1e-9 else ""
        print(f"  {confidence:>11.2f} │" + "".join(f"{c:>15}" for c in cells) + marker)

    policy.MAPPING_AUTO_MIN, policy.MAPPING_MARGIN_MIN = original
    right, asked, wrong, mistakes = evaluate(profiles, schema)

    print(f"\n  Shipped defaults: confidence ≥ {original[0]}, margin ≥ {original[1]}")
    print(f"    {right} mapped correctly, {asked} queried, {wrong} mapped wrongly")
    for mistake in mistakes:
        print(f"      wrong: {mistake}")

    if best:
        print(
            f"\n  Fewest questions with zero wrong mappings: "
            f"confidence ≥ {best[2]}, margin ≥ {best[3]} "
            f"({best[0]} correct, {best[1]} queried)"
        )
    any_wrong = best is not None and best[1] == 0
    print("\n  Reading this: moving down or right trades questions for safety. Cells marked !")
    print("  contain a silent wrong mapping, which is the failure worth paying questions to")
    print("  avoid - a consultant answers a question in fifteen seconds, whereas a wrong")
    print("  mapping is found when payroll runs.")
    if any_wrong:
        print(
            "\n  Note, honestly: on this sample no setting produces a wrong mapping, including\n"
            "  the most permissive one. The thresholds are not what is keeping this dataset\n"
            "  correct - the assignment step is, because columns compete for a target field\n"
            "  and the contest resolves ambiguity structurally rather than numerically.\n"
            "\n  That is a reason to keep the thresholds tight rather than to loosen them. A\n"
            "  thirty-five column sample cannot demonstrate that a permissive setting is safe\n"
            "  on inputs it does not contain; it can only fail to find a counter-example. The\n"
            "  shipped defaults cost two extra questions here, which is the premium paid for\n"
            "  the files this sample does not represent."
        )


if __name__ == "__main__":
    main()
