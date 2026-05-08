# Chat Flat-Flow + ResultCard Beautification Design

## Context

The current chat panel wraps every user-agent exchange in a `RunContainer` with "轮 N · title ✓" headers. This was designed for Compute feature executions but applies to ALL interactions, including simple greetings. Users see "轮 1 · 你好 ✓", "轮 2 · 运行 ✓" etc., which feels unnatural for a chat interface.

Additionally, user messages are wrapped inside card containers rather than appearing as standalone bubbles, and the `result_card` visual design uses dashed borders and gradients that look rough.

## Design Decisions

1. **No runs in chat** — messages flow naturally like a normal conversation
2. **User messages** — right-aligned bubbles, standalone (not inside any card)
3. **Agent text messages** — left-aligned simple bubbles (no card border)
4. **Agent result_card** — card style retained but beautified (solid border, white background, clean modern look)
5. **Agent question_card** — card style retained (brass accent, unchanged)
6. **Agent status_line** — inline lightweight row (unchanged)
7. **Compute progress** — only shown in the right panel (实时工作台)

## Architecture Changes

### MessageList.tsx — Flatten message rendering

Remove:
- `groupByRun()` function
- `RunContainer` import and usage
- `deriveRunTitle()` function
- `currentRunId` prop

New rendering logic:
```
messages.map(m =>
  m.role === "user"
    ? right-aligned bubble
    ? left-aligned, render blocks individually:
      - text → simple bubble (new style, no card border)
      - status_line → inline row
      - question_card → brass card
      - result_card → modern card (new style)
)
```

### Agent text bubble — New simple style

Replace the current bordered container with a simple bubble:
- Background: `var(--bg-elevated)` (white)
- No border
- Subtle shadow or just background color distinction
- Rounded corners (matching user bubble style)
- Max-width: 95%

### ResultCardBlock.tsx — Beautified card

Current: dashed border, teal gradient background, rounded-xl
New:
- Solid border: `1px solid rgba(46, 111, 109, 0.2)`
- White background: `#FFFFFF`
- Subtle shadow: `0 1px 3px rgba(0, 0, 0, 0.06)`
- Clean typography, better spacing
- Keep brand-teal accent for header, findings numerals, TL;DR prefix
- Keep "已完成" badge
- Keep feedback pills

### Files to delete

- `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/RunContainer.tsx` — no longer needed

### Files to modify

- `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/MessageList.tsx` — flatten rendering
- `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/ResultCardBlock.tsx` — beautify
- `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/TextBlock.tsx` — may need style update
- `frontend/app/(workbench)/workspaces/[id]/chat/page.tsx` — remove currentRunId dependency

### Files unchanged

- `QuestionCardBlock.tsx` — brass accent card, no changes needed
- `StatusLineBlock.tsx` — inline row, no changes needed
- `LiveWorkflowPanel.tsx` — right panel, unaffected
- Backend — no changes needed (run_id still exists in data, just not rendered in chat)

## Verification

1. Send "你好" — should appear as a simple user bubble + agent text bubble, no run headers
2. Send a research question — agent text replies as simple bubbles
3. Launch a Compute feature — result_card appears as a clean modern card
4. Question cards still work with pill buttons
5. Right panel (实时工作台) still shows run progress normally
6. Frontend build passes
