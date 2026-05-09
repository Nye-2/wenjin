"use client";

interface V2BannerProps {
  workspaceId: string;
}

export function V2Banner({ workspaceId }: V2BannerProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 12,
        padding: "10px 16px",
        background: "linear-gradient(90deg, var(--v2-accent-purple-100), var(--v2-accent-purple-100))",
        borderBottom: "1px solid var(--v2-accent-purple-300)",
        fontSize: 13.5,
        color: "var(--v2-text-primary)",
        fontFamily: "var(--v2-font-sans)",
      }}
    >
      <span>升级到 v2 体验？</span>
      <a
        href={`/workspaces/${workspaceId}/v2`}
        style={{
          padding: "4px 12px",
          borderRadius: "var(--v2-radius-sm)",
          background: "var(--v2-accent-purple-700)",
          color: "white",
          textDecoration: "none",
          fontWeight: 500,
          fontSize: 13,
        }}
      >
        切换到 v2
      </a>
    </div>
  );
}
