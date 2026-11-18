import { describe, expect, it } from "vitest";

import { currentSession, isExpired, listSessions, saveSession, updateSession } from "./sessions";

describe("sessions", () => {
  it("keeps the newest open session as the current one", () => {
    saveSession("a", "jeton-a", 3600, "premier");
    saveSession("b", "jeton-b", 3600, "second");
    expect(listSessions().map((s) => s.session_id)).toEqual(["b", "a"]);
    expect(currentSession()?.session_id).toBe("b");
    updateSession("b", { closed: true });
    expect(currentSession()?.session_id).toBe("a");
  });

  it("ignores expired sessions and survives a broken storage", () => {
    const old = saveSession("c", "jeton-c", -1);
    expect(isExpired(old)).toBe(true);
    expect(currentSession()).toBeNull();
    localStorage.setItem("darijacare.sessions", "{pas du json");
    expect(listSessions()).toEqual([]);
  });
});
