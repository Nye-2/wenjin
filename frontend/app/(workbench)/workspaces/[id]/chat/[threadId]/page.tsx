"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

export default function ThreadRedirect() {
  const router = useRouter();
  const { id: workspaceId } = useParams<{ id: string }>();

  useEffect(() => {
    router.replace(`/workspaces/${workspaceId}/chat`);
  }, [router, workspaceId]);

  return null;
}
