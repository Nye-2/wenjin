/**
 * Thesis writing store for managing outline and chapter progress
 */

import { create } from "zustand";

export interface ChapterStatus {
  index: number;
  title: string;
  targetWords: number;
  currentWords: number;
  status: "pending" | "generating" | "completed" | "edited" | "failed";
}

export interface OutlineSection {
  title: string;
  position: string;
  targetWords: number;
  keyPoints: string[];
  sections: string[];
}

export interface OutlineData {
  abstract: string;
  keywords: string[];
  chapters: OutlineSection[];
}

interface ThesisWritingState {
  currentStep: 1 | 2;
  outline: OutlineData | null;
  chapters: ChapterStatus[];
  currentChapterIndex: number;
  isGenerating: boolean;
  error: string | null;

  // Actions
  setStep: (step: 1 | 2) => void;
  setOutline: (outline: OutlineData) => void;
  setChapters: (chapters: ChapterStatus[]) => void;
  setCurrentChapter: (index: number) => void;
  updateChapterStatus: (
    index: number,
    status: ChapterStatus["status"],
    words?: number
  ) => void;
  setGenerating: (isGenerating: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useThesisWritingStore = create<ThesisWritingState>((set) => ({
  currentStep: 1,
  outline: null,
  chapters: [],
  currentChapterIndex: 0,
  isGenerating: false,
  error: null,

  setStep: (step) => set({ currentStep: step }),

  setOutline: (outline) => {
    // Convert outline chapters to chapter status
    const chapters: ChapterStatus[] = outline.chapters.map((ch, idx) => ({
      index: idx,
      title: ch.title,
      targetWords: ch.targetWords,
      currentWords: 0,
      status: "pending" as const,
    }));
    set({ outline, chapters });
  },

  setChapters: (chapters) => set({ chapters }),

  setCurrentChapter: (index) => set({ currentChapterIndex: index }),

  updateChapterStatus: (index, status, words) =>
    set((state) => ({
      chapters: state.chapters.map((ch) =>
        ch.index === index
          ? { ...ch, status, currentWords: words ?? ch.currentWords }
          : ch
      ),
    })),

  setGenerating: (isGenerating) => set({ isGenerating }),

  setError: (error) => set({ error }),

  reset: () =>
    set({
      currentStep: 1,
      outline: null,
      chapters: [],
      currentChapterIndex: 0,
      isGenerating: false,
      error: null,
    }),
}));
