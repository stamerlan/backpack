import {
  FluentProvider,
  Text,
  webLightTheme,
} from "@fluentui/react-components";
import { DialogHost } from "./dialog-host";

export function App() {
  return (
    <FluentProvider theme={webLightTheme}>
      <Text size={600} weight="bold" block>Hello, world</Text>
      <DialogHost />
    </FluentProvider>
  );
}
