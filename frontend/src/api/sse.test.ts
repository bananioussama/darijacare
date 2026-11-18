import { describe, expect, it } from "vitest";

import { SseParser } from "./sse";

describe("SseParser", () => {
  it("rebuilds events whatever the chunk boundaries", () => {
    const text = 'event: analysis\ndata: {"a":1}\n\nevent: token\ndata: {"text":"salam "}\n\n';
    for (const size of [1, 2, 3, 5, 8, 13, text.length]) {
      const parser = new SseParser();
      const events = [];
      for (let i = 0; i < text.length; i += size)
        events.push(...parser.push(text.slice(i, i + size)));
      events.push(...parser.flush());
      expect(events).toEqual([
        { event: "analysis", data: '{"a":1}' },
        { event: "token", data: '{"text":"salam "}' },
      ]);
    }
  });

  it("handles CRLF, a CR split across chunks, comments and multi-line data", () => {
    const parser = new SseParser();
    const events = [
      ...parser.push(": commentaire\r\nevent: done\r"),
      ...parser.push("\ndata: ligne 1\r\ndata: ligne 2\r\n\r\n"),
    ];
    expect(events).toEqual([{ event: "done", data: "ligne 1\nligne 2" }]);
  });

  it("returns a final event without trailing blank line on flush", () => {
    const parser = new SseParser();
    expect(parser.push("event: sources\ndata: []")).toEqual([]);
    expect(parser.flush()).toEqual([{ event: "sources", data: "[]" }]);
  });
});
