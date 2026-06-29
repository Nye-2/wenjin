import { describe, expect, it } from "vitest";

import { readItemsArray } from "@/lib/api/v2/list-response";

describe("room list response helpers", () => {
  it("reads plain array payloads", () => {
    expect(readItemsArray([{ id: "a" }], "library items")).toEqual([
      { id: "a" },
    ]);
  });

  it("reads { items } envelopes", () => {
    expect(
      readItemsArray({ items: [{ id: "a" }], count: 1 }, "Prism 文件"),
    ).toEqual([{ id: "a" }]);
  });

  it("rejects malformed list payloads", () => {
    expect(() => readItemsArray({}, "tasks")).toThrow(
      "tasks 数据格式异常",
    );
  });
});
