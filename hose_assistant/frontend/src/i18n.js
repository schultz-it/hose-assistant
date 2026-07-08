// Minimal i18n: English catalog is the source of truth (SPEC section 10).
// Other languages ship as JSON files (Milestone 10); t() falls back to the key.
import en from "./i18n/en.json";

let catalog = en;

export function t(key) {
  return catalog[key] ?? en[key] ?? key;
}
