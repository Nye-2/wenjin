import axios from "axios";

import { API_SERVER_BASE_URL } from "@/lib/api/client";

export async function healthCheck(): Promise<{
  status: string;
  version: string;
}> {
  const response = await axios.get(`${API_SERVER_BASE_URL}/health`, {
    timeout: 30000,
  });
  return response.data;
}
