import { describe, expect, it, vi } from "vitest";
import { dispatch, drainFrames } from "./stream";

/**
 * The SSE framing is the one part of the transport where a bug is both easy to
 * introduce and impossible to notice at runtime: a dropped frame just looks
 * like the agent skipping a step. So it is tested directly rather than through
 * the store.
 */
describe("drainFrames", () => {
  it("parses complete frames and keeps the partial tail", () => {
    const { events, rest } = drainFrames(
      'data: {"type":"progress","text":"one"}\n\ndata: {"type":"progress","text":"tw',
    );
    expect(events).toEqual([{ type: "progress", text: "one" }]);
    expect(rest).toBe('data: {"type":"progress","text":"tw');
  });

  it("rejoins a frame split across two chunks", () => {
    // This is the case a naive per-chunk split loses silently.
    const first = drainFrames('data: {"type":"progress","tex');
    expect(first.events).toHaveLength(0);

    const second = drainFrames(first.rest + 't":"resumed"}\n\n');
    expect(second.events).toEqual([{ type: "progress", text: "resumed" }]);
    expect(second.rest).toBe("");
  });

  it("skips a malformed frame instead of throwing", () => {
    const { events } = drainFrames(
      'data: {not json}\n\ndata: {"type":"done","summary":{}}\n\n',
    );
    // One bad event must never take down a stream reporting a live migration.
    expect(events).toEqual([{ type: "done", summary: {} }]);
  });

  it("joins a multi-line data payload per the SSE spec", () => {
    const { events } = drainFrames('data: {"type":"progress",\ndata: "text":"split"}\n\n');
    expect(events).toEqual([{ type: "progress", text: "split" }]);
  });

  it("tolerates comment lines and a missing space after the colon", () => {
    const { events } = drainFrames(': keep-alive\ndata:{"type":"progress","text":"tight"}\n\n');
    expect(events).toEqual([{ type: "progress", text: "tight" }]);
  });

  it("returns nothing for an empty buffer", () => {
    expect(drainFrames("")).toEqual({ events: [], rest: "" });
  });
});

describe("dispatch", () => {
  it("routes each event type to its handler", () => {
    const handlers = {
      onProgress: vi.fn(),
      onSummary: vi.fn(),
      onAwaiting: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
    };

    dispatch({ type: "progress", text: "hello" }, handlers);
    expect(handlers.onProgress).toHaveBeenCalledWith("hello");

    dispatch({ type: "awaiting", escalations: [{ id: "e1" }], summary: { records: 5 } }, handlers);
    expect(handlers.onAwaiting).toHaveBeenCalledWith([{ id: "e1" }], { records: 5 }, 1);

    dispatch({ type: "awaiting", escalations: [], summary: {}, round: 2 }, handlers);
    expect(handlers.onAwaiting).toHaveBeenLastCalledWith([], {}, 2);

    dispatch({ type: "done", summary: { pushed: 3 }, records: [] }, handlers);
    expect(handlers.onDone).toHaveBeenCalledWith({ pushed: 3 }, []);

    dispatch({ type: "error", message: "boom" }, handlers);
    expect(handlers.onError).toHaveBeenCalledWith("boom");
  });

  it("treats an escalations event as a summary update", () => {
    // The queue itself arrives on `awaiting`; `escalations` only refreshes the
    // header counters mid-run.
    const onSummary = vi.fn();
    dispatch({ type: "escalations", summary: { escalations: 10 } }, { onSummary });
    expect(onSummary).toHaveBeenCalledWith({ escalations: 10 });
  });

  it("ignores an unknown type so the server can add events freely", () => {
    const handlers = { onProgress: vi.fn(), onError: vi.fn() };
    expect(() => dispatch({ type: "something_new", data: 1 }, handlers)).not.toThrow();
    expect(handlers.onProgress).not.toHaveBeenCalled();
    expect(handlers.onError).not.toHaveBeenCalled();
  });

  it("survives a null event", () => {
    expect(() => dispatch(null, { onError: vi.fn() })).not.toThrow();
  });
});
