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

type DurationUnitsDict = (typeof translations)["tr"]["common"]["durationUnits"];

/** Bir sürenin (saniye) kompakt "Xg Ys" biçimi — Silinen Agent'lar
 * ekranındaki "ne kadar süre aktifti" sütunu için. `timeAgo`'nun
 * aksine bir "önce" anlamı TAŞIMAZ, yalnızca ham bir aralık uzunluğu. */
export function formatDuration(seconds: number, t: DurationUnitsDict): string {
  const totalMinutes = Math.floor(seconds / 60);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;

  if (days > 0) return `${days}${t.days} ${hours}${t.hours}`;
  if (hours > 0) return `${hours}${t.hours} ${minutes}${t.minutes}`;
  return `${minutes}${t.minutes}`;
}
