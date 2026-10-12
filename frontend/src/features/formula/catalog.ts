import { useCallback, useEffect, useState } from "react";
import { getFunctions } from "./api";
import type { FunctionCatalog } from "./types";

/**
 * D1(함수 목록·셀 오류 문구)은 사용자가 바꾸지 못하는 사전에서 만들어지므로 화면 수명 동안 한 번만 읽는다.
 * 실패하면 캐시를 비워 다음에 다시 읽는다.
 */
let cached: Promise<FunctionCatalog> | null = null;

export function loadCatalog(): Promise<FunctionCatalog> {
  if (!cached) {
    cached = getFunctions().catch((error: unknown) => {
      cached = null;
      throw error;
    });
  }
  return cached;
}

/** 시험용: 캐시를 비운다. */
export function resetCatalogCache(): void {
  cached = null;
}

export type CatalogState = { status: "off" | "loading" } | { status: "ready"; catalog: FunctionCatalog } | { status: "error"; error: unknown };

/** enabled가 false면 호출하지 않는다(계산 열이 없는 데이터셋은 D1이 필요 없다). */
export function useFunctionCatalog(enabled: boolean): CatalogState & { reload: () => void } {
  const [state, setState] = useState<CatalogState>({ status: "loading" });
  const [token, setToken] = useState(0);
  const reload = useCallback(() => {
    cached = null;
    setState({ status: "loading" });
    setToken((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    loadCatalog()
      .then((catalog) => active && setState({ status: "ready", catalog }))
      .catch((error: unknown) => active && setState({ status: "error", error }));
    return () => {
      active = false;
    };
  }, [enabled, token]);

  return { ...(enabled ? state : ({ status: "off" } as CatalogState)), reload };
}
