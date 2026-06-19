import { useCallback, useEffect, useState } from "react";

import { SessionsApi, type SessionEvent } from "./api";
import type { PlatformSlug } from "./platforms";
import type { SessionInfo } from "./types";

type PendingAction = "create" | "launch" | "check" | "delete" | null;

export function useSessions(platform: PlatformSlug | undefined) {
  const [items, setItems] = useState<SessionInfo[]>([]);
  const [pending, setPending] = useState<PendingAction>(null);
  const [pendingSessionId, setPendingSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastCheck, setLastCheck] = useState<
    Record<string, { logged_in: boolean; url: string }>
  >({});

  const refresh = useCallback(async () => {
    if (!platform) return;
    setError(null);
    try {
      const rows = await SessionsApi.list(platform);
      setItems(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [platform]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!platform) return;

    const onSession = (event: SessionEvent) => {
      if (event.route !== "session.closed") return;
      const sessionId = event.payload.session_id;
      setItems((current) =>
        current.map((item) => {
          if (item.id !== sessionId) return item;
          const activeRunCount = Math.max(0, item.active_run_count - 1);
          return {
            ...item,
            active_run_count: activeRunCount,
            status: activeRunCount > 0 ? "running" : "idle",
          };
        }),
      );
      void refresh();
    };

    void SessionsApi.subscribe(onSession);
    return () => SessionsApi.unsubscribe(onSession);
  }, [platform, refresh]);

  const createSession = useCallback(
    async (name: string, launchFresh = true) => {
      if (!platform) return null;
      setPending("create");
      setError(null);
      try {
        const session = await SessionsApi.create(platform, name);
        if (launchFresh) {
          const launched = await SessionsApi.launch(session.id, true);
          const created = launched.session;
          setItems((current) =>
            [...current, created].sort((a, b) => a.name.localeCompare(b.name)),
          );
          return created;
        }
        setItems((current) =>
          [...current, session].sort((a, b) => a.name.localeCompare(b.name)),
        );
        return session;
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        return null;
      } finally {
        setPending(null);
      }
    },
    [platform],
  );

  const launchSession = useCallback(async (sessionId: string, fresh = false) => {
    setPending("launch");
    setPendingSessionId(sessionId);
    setError(null);
    try {
      const result = await SessionsApi.launch(sessionId, fresh);
      setItems((current) =>
        current.map((item) =>
          item.id === result.session.id ? result.session : item,
        ),
      );
      return result.session;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      setPending(null);
      setPendingSessionId(null);
    }
  }, []);

  const checkSession = useCallback(async (sessionId: string) => {
    setPending("check");
    setPendingSessionId(sessionId);
    setError(null);
    try {
      const result = await SessionsApi.check(sessionId);
      setItems((current) =>
        current.map((item) =>
          item.id === result.session.id ? result.session : item,
        ),
      );
      setLastCheck((current) => ({
        ...current,
        [result.session.id]: {
          logged_in: result.logged_in,
          url: result.url,
        },
      }));
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      setPending(null);
      setPendingSessionId(null);
    }
  }, []);

  const deleteSession = useCallback(async (sessionId: string) => {
    setPending("delete");
    setPendingSessionId(sessionId);
    setError(null);
    try {
      await SessionsApi.delete(sessionId);
      setItems((current) => current.filter((item) => item.id !== sessionId));
      setLastCheck((current) => {
        const next = { ...current };
        delete next[sessionId];
        return next;
      });
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return false;
    } finally {
      setPending(null);
      setPendingSessionId(null);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
    items,
    pending,
    pendingSessionId,
    error,
    lastCheck,
    refresh,
    createSession,
    launchSession,
    checkSession,
    deleteSession,
    clearError,
  };
}

export function usePlatformSessions(platform: PlatformSlug | undefined) {
  const state = useSessions(platform);
  return {
    sessions: state.items,
    ...state,
  };
}
