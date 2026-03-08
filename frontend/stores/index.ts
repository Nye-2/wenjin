/**
 * Stores Index
 * Re-exports all Zustand stores for AcademiaGPT
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
