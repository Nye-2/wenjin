import { describe, expect, it } from "vitest";

import {
  findLatestIntakeSpec,
  readIntakeSpecFromToolResultData,
} from "@/lib/intake-spec";
import type { Message } from "@/stores/chat-store";

const softwareSpec = {
  schema_version: "wenjin.intake_spec.v1",
  spec_id: "intake-1",
  revision: 1,
  workspace_id: "ws-1",
  workspace_type: "software_copyright",
  capability_id: "software_copyright_application_pack",
  title: "智慧排课系统软著申报 Spec",
  status: "ready",
  markdown: "# 智慧排课系统软著申报 Spec\n\n生成申报材料包。",
  params: {
    software_name: "智慧排课系统",
    target_platform: "web",
  },
  missing_fields: [],
  assumptions: ["按 Web 管理系统生成。"],
};

describe("intake spec helpers", () => {
  it("reads intake specs from draft_intake_spec tool results", () => {
    const spec = readIntakeSpecFromToolResultData({
      tool: "draft_intake_spec",
      status: "ready",
      output: {
        status: "ready",
        intake_spec: softwareSpec,
      },
    });

    expect(spec?.title).toBe("智慧排课系统软著申报 Spec");
    expect(spec?.capability_id).toBe("software_copyright_application_pack");
  });

  it("finds the newest assistant intake spec for a workspace", () => {
    const messages: Message[] = [
      {
        id: "msg-1",
        role: "assistant",
        createdAt: "2026-06-29T00:00:00Z",
        blocks: [
          {
            kind: "tool_result",
            tool: "draft_intake_spec",
            status: "draft",
            output: {
              status: "draft",
              intake_spec: {
                ...softwareSpec,
                spec_id: "intake-old",
                title: "旧 Spec",
                status: "draft",
              },
            },
          },
        ],
      },
      {
        id: "msg-2",
        role: "assistant",
        createdAt: "2026-06-29T00:01:00Z",
        blocks: [
          {
            kind: "tool_result",
            tool: "draft_intake_spec",
            status: "ready",
            output: {
              status: "ready",
              intake_spec: softwareSpec,
            },
          },
        ],
      },
    ];

    expect(findLatestIntakeSpec(messages, "ws-1")?.spec_id).toBe("intake-1");
    expect(findLatestIntakeSpec(messages, "other")).toBeNull();
  });
});
