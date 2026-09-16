import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TicketDetailModal } from "@/components/TicketDetailModal";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

const k = tr.tickets;

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

function ticketFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "t1",
    ticket_number: "INC-2026-0001",
    title: "Switch portu down",
    description: "port 12 flapping",
    category_id: "cat-net",
    category_name: "Ağ",
    department_id: "dep-it",
    department_name: "IT",
    priority: "HIGH",
    status: "OPEN",
    created_by: "u1",
    created_by_username: "operator1",
    assigned_to: null,
    assigned_to_username: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    resolved_at: null,
    sla_due_at: null,
    comments: [
      {
        id: "c0",
        ticket_id: "t1",
        author_id: "u1",
        author_username: "operator1",
        event: "created",
        body: null,
        status_from: null,
        status_to: "OPEN",
        assigned_from_username: null,
        assigned_to_username: null,
        is_internal: false,
        created_at: new Date().toISOString(),
      },
      {
        id: "c1",
        ticket_id: "t1",
        author_id: "u2",
        author_username: "tech1",
        event: "comment",
        body: "Sadece IT'nin göreceği gizli not",
        status_from: null,
        status_to: null,
        assigned_from_username: null,
        assigned_to_username: null,
        is_internal: true,
        created_at: new Date().toISOString(),
      },
    ],
    ...overrides,
  };
}

function mockFetch(handlers: { ticketRole?: "REQUESTER" | "TECHNICIAN" | "ADMIN"; ticket?: unknown; onRequest?: (method: string, url: string, body?: string) => unknown }) {
  const calls: { method: string; url: string; body?: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body as string | undefined;
      calls.push({ method, url, body });

      if (url.includes("/api/auth/me")) {
        return { ok: true, json: async () => mockCurrentUser(["TICKETS_VIEW"], { ticket_role: handlers.ticketRole ?? "TECHNICIAN" }) };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url, body);
        if (custom !== undefined) return custom;
      }
      if (url.includes("/api/tickets/assignable-users")) {
        return { ok: true, json: async () => [] };
      }
      if (url.includes("/api/tickets/t1")) {
        return { ok: true, json: async () => handlers.ticket ?? ticketFixture() };
      }
      return Promise.reject(new Error(`Unexpected request: ${method} ${url}`));
    }),
  );
  return calls;
}

function renderModal(props: Partial<Parameters<typeof TicketDetailModal>[0]> = {}) {
  setLoggedInToken();
  return render(
    <LocaleProvider>
      <AuthProvider>
        <TicketDetailModal ticketId="t1" onClose={vi.fn()} onChanged={vi.fn()} {...props} />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("TicketDetailModal", () => {
  it("IT staff sees reply tabs + quick action bar, and internal tab sends is_internal:true", async () => {
    const calls = mockFetch({
      ticketRole: "TECHNICIAN",
      onRequest: (method, url) => {
        if (method === "POST" && url.includes("/comments")) {
          return { ok: true, json: async () => ticketFixture() };
        }
        return undefined;
      },
    });
    renderModal();

    await waitFor(() => expect(screen.getByText(k.replyTabPublic)).toBeInTheDocument());
    expect(screen.getByText(k.assignToMe)).toBeInTheDocument();
    expect(screen.getByText(k.markResolved)).toBeInTheDocument();
    expect(screen.getByText(k.closeTicket)).toBeInTheDocument();

    fireEvent.click(screen.getByText(k.replyTabInternal));
    fireEvent.change(screen.getByPlaceholderText(k.internalReplyPlaceholder), { target: { value: "gizli not" } });
    fireEvent.click(screen.getByText(k.send));

    await waitFor(() => {
      const postCall = calls.find((c) => c.method === "POST" && c.url.includes("/comments"));
      expect(postCall).toBeDefined();
      expect(JSON.parse(postCall!.body!)).toMatchObject({ body: "gizli not", is_internal: true });
    });
  });

  it("REQUESTER does not see the internal note tab or the IT quick action bar", async () => {
    mockFetch({ ticketRole: "REQUESTER" });
    renderModal();

    await waitFor(() => expect(screen.getByText("INC-2026-0001", { exact: false })).toBeInTheDocument());
    expect(screen.queryByText(k.replyTabInternal)).not.toBeInTheDocument();
    expect(screen.queryByText(k.assignToMe)).not.toBeInTheDocument();
    expect(screen.queryByText(k.closeTicket)).not.toBeInTheDocument();
  });

  it("renders the internal-note badge for hidden comments visible to IT staff", async () => {
    mockFetch({ ticketRole: "TECHNICIAN" });
    renderModal();

    await waitFor(() => expect(screen.getByText("Sadece IT'nin göreceği gizli not")).toBeInTheDocument());
    expect(screen.getByText(k.internalNoteBadge)).toBeInTheDocument();
  });
});
