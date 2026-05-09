import { redirect } from "next/navigation";

export default function WorkspaceRootPage({ params }: { params: Promise<{ id: string }> }) {
  void params;
  redirect("./v2");
}
