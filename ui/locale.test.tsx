/* The localization wiring itself: the set_locale bridge switches the catalog
 * so components re-render in the new language, keeps the document language in
 * step, falls back to English for anything we do not ship, and re-points the
 * unit formatters at the chosen system.
 */
import { afterEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { TripCard } from "./trip-card";
import {
  dist_str,
  elev_str,
  to_dist,
  to_elev,
  unit_system,
} from "./i18n";
import { render_ui, reset_locale, set_locale, t } from "./test-utils";

/* Every spec leaves the shared instance on the English, metric defaults so a
 * later switch cannot bleed into the next test.
 */
afterEach(async () => {
  await reset_locale();
});

describe("set_locale language", () => {
  it("re-renders the tree in the chosen language", async () => {
    render_ui(
      <TripCard id="trip-1" title="" notes="" on_change={() => {}} />,
    );
    expect(
      screen.getByPlaceholderText(t("common.untitled_trip")),
    ).toBeInTheDocument();
    await set_locale("ru", "metric");
    expect(
      await screen.findByPlaceholderText("Поход без названия"),
    ).toBeInTheDocument();
  });

  it("keeps the document language in step", async () => {
    await set_locale("ru", "metric");
    expect(document.documentElement.lang).toBe("ru");
    await set_locale("en", "metric");
    expect(document.documentElement.lang).toBe("en");
  });

  it("falls back to English for an unshipped language", async () => {
    await set_locale("fr", "metric");
    expect(t("common.untitled_trip")).toBe("Untitled trip");
  });
});

describe("set_locale units", () => {
  it("measures in kilometers and meters under metric", async () => {
    await set_locale("en", "metric");
    expect(unit_system).toBe("metric");
    expect(dist_str(1000)).toBe("1.00 km");
    expect(elev_str(100)).toBe("100 m");
    expect(to_dist(1000)).toBeCloseTo(1);
    expect(to_elev(100)).toBeCloseTo(100);
  });

  it("measures in miles and feet under imperial", async () => {
    await set_locale("en", "imperial");
    expect(unit_system).toBe("imperial");
    expect(dist_str(1609.344)).toBe("1.00 mi");
    expect(elev_str(0)).toBe("0 ft");
    expect(to_dist(1609.344)).toBeCloseTo(1);
    expect(to_elev(1)).toBeCloseTo(3.280839895);
  });

  it("translates unit labels alongside the numbers", async () => {
    await set_locale("ru", "metric");
    const one_km = new Intl.NumberFormat("ru", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(1);
    expect(dist_str(1000)).toBe(`${one_km} ${t("units.km")}`);
    expect(elev_str(100)).toBe(`100 ${t("units.m")}`);
  });
});
