"use client";

import { use } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { LiveWorkflowPanel } from "./components/LiveWorkflowPanel";
import { RoomsTopbar } from "./components/RoomsTopbar";

export default function V2Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <div className="flex flex-col h-screen">
      <RoomsTopbar workspaceId={id} data-testid="rooms-topbar" />
      <div className="flex flex-1 min-h-0">
        <ChatPanel
          workspaceId={id}
          className="w-[42%] border-r"
          data-testid="chat-panel"
        />
        <LiveWorkflowPanel
          workspaceId={id}
          className="flex-1"
          data-testid="workflow-panel"
        />
      </div>
    </div>
  );
}
