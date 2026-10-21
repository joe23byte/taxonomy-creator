import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { translate, type Lang } from "./i18n";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function timeAgo(iso: string | null | undefined, lang: Lang = "en"): string {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 10) return translate(lang, "time.justNow");
  if (diff < 60) return translate(lang, "time.secondsAgo", { n: Math.floor(diff) });
  if (diff < 3600) return translate(lang, "time.minutesAgo", { n: Math.floor(diff / 60) });
  if (diff < 86400) return translate(lang, "time.hoursAgo", { n: Math.floor(diff / 3600) });
  return new Date(iso).toLocaleDateString(lang);
}

export function formatTime(iso: string | null | undefined, lang: Lang = "en"): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDateTime(iso: string | null | undefined, lang: Lang = "en"): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" });
}

export const channelLabel: Record<string, string> = {
  voice: "Voice",
  whatsapp: "WhatsApp",
  web_messaging: "Web Messaging",
  social_media: "Social Media",
};

export function titleCase(s: string | null | undefined) {
  if (!s) return "";
  return channelLabel[s] ?? s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function sim(v: number | null | undefined) {
  return v == null ? "—" : v.toFixed(2);
}
