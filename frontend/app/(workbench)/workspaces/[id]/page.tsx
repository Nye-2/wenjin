import { redirect } from "next/navigation";
import { isFlagEnabled } from "@/lib/flags";

export default function WorkspaceRootPage({ params }: { params: Promise<{ id: string }> }) {
  if (isFlagEnabled("default_to_v2")) {
    void params; // consume the promise
    redirect("./v2");
  }
  redirect("./chat");
}
