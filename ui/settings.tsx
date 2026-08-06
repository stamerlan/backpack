import { useEffect, useRef, useState } from "react";
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
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { icon } from "./icon";

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

const THEME_OPTIONS = [
  { value: "system", label: "Follow system" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

/* Read a string field from the untyped settings, falling back to a default. */
function get_str(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

const use_styles = makeStyles({
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    minWidth: "min(520px, 80vw)",
    padding: "4px 0"
  },
  row: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "24px"
  },
  text: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
    minWidth: 0
  },
  label: {
    fontWeight: tokens.fontWeightSemibold
  },
  hint: {
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorNeutralForeground3
  },
  control: {
    flex: "0 0 auto",
    minWidth: "220px"
  }
});

let open_dialog:
  | ((settings: Record<string, unknown>, send_cpl: SendCpl) => void)
  | null = null;

export function SettingsDialog() {
  const styles = use_styles();
  const [cur_settings, set_cur_settings] =
    useState<Record<string, unknown> | null>(null);
  const [cpl_cb, set_cpl_cb] = useState<SendCpl | null>(null);
  const [open, set_open] = useState(false);
  const cur_theme = useRef("system");
  const done = useRef(true);

  useEffect(() => {
    open_dialog = (settings, send_cpl) => {
      cur_theme.current = get_str(settings.theme, "system");
      done.current = false;
      set_cur_settings(settings);
      set_cpl_cb(() => send_cpl);
      set_open(true);
    };
    return () => { open_dialog = null; };
  }, []);

  if (cur_settings === null)
    return null;

  /* cur_settings is the working copy: each control reads its value from it and
   * writes edits straight back under the same key.
   */
  const api_key = get_str(cur_settings.gemini_api_key, "");
  const theme = get_str(cur_settings.theme, "system");
  const selected_theme =
    THEME_OPTIONS.find((o) => o.value === theme) ?? THEME_OPTIONS[0];

  const set_setting = (key: string, value: string): void =>
    set_cur_settings((s) => s && { ...s, [key]: value });

  /* Live preview: applying the theme as it is picked matches the original
   * window. A dismissed dialog restores whatever was active on open.
   */
  const apply_theme = (mode: string): void => window.set_theme_mode?.(mode);

  const close = (new_settings: SettingsValues | null): void => {
    if (done.current)
      return;
    done.current = true;
    if (new_settings === null)
      apply_theme(cur_theme.current);
    set_open(false);
    cpl_cb?.(new_settings);
    /* Let the exit animation finish before dropping the dialog. */
    setTimeout(() => {
      set_cur_settings(null);
      set_cpl_cb(null);
    }, 300);
  };

  const save = (): void => close({ gemini_api_key: api_key, theme });

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
            <div className={styles.form}>
              <Card>
                <div className={styles.row}>
                  <div className={styles.text}>
                    <Label className={styles.label}
                      htmlFor="settings-gemini-api-key">Gemini API key</Label>
                    <span className={styles.hint}>
                      Used by the AI assistant. Stored in the operating
                      system credential manager.
                    </span>
                  </div>
                  <Input
                    id="settings-gemini-api-key"
                    className={styles.control}
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="AIza..."
                    value={api_key}
                    onChange={(_event, data) =>
                      set_setting("gemini_api_key", data.value)}
                  />
                </div>
              </Card>

              <Card>
                <div className={styles.row}>
                  <div className={styles.text}>
                    <Label className={styles.label}
                      htmlFor="settings-theme">Theme</Label>
                    <span className={styles.hint}>
                      Choose how Backpack looks.
                    </span>
                  </div>
                  <Dropdown
                    id="settings-theme"
                    className={styles.control}
                    inlinePopup
                    positioning={{ strategy: "fixed" }}
                    value={selected_theme.label}
                    selectedOptions={[selected_theme.value]}
                    onOptionSelect={(_event, data) => {
                      const mode = data.optionValue ?? "system";
                      set_setting("theme", mode);
                      apply_theme(mode);
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
            <Button appearance="primary" onClick={save}>Save</Button>
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
