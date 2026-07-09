// Minimal i18n: English catalog is the source of truth (SPEC section 10).
// Adding a language = one JSON file + an entry here; t() falls back to
// English for missing keys, then to the key itself.
import en from "./i18n/en.json";
import it from "./i18n/it.json";

export const LANGUAGES = { en: "English", it: "Italiano" };
const CATALOGS = { en, it };

let catalog = en;

export function setLang(lang) {
  catalog = CATALOGS[lang] ?? en;
}

export function t(key) {
  return catalog[key] ?? en[key] ?? key;
}
