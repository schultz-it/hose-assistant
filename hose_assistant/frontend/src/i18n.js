// Minimal i18n: English catalog is the source of truth (SPEC section 10).
// Adding a language = one JSON file + an entry here; t() falls back to
// English for missing keys, then to the key itself.
import en from "./i18n/en.json";
import it from "./i18n/it.json";
import fr from "./i18n/fr.json";
import de from "./i18n/de.json";
import es from "./i18n/es.json";
import pt from "./i18n/pt.json";
import zh from "./i18n/zh.json";
import ja from "./i18n/ja.json";
import ar from "./i18n/ar.json";
import brz from "./i18n/brz.json";

export const LANGUAGES = {
  en: "English",
  it: "Italiano",
  fr: "Français",
  de: "Deutsch",
  es: "Español",
  pt: "Português",
  zh: "中文",
  ja: "日本語",
  ar: "العربية",
  brz: "Brianzöö",
};
const CATALOGS = { en, it, fr, de, es, pt, zh, ja, ar, brz };
const RTL = new Set(["ar"]);

let catalog = en;

export function setLang(lang) {
  catalog = CATALOGS[lang] ?? en;
  // Right-to-left languages flip the whole document direction.
  const root = document.documentElement;
  root.setAttribute("dir", RTL.has(lang) ? "rtl" : "ltr");
  root.setAttribute("lang", CATALOGS[lang] ? lang : "en");
}

export function t(key) {
  return catalog[key] ?? en[key] ?? key;
}
