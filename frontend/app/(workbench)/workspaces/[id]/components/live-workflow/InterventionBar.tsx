import { styles } from "./styles";

export function InterventionBar({
  value,
  disabled,
  status,
  onChange,
  onSubmit,
}: {
  value: string;
  disabled: boolean;
  status: string | null;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  return (
    <div style={styles.interventionBar}>
      <textarea
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        placeholder="补充新的约束、方向或纠错信息。问津会先在安全点中断当前任务，再通过对话继续编排后续处理。"
        rows={2}
        style={styles.interventionInput}
      />
      <button
        type="button"
        disabled={disabled || !value.trim()}
        onClick={onSubmit}
        style={{
          ...styles.primaryButton,
          opacity: disabled || !value.trim() ? 0.55 : 1,
        }}
      >
        提交介入
      </button>
      {status ? <span style={styles.interventionStatus}>{status}</span> : null}
    </div>
  );
}
