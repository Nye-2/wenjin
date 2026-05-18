import { describe, expect, it } from "vitest";

import {
  readItemsArray,
  readOptionalActiveItem,
} from "@/lib/api/v2/list-response";

describe("room list response helpers", () => {
  it("reads plain array payloads", () => {
    expect(readItemsArray([{ id: "a" }], "library items")).toEqual([
      { id: "a" },
    ]);
  });

  it("reads { items } envelopes", () => {
    expect(
      readItemsArray({ items: [{ id: "a" }], count: 1 }, "documents"),
    ).toEqual([{ id: "a" }]);
  });

  it("reads optional active items", () => {
    expect(readOptionalActiveItem({ active: { id: "d-1" } })).toEqual([
      { id: "d-1" },
    ]);
    expect(readOptionalActiveItem({ active: null })).toEqual([]);
  });

  it("rejects malformed list payloads", () => {
    expect(() => readItemsArray({}, "tasks")).toThrow(
      "Invalid tasks response",
    );
  });
});
