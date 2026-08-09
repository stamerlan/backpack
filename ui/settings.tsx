/* The settings dialog. The backend opens it through window.show_settings_
 * dialog with the current values and awaits the edited ones, or null when
 * the dialog is dismissed.
 *
 * Properties:
 *   - (none): Driven by the backend through ui-api.ts, not by a parent.
 *
 * State:
 *   - req: The open request, holding the values being edited, the promise
 *     to settle and the theme to restore if the dialog is dismissed. Null
 *     when no dialog is up.
 *   - open: Whether the dialog is showing. Separate from req, which
 *     outlives it by the length of the exit animation.
 */
import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  DialogTrigger,
  Dropdown,
  Input,
  Label,
  Option,
} from "@fluentui/react-components";
import api from "./api";
import { not_mounted } from "./ui-api";
import { icon } from "./icon";
import "./settings.css";

/* Values the dialog rounds back to Python. Every field maps to a key the
 * backend reads under the same name, so a new setting only needs a new row.
 */
export interface SettingsValues {
  /* A stored key never reaches the frontend, so the field cannot show it and
   * an empty one cannot mean "remove". Instead "" leaves the stored key
   * alone, a string replaces it and null removes it.
   */
  gemini_api_key: string | null;
  theme: string;
  clear_poi_cache: boolean;
}

interface Request {
  values: SettingsValues;
  /* Settles show_settings_dialog() with the edited values, or null when the
   * dialog is dismissed.
   */
  resolve: (value: SettingsValues | null) => void;
  /* Applying a theme as it is picked previews it, so a dismissed dialog has
   * to put back whatever was active when it opened.
   */
  initial_theme: string;
  /* Whether the credential store holds a key. Only then is there something
   * to replace or remove.
   */
  key_set: boolean;
  /* Size of the POI tile cache file in bytes, or 0 when empty. */
  poi_cache_bytes: number;
}

const THEME_OPTIONS = [
  { value: "system", label: "Follow system" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

/* Read a string field from the untyped settings, falling back to a default. */
function get_str(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function format_bytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024)
    return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function SettingsDialog() {
  const [req, set_req] = useState<Request | null>(null);
  const [open, set_open] = useState(false);

  useEffect(() => {
    window.show_settings_dialog = (settings) => new Promise((resolve) => {
      const theme = get_str(settings?.theme, "system");
      const poi_cache_bytes =
        typeof settings?.poi_cache_bytes === "number"
          ? settings.poi_cache_bytes : 0;
      set_req({
        values: { gemini_api_key: "", theme, clear_poi_cache: false },
        resolve,
        initial_theme: theme,
        key_set: settings?.gemini_api_key_set === true,
        poi_cache_bytes,
      });
      set_open(true);
    });
    return () => {
      window.show_settings_dialog = not_mounted("settings dialog");
    };
  }, []);

  if (req === null)
    return null;

  const { gemini_api_key, theme, clear_poi_cache } = req.values;
  const selected_theme =
    THEME_OPTIONS.find((o) => o.value === theme) ?? THEME_OPTIONS[0];
  /* The remove button doubles as its own undo, so the removal stays pending
   * until the dialog is saved and Cancel needs no special handling.
   */
  const removing = gemini_api_key === null;
  const key_action = removing
    ? "Keep the stored key" : "Remove the stored key";
  const key_hint = removing
    ? "Removed from the credential manager when you save."
    : "Used by the AI assistant. Stored in the operating system"
      + " credential manager.";

  const set_value = (patch: Partial<SettingsValues>): void =>
    set_req((cur) => cur && { ...cur, values: { ...cur.values, ...patch } });

  /* Resolving twice is a no-op on a promise, and putting the theme back is
   * idempotent, so the close paths need no guard against each other.
   */
  const close = (values: SettingsValues | null): void => {
    if (values === null)
      void api.set_theme(req.initial_theme);
    set_open(false);
    req.resolve(values);
    /* Let the exit animation finish before dropping the dialog. */
    setTimeout(() => set_req(null), 300);
  };

  return (
    <Dialog open={open} modalType="alert" onOpenChange={(_event, data) => {
      if (!data.open)
        close(null);
    }}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle
            action={
              <DialogTrigger action="close" disableButtonEnhancement>
                <Button
                  appearance="transparent"
                  aria-label="close"
                  icon={icon("close")}
                />
              </DialogTrigger>
            }
          >
            Settings
          </DialogTitle>
          <DialogContent>
            <div className="settings-form">
              <Card>
                <div className="settings-row">
                  <div className="settings-text">
                    <Label className="settings-label"
                      htmlFor="settings-gemini-api-key">Gemini API key</Label>
                    <span className="settings-hint">{key_hint}</span>
                  </div>
                  <div className="settings-control-group">
                    <Input
                      id="settings-gemini-api-key"
                      className="settings-control"
                      type="password"
                      autoComplete="off"
                      spellCheck={false}
                      disabled={removing}
                      placeholder={
                        req.key_set ? "Stored, type to replace" : "AIza..."}
                      value={gemini_api_key ?? ""}
                      onChange={(_event, data) =>
                        set_value({ gemini_api_key: data.value })}
                    />
                    {req.key_set && (
                      <Button
                        appearance="subtle"
                        aria-label={key_action}
                        title={key_action}
                        icon={icon(removing ? "close" : "trash")}
                        onClick={() =>
                          set_value({ gemini_api_key: removing ? "" : null })}
                      />
                    )}
                  </div>
                </div>
              </Card>

              <Card>
                <div className="settings-row">
                  <div className="settings-text">
                    <Label className="settings-label"
                      htmlFor="settings-theme">Theme</Label>
                    <span className="settings-hint">
                      Choose how Backpack looks.
                    </span>
                  </div>
                  <div className="settings-control-group">
                    <Dropdown
                      id="settings-theme"
                      className="settings-control"
                      inlinePopup
                      positioning={{ strategy: "fixed" }}
                      value={selected_theme.label}
                      selectedOptions={[selected_theme.value]}
                      onOptionSelect={(_event, data) => {
                        const mode = data.optionValue ?? "system";
                        set_value({ theme: mode });
                        /* Preview it, through the backend so the native title
                         * bar is themed too, not just the web content.
                         */
                        void api.set_theme(mode);
                      }}
                    >
                      {THEME_OPTIONS.map((option) => (
                        <Option key={option.value} value={option.value}>
                          {option.label}
                        </Option>
                      ))}
                    </Dropdown>
                  </div>
                </div>
              </Card>

              <Card>
                <div className="settings-row">
                  <div className="settings-text">
                    <Label className="settings-label">
                      Cached points of interest
                    </Label>
                    <span className="settings-hint">
                      {clear_poi_cache
                        ? "Will be cleared when you save."
                        : format_bytes(req.poi_cache_bytes)}
                    </span>
                  </div>
                  <div className="settings-control-group">
                    <Button
                      appearance="subtle"
                      disabled={req.poi_cache_bytes === 0}
                      icon={icon(clear_poi_cache ? "close" : "trash")}
                      onClick={() => set_value({
                        clear_poi_cache: !clear_poi_cache,
                      })}
                    >
                      {clear_poi_cache ? "Keep" : "Clear"}
                    </Button>
                  </div>
                </div>
              </Card>
            </div>
          </DialogContent>
          <DialogActions>
            <Button appearance="primary" onClick={() => close(req.values)}>
              Save
            </Button>
            <Button onClick={() => close(null)}>Cancel</Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}
