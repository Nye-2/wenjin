"use client";

import { useState, useEffect, useRef, useMemo } from "react";

import { useExecutionStreamV2 } from "@/hooks/useExecutionStreamV2";
import type { PhaseGroup } from "@/hooks/useExecutionStreamV2";
import type { ExecutionRecord } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";
import { ExecutionCard } from "./ExecutionCard";

// ── Types ──────────────────────────────────────────────────────────────────

interface HistoryEntry {
  id: string;
  record: ExecutionRecord;
  phases: PhaseGroup[];
}

interface ExecutionCardListProps {
  workspaceId: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function isTerminalStatus(status: string): boolean {
  return ["completed", "failed_partial", "failed", "cancelled"].includes(status);
}

// ── Component ──────────────────────────────────────────────────────────────

export function ExecutionCardList({ workspaceId }: ExecutionCardListProps) {
  const { record, phases, selectedNodeId, selectNode } =
    useExecutionStreamV2(workspaceId);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const prevStatusRef = useRef<string | null>(null);
  const frozenPhasesRef = useRef<Map<string, PhaseGroup[]>>(new Map());

  // Compute phases for the active record (non-terminal)
  const activePhases = useMemo(() => {
    if (!record || isTerminalStatus(record.status)) return [];
    return phases;
  }, [record, phases]);

  // When active record transitions to terminal, freeze it into history
  useEffect(() => {
    if (!record) return;

    const isTerminal = isTerminalStatus(record.status);

    // Freeze current phases snapshot before moving to history
    if (!isTerminal) {
      frozenPhasesRef.current.set(record.id, phases);
    }

    // Detect transition from non-terminal -> terminal
    const wasNonTerminal =
      prevStatusRef.current && !isTerminalStatus(prevStatusRef.current);

    if (isTerminal && (wasNonTerminal || prevStatusRef.current === null)) {
      // Use the frozen phases snapshot (last known non-terminal phases)
      const frozenPhases =
        frozenPhasesRef.current.get(record.id) || phases;

      setHistory((prev) => {
        // Don't duplicate
        if (prev.some((h) => h.id === record.id)) return prev;
        return [{ id: record.id, record, phases: frozenPhases }, ...prev];
      });
      setExpandedId(null);
      frozenPhasesRef.current.delete(record.id);
    }

    prevStatusRef.current = record.status;
  }, [record, phases]);

  // Auto-expand when a new running execution appears
  useEffect(() => {
    if (
      record &&
      !isTerminalStatus(record.status) &&
      expandedId !== record.id
    ) {
      setExpandedId(record.id);
    }
  }, [record, expandedId]);

  // Determine if the active record should be shown (non-terminal)
  const activeRecord =
    record && !isTerminalStatus(record.status) ? record : null;

  const cards: Array<{
    key: string;
    record: ExecutionRecord;
    phases: PhaseGroup[];
    isExpanded: boolean;
  }> = [];

  // Active (running/pending) card first
  if (activeRecord) {
    cards.push({
      key: activeRecord.id,
      record: activeRecord,
      phases: activePhases,
      isExpanded: expandedId === activeRecord.id,
    });
  }

  // History cards (newest first — already sorted)
  for (const entry of history) {
    cards.push({
      key: entry.id,
      record: entry.record,
      phases: entry.phases,
      isExpanded: expandedId === entry.id,
    });
  }

  if (cards.length === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 8,
        width: "100%",
      }}
    >
      {cards.map((card) => (
        <ExecutionCard
          key={card.key}
          record={card.record}
          phases={card.phases}
          isExpanded={card.isExpanded}
          onToggle={() =>
            setExpandedId((prev) => (prev === card.key ? null : card.key))
          }
          selectedNodeId={selectedNodeId}
          selectNode={selectNode}
        />
      ))}
    </div>
  );
}
