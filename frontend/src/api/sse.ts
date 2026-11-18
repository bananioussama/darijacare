// Analyseur incrémental d'un flux text/event-stream (format WHATWG, champs event et data).
// POST /chat renvoie un flux SSE : EventSource ne permettant que GET, le flux est lu avec
// fetch et découpé ici, quel que soit le découpage des paquets réseau.

export interface SseEvent {
  event: string;
  data: string;
}

function parseBlock(block: string): SseEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue; // ligne vide ou commentaire
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length > 0 ? { event, data: data.join("\n") } : null;
}

export class SseParser {
  private buffer = "";
  private pendingCR = false;

  /** Ajoute un morceau de texte et renvoie les événements complets. */
  push(chunk: string): SseEvent[] {
    let text = this.pendingCR ? `\r${chunk}` : chunk;
    // Un \r en fin de morceau peut être la première moitié d'un \r\n : on l'attend.
    this.pendingCR = text.endsWith("\r");
    if (this.pendingCR) text = text.slice(0, -1);
    this.buffer += text.replace(/\r\n?/g, "\n");
    const events: SseEvent[] = [];
    let end = this.buffer.indexOf("\n\n");
    while (end >= 0) {
      const event = parseBlock(this.buffer.slice(0, end));
      if (event) events.push(event);
      this.buffer = this.buffer.slice(end + 2);
      end = this.buffer.indexOf("\n\n");
    }
    return events;
  }

  /** Fin du flux : renvoie le dernier événement s'il n'était pas suivi d'une ligne vide. */
  flush(): SseEvent[] {
    const rest = this.buffer + (this.pendingCR ? "\n" : "");
    this.buffer = "";
    this.pendingCR = false;
    const event = rest.trim() ? parseBlock(rest.replace(/\n+$/, "")) : null;
    return event ? [event] : [];
  }
}
