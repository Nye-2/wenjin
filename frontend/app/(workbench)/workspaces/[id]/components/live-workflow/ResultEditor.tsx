import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import {
  coerceEditableValue,
  getEditableFields,
  stringifyEditableValue,
  type EditableResultKind,
} from "@/lib/workbench-result-editing";
import type { WorkbenchDraftEdit } from "@/stores/workbench-layout-store";

import { styles } from "./styles";
import { fieldLabel } from "./utils";

export function ResultEditor({
  preview,
  draft,
  disabled,
  onPatchDraft,
  onSetDraft,
}: {
  preview: WorkspaceResultPreview;
  draft?: WorkbenchDraftEdit;
  disabled: boolean;
  onPatchDraft: (outputId: string, field: string, value: unknown) => void;
  onSetDraft: (outputId: string, edit: WorkbenchDraftEdit | null) => void;
}) {
  const fields = getEditableFields(preview.kind);
  const kind = preview.kind as EditableResultKind;
  if (fields.length === 0) {
    return (
      <div style={styles.editorPanel}>
        <div style={styles.sectionTitleSmall}>只读预览</div>
        <div style={styles.sectionSubtitle}>该类型暂不支持字段编辑。</div>
      </div>
    );
  }
  const data = {
    ...(preview.data ?? {}),
    ...(draft?.data ?? {}),
  };

  return (
    <div style={styles.editorPanel} data-testid="workbench-result-editor">
      <div style={styles.sectionHeaderCompact}>
        <div>
          <div style={styles.sectionTitleSmall}>暂存编辑</div>
          <div style={styles.sectionSubtitle}>编辑只暂存在右侧，点击接受后才写入 DataService rooms。</div>
        </div>
        {draft ? (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSetDraft(preview.id, null)}
            style={styles.ghostButton}
          >
            清除编辑
          </button>
        ) : null}
      </div>
      <label style={styles.fieldLabel}>
        卡片摘要
        <input
          value={draft?.preview ?? preview.previewText ?? preview.title}
          disabled={disabled}
          onChange={(event) =>
            onSetDraft(preview.id, {
              ...(draft ?? {}),
              preview: event.target.value,
            })
          }
          style={styles.textInput}
        />
      </label>
      {fields.map((field) => {
        const value = stringifyEditableValue(data[field]);
        const longField = ["content", "abstract", "value", "description"].includes(field);
        return (
          <label key={field} style={styles.fieldLabel}>
            {fieldLabel(preview.kind, field)}
            {longField ? (
              <textarea
                value={value}
                disabled={disabled}
                rows={field === "content" ? 10 : 5}
                onChange={(event) =>
                  onPatchDraft(
                    preview.id,
                    field,
                    coerceEditableValue(kind, field, event.target.value),
                  )
                }
                style={styles.textArea}
              />
            ) : (
              <input
                value={value}
                disabled={disabled}
                onChange={(event) =>
                  onPatchDraft(
                    preview.id,
                    field,
                    coerceEditableValue(kind, field, event.target.value),
                  )
                }
                style={styles.textInput}
              />
            )}
          </label>
        );
      })}
    </div>
  );
}
