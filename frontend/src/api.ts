import { apiUrl } from "./config";

export interface HealthResult {
  ok: boolean;
  detail: string;
}

async function check(path: string): Promise<HealthResult> {
  try {
    const response = await fetch(apiUrl(path), { headers: { Accept: "application/json" } });
    return { ok: response.ok, detail: `HTTP ${response.status}` };
  } catch {
    return { ok: false, detail: "연결 실패" };
  }
}

export const checkApi = (): Promise<HealthResult> => check("/health");
export const checkDatabase = (): Promise<HealthResult> => check("/health/db");
