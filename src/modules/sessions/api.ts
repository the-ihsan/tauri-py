import { Backend, type DaemonEvent } from "@/lib/api";

import type { PlatformSlug } from "./platforms";
import type {
  SessionCheckResult,
  SessionClosedPayload,
  SessionInfo,
  SessionLaunchResult,
  StoredCookie,
} from "./types";

export type SessionEvent = DaemonEvent<SessionClosedPayload>;

const CHANNEL = "session";

export class SessionsApi {
  static list(platform: PlatformSlug) {
    return Backend.request<SessionInfo[]>("sessions.list", { platform });
  }

  static create(platform: PlatformSlug, name: string) {
    return Backend.request<SessionInfo>("sessions.create", { platform, name });
  }

  static delete(sessionId: string) {
    return Backend.request<void>("sessions.delete", { session_id: sessionId });
  }

  static launch(sessionId: string, fresh = false) {
    return Backend.request<SessionLaunchResult>("sessions.launch", {
      session_id: sessionId,
      fresh,
    });
  }

  static check(sessionId: string) {
    return Backend.request<SessionCheckResult>("sessions.check", {
      session_id: sessionId,
    });
  }

  static cookies(sessionId: string) {
    return Backend.request<StoredCookie[]>("sessions.cookies", {
      session_id: sessionId,
    });
  }

  static subscribe(cb: (event: SessionEvent) => void) {
    return Backend.subscribeDaemon<SessionClosedPayload>(CHANNEL, cb);
  }

  static unsubscribe(cb: (event: SessionEvent) => void) {
    Backend.unsubscribeDaemon(cb as never);
  }
}
