import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SshTerminal } from "@/components/SshTerminal";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

const AGENT_ID = "11111111-1111-1111-1111-111111111111";

// `@xterm/xterm` gerçek bir canvas/DOM rendering katmanı kullanır —
// jsdom'da bunu simüle etmek gereksiz karmaşıklık; test SADECE bu
// component'in kendi mantığını (login formu, WS mesaj protokolü, faz
// geçişleri) doğrular, gerçek terminal render'ını DEĞİL.
vi.mock("@xterm/xterm", () => {
  class MockTerminal {
    cols = 80;
    rows = 24;
    loadAddon = vi.fn();
    open = vi.fn();
    write = vi.fn();
    onData = vi.fn();
    focus = vi.fn();
    dispose = vi.fn();
  }
  return { Terminal: MockTerminal };
});
vi.mock("@xterm/addon-fit", () => {
  class MockFitAddon {
    fit = vi.fn();
  }
  return { FitAddon: MockFitAddon };
});

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;

  url: string;
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((evt: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = 3;
  }

  triggerOpen() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  triggerMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

function renderTerminal() {
  return render(
    <LocaleProvider>
      <SshTerminal agentId={AGENT_ID} />
    </LocaleProvider>
  );
}

async function submitLogin(username: string, password: string) {
  fireEvent.change(screen.getByLabelText(tr.sshTerminal.username), { target: { value: username } });
  fireEvent.change(screen.getByLabelText(tr.sshTerminal.password), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: tr.sshTerminal.connect }));
  await waitFor(() => expect(FakeWebSocket.instances.length).toBeGreaterThan(0));
  return FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
}

describe("SshTerminal", () => {
  afterEach(() => {
    FakeWebSocket.instances = [];
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("shows a login form before connecting", () => {
    renderTerminal();
    expect(screen.getByLabelText(tr.sshTerminal.username)).toBeInTheDocument();
    expect(screen.getByLabelText(tr.sshTerminal.password)).toHaveAttribute("type", "password");
  });

  it("opens a WebSocket to the agent's SSH endpoint and sends credentials on open", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    renderTerminal();
    const ws = await submitLogin("bob", "s3cr3t");

    expect(ws.url).toContain(`/api/agents/${AGENT_ID}/ssh`);

    ws.triggerOpen();
    const sentInit = JSON.parse(ws.sent[0]);
    expect(sentInit).toEqual({ type: "connect", username: "bob", password: "s3cr3t", cols: 80, rows: 24 });
  });

  it("shows the terminal and clears the password field once connected", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    renderTerminal();
    const ws = await submitLogin("bob", "s3cr3t");
    ws.triggerOpen();
    ws.triggerMessage({ type: "connected" });

    await waitFor(() => expect(screen.queryByLabelText(tr.sshTerminal.password)).not.toBeInTheDocument());
  });

  it("shows an honest error message when authentication fails", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    renderTerminal();
    const ws = await submitLogin("bob", "wrong-password");
    ws.triggerOpen();
    ws.triggerMessage({ type: "error", message: "Kimlik doğrulama başarısız" });

    expect(await screen.findByText("Kimlik doğrulama başarısız")).toBeInTheDocument();
    // Parola hiçbir zaman DOM'da (hata mesajında dahil) görünmemeli.
    expect(screen.queryByText(/wrong-password/)).not.toBeInTheDocument();
  });

  it("shows a session-closed message when the backend sends 'closed'", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    renderTerminal();
    const ws = await submitLogin("bob", "s3cr3t");
    ws.triggerOpen();
    ws.triggerMessage({ type: "connected" });
    ws.triggerMessage({ type: "closed" });

    expect(await screen.findByText(tr.sshTerminal.sessionClosed)).toBeInTheDocument();
  });

  it("closes the WebSocket on unmount", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const { unmount } = renderTerminal();
    await submitLogin("bob", "s3cr3t");
    const ws = FakeWebSocket.instances[0];
    const closeSpy = vi.spyOn(ws, "close");

    unmount();

    expect(closeSpy).toHaveBeenCalled();
  });
});
