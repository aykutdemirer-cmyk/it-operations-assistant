// Faz 62 — bilet öncelik/durum → rozet CSS sınıfı eşlemesi. Hem
// `TicketsPanel` hem `TicketDetailModal` aynı renkleri kullansın diye
// ortak dosyada (KOPYALANMADI). `styles` = `AgentsList.module.css`.
import type { TicketPriority, TicketStatus } from "@/lib/api";

export function priorityBadgeClass(priority: TicketPriority, styles: Record<string, string>): string {
  switch (priority) {
    case "CRITICAL":
      return styles.badgeRed;
    case "HIGH":
      return styles.badgeOrange;
    case "MEDIUM":
      return styles.badgeBlue;
    case "LOW":
      return styles.badgeNeutral;
  }
}

export function statusBadgeClass(status: TicketStatus, styles: Record<string, string>): string {
  switch (status) {
    case "OPEN":
      return styles.badgeBlue;
    case "IN_PROGRESS":
      return styles.badgeYellow;
    case "WAITING_USER":
      return styles.badgeNeutral;
    case "RESOLVED":
      return styles.badgeGreen;
    case "CLOSED":
      return styles.badgeNeutral;
  }
}
