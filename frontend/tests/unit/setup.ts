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

afterEach(() => {
  cleanup();
});
