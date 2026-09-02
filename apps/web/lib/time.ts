import type { translations } from "@/lib/i18n/translations";

type TimeAgoDict = (typeof translations)["tr"]["timeAgo"];

export function timeAgo(isoTimestamp: string, t: TimeAgoDict): string {
  const diffMs = Date.now() - new Date(isoTimestamp).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return t.justNow;
  if (minutes < 60) return t.minutesAgo(minutes);
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t.hoursAgo(hours);
  const days = Math.floor(hours / 24);
  return t.daysAgo(days);
}
