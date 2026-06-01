import type { LatexCompileResult } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export function LatexCompileLogDialog({
  open,
  compileResult,
  compileLog,
  onOpenChange,
}: {
  open: boolean;
  compileResult: LatexCompileResult | null;
  compileLog: string;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-5xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>编译后台详情</DialogTitle>
          <DialogDescription>
            历史 ID：{compileResult?.history_id || "-"}
          </DialogDescription>
        </DialogHeader>
        {compileResult ? (
          <div className="grid gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-sm text-[var(--text-secondary)] md:grid-cols-2">
            <p>状态：{compileResult.ok ? "成功" : "失败"}</p>
            <p>编译器：{compileResult.engine}</p>
            <p>主文件：{compileResult.main_file}</p>
            <p>退出码：{compileResult.status}</p>
          </div>
        ) : null}
        <pre className="max-h-[56vh] overflow-auto rounded-xl bg-[rgba(19,34,53,0.05)] p-4 text-xs leading-6 text-[var(--text-secondary)]">
          {compileLog || compileResult?.error || "暂无日志"}
        </pre>
      </DialogContent>
    </Dialog>
  );
}
