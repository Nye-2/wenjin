import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
  },
}));

import {
  createAdminModel,
  listAdminModels,
  testAdminModel,
  updateAdminModel,
} from "@/lib/api/admin-models";

describe("admin model api wrappers", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockPatch.mockReset();
  });

  it("uses admin model catalog endpoints", async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } });
    mockPost
      .mockResolvedValueOnce({ data: { model_id: "m1" } })
      .mockResolvedValueOnce({ data: { model_id: "m1", health_status: "healthy" } });
    mockPatch.mockResolvedValueOnce({ data: { model_id: "m1" } });

    await listAdminModels({ category: "llm", enabled_only: true });
    await createAdminModel({
      model_id: "m1",
      display_name: "Model 1",
      model_name: "gpt-4.1",
      base_url: "https://api.example.com/v1",
      api_key: "sk-test",
    });
    await updateAdminModel("m1", { display_name: "Model One", api_key: "" });
    await testAdminModel("m1");

    expect(mockGet).toHaveBeenCalledWith("/admin/models", {
      params: { category: "llm", enabled_only: true },
    });
    expect(mockPost).toHaveBeenNthCalledWith(1, "/admin/models", {
      model_id: "m1",
      display_name: "Model 1",
      model_name: "gpt-4.1",
      base_url: "https://api.example.com/v1",
      api_key: "sk-test",
    });
    expect(mockPatch).toHaveBeenCalledWith("/admin/models/m1", {
      display_name: "Model One",
    });
    expect(mockPost).toHaveBeenNthCalledWith(2, "/admin/models/m1/test");
  });
});
