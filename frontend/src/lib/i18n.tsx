import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import en from "@/i18n/en.json";
import de from "@/i18n/de.json";

export const LANGUAGES = { en: "English", de: "Deutsch" } as const;
export type Lang = keyof typeof LANGUAGES;
type Dict = { [key: string]: string | Dict };
type Vars = Record<string, string | number | null | undefined>;

const DICTS: Record<Lang, Dict> = { en, de };
const STORAGE_KEY = "intent-studio-lang";

function lookup(dict: Dict, key: string): string | undefined {
  let cur: string | Dict | undefined = dict;
  for (const part of key.split(".")) {
    if (cur == null || typeof cur === "string") return undefined;
    cur = cur[part];
  }
  return typeof cur === "string" ? cur : undefined;
}

export function translate(lang: Lang, key: string, vars?: Vars): string {
  // "_one" / "_other" variants are picked by vars.count
  const plural = vars && typeof vars.count === "number" ? `${key}_${vars.count === 1 ? "one" : "other"}` : null;
  const text = (plural && (lookup(DICTS[lang], plural) ?? lookup(DICTS.en, plural)))
    ?? lookup(DICTS[lang], key) ?? lookup(DICTS.en, key) ?? key;
  return vars ? text.replace(/\{(\w+)\}/g, (m, name) => (vars[name] != null ? String(vars[name]) : m)) : text;
}

interface I18n {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string, vars?: Vars) => string;
  pct: (value: number, digits?: number) => string;
}

const I18nContext = createContext<I18n | null>(null);

function initialLang(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && stored in LANGUAGES) return stored as Lang;
  return navigator.language?.toLowerCase().startsWith("de") ? "de" : "en";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = useCallback((l: Lang) => {
    localStorage.setItem(STORAGE_KEY, l);
    setLangState(l);
  }, []);
  const value = useMemo<I18n>(() => {
    const percent = (digits: number) => new Intl.NumberFormat(lang, { style: "percent", maximumFractionDigits: digits, minimumFractionDigits: digits });
    return {
      lang,
      setLang,
      t: (key, vars) => translate(lang, key, vars),
      pct: (v, digits = 0) => percent(digits).format(v),
    };
  }, [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}
