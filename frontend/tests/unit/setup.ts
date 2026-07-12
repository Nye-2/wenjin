/**
 * Vitest setup for component tests.
 *
 * Adds @testing-library/jest-dom matchers (toBeInTheDocument,
 * toHaveTextContent, etc.) globally so component tests can assert on the
 * rendered DOM. Also auto-cleans up rendered components after each test
 * to prevent leakage.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.values.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

// Node's experimental Web Storage global can shadow jsdom with an unavailable
// localStorage. Pin one test-owned implementation for browser state and stores.
const localStorage = new MemoryStorage();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: localStorage,
});
Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: localStorage,
});

afterEach(() => {
  cleanup();
});
