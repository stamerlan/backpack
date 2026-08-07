/* The app's slide-out menu: document actions, the recently opened trips and
 * the way into settings. While mounted it publishes window.menu so the
 * backend can refresh the recent list (see UI in src/backpack/ui.py).
 *
 * Properties:
 *   - open: Whether the drawer is showing.
 *   - show_menu: Opens or closes the drawer.
 *
 * State:
 *   - recent: Recently opened trips, newest first, pushed by the backend.
 */
import { useEffect, useState } from "react";
import {
  Button,
  Card,
  CardHeader,
  OverlayDrawer,
  DrawerHeader,
  DrawerHeaderTitle,
  DrawerBody,
  DrawerFooter,
  Text,
} from "@fluentui/react-components";
import api from "./api";
import { icon } from "./icon";
import "./menu.css";

export interface RecentItem {
  title: string;
  meta: string;
  filename: string;
}

export function Menu(props: {
  open: boolean;
  show_menu: (open: boolean) => void;
}) {
  const [recent, set_recent] = useState<RecentItem[]>([]);

  useEffect(() => {
    window.menu = { set_recent };
    return () => { window.menu = null; };
  }, []);

  const hide_menu = (): void => props.show_menu(false);

  return (
    <OverlayDrawer
      position="start"
      size="small"
      open={props.open}
      onOpenChange={(_event, data) => props.show_menu(data.open)}
    >
      <DrawerHeader>
        <DrawerHeaderTitle
          action={
            <Button
              appearance="subtle"
              title="Close menu"
              aria-label="Close menu"
              icon={icon("close")}
              onClick={hide_menu}
            />
          }
        >
          Backpack
        </DrawerHeaderTitle>
      </DrawerHeader>

      <DrawerBody>
        <div className="menu-actions">
          <Button
            className="menu-entry"
            appearance="subtle"
            icon={icon("doc-add")}
            onClick={() => { hide_menu(); api.new_doc(); }}
          >
            New trip
          </Button>
          <Button
            className="menu-entry"
            appearance="subtle"
            icon={icon("folder-open")}
            onClick={() => { hide_menu(); api.open_doc(); }}
          >
            Open trip...
          </Button>
          <Button
            className="menu-entry"
            appearance="subtle"
            icon={icon("save")}
            onClick={() => { hide_menu(); api.save_doc(); }}
          >
            Save
          </Button>
          <Button
            className="menu-entry"
            appearance="subtle"
            icon={icon("save-as")}
            onClick={() => { hide_menu(); api.save_doc(null, true); }}
          >
            Save as...
          </Button>
        </div>

        {recent.length > 0 && (
          <>
            <div className="menu-section">Recent</div>
            <div className="menu-recent">
              {recent.map((item) => (
                <Card
                  key={item.filename}
                  className="menu-recent-card"
                  appearance="subtle"
                  onClick={() => { hide_menu(); api.open_doc(item.filename); }}
                >
                  <CardHeader
                    header={
                      <Text weight="semibold" truncate wrap={false}>
                        {item.title.trim() || "Untitled trip"}
                      </Text>
                    }
                    description={
                      <span className="menu-recent-meta">{item.meta}</span>
                    }
                  />
                </Card>
              ))}
            </div>
          </>
        )}
      </DrawerBody>

      <DrawerFooter className="menu-footer">
        <Button
          className="menu-entry"
          appearance="subtle"
          icon={icon("settings")}
          onClick={() => { hide_menu(); api.open_settings(); }}
        >
          Settings...
        </Button>
      </DrawerFooter>
    </OverlayDrawer>
  );
}

declare global {
  interface Window {
    menu: { set_recent(items: RecentItem[]): void } | null;
  }
}

window.menu = null;
