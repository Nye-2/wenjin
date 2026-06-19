import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { proxy } from "@/proxy";

describe("proxy", () => {
  it("keeps the pricing page public", () => {
    const response = proxy(new NextRequest("http://localhost:3000/pricing"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("does not use a client-writable auth cookie as a server-side access gate", () => {
    const request = new NextRequest("http://localhost:3000/workspaces/ws-1", {
      headers: {
        cookie: encodeURIComponent(
          JSON.stringify({ state: { isAuthenticated: false } }),
        ),
      },
    });

    const response = proxy(request);

    expect(response.headers.get("location")).toBeNull();
  });
});
