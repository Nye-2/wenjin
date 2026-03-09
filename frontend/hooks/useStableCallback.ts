import { useCallback, useRef } from 'react';

/**
 * Returns a stable callback that always calls the latest function.
 * Useful for avoiding unnecessary re-renders in child components.
 */
export function useStableCallback<T extends (...args: unknown[]) => unknown>(
  callback: T
): T {
  const ref = useRef<T>(callback);
  ref.current = callback;

  return useCallback(((...args: Parameters<T>) => ref.current(...args)) as T, []);
}
