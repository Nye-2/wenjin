/**
 * Stores Index
 * Re-exports all Zustand stores for Wenjin (问津)
 */

// Workspace Store
export {
  useWorkspaceStore,
  type Workspace,
  type Artifact,
  type Reference,
} from './workspace';

// Chat Store v2
export {
  useChatStoreV2,
  type Message,
  type Block,
} from './chat-store-v2';

// Execution Store
export {
  useExecutionStore,
} from './execution-store';

// Compute Store
export {
  useComputeStore,
} from './compute';

// Locale Store (for i18n)
export {
  useLocaleStore,
  type Locale,
} from './locale';
