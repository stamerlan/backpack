/* i18next setup: initializes the catalog with the English and Russian
 * resources and re-exports the instance react-i18next binds to. English is
 * the fallback, so the app runs with no catalog at all; a missing key
 * renders its English source.
 *
 * set_locale is the single entry the backend pushes the active locale
 * through, mirroring set_theme_mode. It negotiates the tag down to a
 * supported language and switches the catalog, then re-broadcasts the push
 * as a "set_locale" window event so other locale-aware state (the units
 * context) can seed itself from the same call without contending for the
 * global.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import ru from "./locales/ru.json";

/* The languages we ship a catalog for; everything else falls back to en. */
export const supported_languages = ["en", "ru"] as const;

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

window.set_locale = (tag, units) => {
  void i18n.changeLanguage(tag);
  window.dispatchEvent(
    new CustomEvent<LocaleDetail>("set_locale", {
      detail: { tag, units },
    }),
  );
};

export default i18n;
