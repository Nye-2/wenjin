/**
 * Stores Index
 * Re-exports all Zustand stores for Guanlan (观澜)
 */

// Workspace Store
export {
  useWorkspaceStore,
  type Workspace,
  type Artifact,
  type Paper,
} from './workspace';

// Chat Store
export {
  useChatStore,
  type Message,
} from './chat';

// Locale Store (for i18n)
export {
  useLocaleStore,
  type Locale,
} from './locale';
