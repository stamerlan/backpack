/* The settings dialog. The backend opens it through window.show_settings_
 * dialog with the current values and awaits the edited ones, or null when
 * the dialog is dismissed.
 *
 * Properties:
 *   - (none): The backend drives the dialog through the global above.
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
import { icon } from "./icon";
import "./settings.css";

/* Values the dialog rounds back to Python. Every field maps to a key the
 * backend reads under the same name, so a new setting only needs a new row.
 */
export interface SettingsValues {
  gemini_api_key: string;
  theme: string;
}

/* Resolves the show_settings_dialog() promise with the edited values, or null
 * when the dialog is dismissed.
 */
type SendCpl = (value: SettingsValues | null) => void;

interface Request {
  values: SettingsValues;
  resolve: SendCpl;
  /* Applying a theme as it is picked previews it, so a dismissed dialog has
   * to put back whatever was active when it opened.
   */
  initial_theme: string;
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

let open_dialog:
  | ((settings: Record<string, unknown>, send_cpl: SendCpl) => void)
  | null = null;

export function SettingsDialog() {
  const [req, set_req] = useState<Request | null>(null);
  const [open, set_open] = useState(false);

  useEffect(() => {
    open_dialog = (settings, send_cpl) => {
      const theme = get_str(settings.theme, "system");
      set_req({
        values: {
          gemini_api_key: get_str(settings.gemini_api_key, ""),
          theme,
        },
        resolve: send_cpl,
        initial_theme: theme,
      });
      set_open(true);
    };
    return () => { open_dialog = null; };
  }, []);

  if (req === null)
    return null;

  const { gemini_api_key, theme } = req.values;
  const selected_theme =
    THEME_OPTIONS.find((o) => o.value === theme) ?? THEME_OPTIONS[0];

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
                    <span className="settings-hint">
                      Used by the AI assistant. Stored in the operating
                      system credential manager.
                    </span>
                  </div>
                  <Input
                    id="settings-gemini-api-key"
                    className="settings-control"
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="AIza..."
                    value={gemini_api_key}
                    onChange={(_event, data) =>
                      set_value({ gemini_api_key: data.value })}
                  />
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

function show_settings_dialog(
  settings: Record<string, unknown>
): Promise<SettingsValues | null> {
  const open = open_dialog;
  if (open === null)
    throw new Error("settings dialog is not mounted");
  return new Promise<SettingsValues | null>((resolve) => {
    open(settings ?? {}, resolve);
  });
}

declare global {
  interface Window {
    show_settings_dialog: typeof show_settings_dialog;
  }
}

window.show_settings_dialog = show_settings_dialog;
