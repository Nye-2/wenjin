/**
 * Stores Index
 * Re-exports all Zustand stores for Wenjin (问津)
 */

// Workspace Store
export {
  useWorkspaceStore,
  type Workspace,
  type Artifact,
  type Paper,
} from './workspace';

// Thread Store
export {
  useThreadStore,
  type Message,
} from './thread';

// Locale Store (for i18n)
export {
  useLocaleStore,
  type Locale,
} from './locale';
