import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { EscalationCard } from "./EscalationCard";
import type { Escalation } from "../../types";

function build(overrides: Partial<Escalation> = {}): Escalation {
  return {
    id: "esc_1",
    run_id: "run_1",
    subject: "date:legacy.csv:doj",
    type: "date_convention",
    title: "Is this column day-first or month-first?",
    question: "Every value in doj could be read two ways.",
    evidence: {
      column: "doj",
      target_field: "date_of_joining",
      ambiguous_count: 21,
      total_values: 33,
      sample_values: ["03/04/2021", "05/06/2020"],
    },
    options: [
      { value: "DMY", label: "Day first" },
      { value: "MDY", label: "Month first" },
    ],
    affected_records: ["E1001", "E1002"],
    affected_count: 2,
    status: "open",
    resolution: null,
    created_at: "2026-09-19T00:00:00Z",
    ...overrides,
  };
}

const noop = () => {};

describe("EscalationCard", () => {
  it("stages the option that was clicked, keyed by subject", () => {
    const onStage = vi.fn();
    const escalation = build();
    render(
      <EscalationCard
        escalation={escalation}
        onStage={onStage}
        onUnstage={noop}
        focused={false}
        onFocus={noop}
        index={0}
      />,
    );
    screen.getByText("Month first").click();
    // The subject, not the escalation id: ids are regenerated on every re-run,
    // subjects are what let an answer survive one.
    expect(onStage).toHaveBeenCalledWith("date:legacy.csv:doj", "MDY");
  });

  it("shows how many records ride on the answer", () => {
    render(
      <EscalationCard
        escalation={build()}
        onStage={noop}
        onUnstage={noop}
        focused={false}
        onFocus={noop}
        index={0}
      />,
    );
    // One question standing for many records is the core claim of the design.
    expect(screen.getByText("2 records")).toBeTruthy();
  });

  it("spells out both readings of an ambiguous date", () => {
    render(
      <EscalationCard
        escalation={build()}
        onStage={noop}
        onUnstage={noop}
        focused={false}
        onFocus={noop}
        index={0}
      />,
    );
    expect(screen.getByText("3 April 2021")).toBeTruthy();
    expect(screen.getByText("4 March 2021")).toBeTruthy();
  });

  it("replaces the options with the answer once staged", () => {
    const onUnstage = vi.fn();
    render(
      <EscalationCard
        escalation={build()}
        staged="DMY"
        onStage={noop}
        onUnstage={onUnstage}
        focused={false}
        onFocus={noop}
        index={0}
      />,
    );
    expect(screen.getByText("DMY")).toBeTruthy();
    expect(screen.queryByText("Month first")).toBeNull();
    screen.getByText("Change").click();
    expect(onUnstage).toHaveBeenCalledWith("date:legacy.csv:doj");
  });

  it("describes an inline correction rather than dumping JSON", () => {
    render(
      <EscalationCard
        escalation={build({ type: "validation_failed", evidence: { record: {}, issues: [] } })}
        staged={{ action: "edit", fields: { work_email: "a@b.com", phone: "" } }}
        onStage={noop}
        onUnstage={noop}
        focused={false}
        onFocus={noop}
        index={0}
      />,
    );
    expect(screen.getByText("work_email = a@b.com")).toBeTruthy();
  });

  it("shows editable input fields for push_rejected escalations", () => {
    render(
      <EscalationCard
        escalation={build({
          type: "push_rejected",
          subject: "push:E1021",
          evidence: {
            record_key: "E1021",
            employee_code: "E1021",
            status_code: 409,
            target_message: "duplicate code",
            editable_fields: ["employee_code"],
          },
          options: [
            { value: "skip", label: "Leave it out" },
            { value: "edit", label: "Change the record and resend" },
          ],
        })}
        onStage={noop}
        onUnstage={noop}
        focused={false}
        onFocus={noop}
        index={0}
      />,
    );
    expect(screen.getByText("Update record details")).toBeTruthy();
    expect(screen.getByPlaceholderText("leave blank to skip")).toBeTruthy();
  });
});
