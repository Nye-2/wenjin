import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { proxy } from "@/proxy";

describe("proxy", () => {
  it("keeps the pricing page public", () => {
    const response = proxy(new NextRequest("http://localhost:3000/pricing"));

    expect(response.headers.get("location")).toBeNull();
  });
});
