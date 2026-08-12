/* i18next setup and unit formatting. English is the fallback, so the app runs
 * with no catalog at all; a missing key renders its English source.
 *
 * set_locale is the single entry the backend pushes the active locale through,
 * mirroring set_theme_mode. It switches the catalog, then re-broadcasts the
 * push as a "set_locale" window event. This module listens for that event to
 * swap elev_str / dist_str; App listens too so the tree re-renders with the
 * new formatters. Units arrive already resolved ("metric" or "imperial").
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import ru from "./locales/ru.json";

/* The languages we ship a catalog for; everything else falls back to en. */
export const supported_languages = ["en", "ru"] as const;

/* The two systems every formatter measures in. */
export type UnitSystem = "metric" | "imperial";

/* Payload of the "set_locale" window event, mirroring the bridge arguments. */
export interface LocaleDetail {
  tag: string;
  units: string;
}

declare global {
  interface WindowEventMap {
    set_locale: CustomEvent<LocaleDetail>;
  }
}

/* Meters per unit for the length scales a route is drawn on. */
const M_PER_KM = 1000;
const M_PER_MI = 1609.344;
const FT_PER_M = 3.280839895;

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ru: { translation: ru },
  },
  lng: "en",
  fallbackLng: "en",
  supportedLngs: [...supported_languages],
  load: "languageOnly",
  nonExplicitSupportedLngs: true,
  interpolation: { escapeValue: false },
});

function make_elev(
  system: UnitSystem, tag: string,
): (meters: number, units?: boolean) => string {
  const imperial = system === "imperial";
  const key = imperial ? "units.ft" : "units.m";
  return (meters, units = true) => {
    const value = imperial ? meters * FT_PER_M : meters;
    const text = new Intl.NumberFormat(tag, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
    return units ? `${text} ${i18n.t(key)}` : text;
  };
}

function make_dist(
  system: UnitSystem, tag: string,
): (meters: number, units?: boolean) => string {
  const imperial = system === "imperial";
  const key = imperial ? "units.mi" : "units.km";
  return (meters, units = true) => {
    const value = meters / (imperial ? M_PER_MI : M_PER_KM);
    const text = new Intl.NumberFormat(tag, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value);
    return units ? `${text} ${i18n.t(key)}` : text;
  };
}

/* Elevation in meters as a localized number in m or ft. */
export let elev_str = make_elev("metric", "en");
/* Distance in meters as a localized number in km or mi. */
export let dist_str = make_dist("metric", "en");

window.addEventListener("set_locale", (event) => {
  const { tag, units } = event.detail;
  const system: UnitSystem =
    units === "imperial" ? "imperial" : "metric";
  elev_str = make_elev(system, tag);
  dist_str = make_dist(system, tag);
});

window.set_locale = (tag, units) => {
  void i18n.changeLanguage(tag).then(() => {
    window.dispatchEvent(
      new CustomEvent<LocaleDetail>("set_locale", { detail: { tag, units } })
    );
  });
};

export default i18n;
