import { useEffect, useRef, useState } from "react";

import type { LatexFeedbackItem } from "@/lib/api";
import {
  getLatexProjectFeedback,
  saveLatexProjectFeedback,
} from "@/lib/api";
import { readClientErrorMessage } from "./clientErrors";

export function useLatexFeedbackPersistence(projectId: string) {
  const [feedbackItems, setFeedbackItems] = useState<LatexFeedbackItem[]>([]);
  const [feedbackLoaded, setFeedbackLoaded] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState("");
  const [feedbackError, setFeedbackError] = useState("");
  const feedbackSaveTimerRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setFeedbackLoaded(false);
    setFeedbackItems([]);
    setFeedbackError("");
    setFeedbackStatus("");
    const load = async () => {
      try {
        const response = await getLatexProjectFeedback(projectId);
        if (cancelled) {
          return;
        }
        const normalized = Array.isArray(response.items)
          ? response.items
            .filter((item) => Boolean(item && typeof item === "object"))
            .map((item) => ({
              ...item,
              created_at: item.created_at || new Date().toISOString(),
            }))
          : [];
        setFeedbackItems(normalized);
      } catch (err) {
        if (!cancelled) {
          setFeedbackError(`加载点评失败: ${readClientErrorMessage(err)}`);
        }
      } finally {
        if (!cancelled) {
          setFeedbackLoaded(true);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (!feedbackLoaded) {
      return;
    }
    if (feedbackSaveTimerRef.current) {
      window.clearTimeout(feedbackSaveTimerRef.current);
    }
    feedbackSaveTimerRef.current = window.setTimeout(() => {
      void saveLatexProjectFeedback(projectId, feedbackItems).catch((err) => {
        setFeedbackError(`保存点评失败: ${readClientErrorMessage(err)}`);
      });
    }, 500);
    return () => {
      if (feedbackSaveTimerRef.current) {
        window.clearTimeout(feedbackSaveTimerRef.current);
        feedbackSaveTimerRef.current = null;
      }
    };
  }, [feedbackItems, feedbackLoaded, projectId]);

  return {
    feedbackItems,
    feedbackLoaded,
    feedbackStatus,
    feedbackError,
    setFeedbackItems,
    setFeedbackStatus,
    setFeedbackError,
  };
}
