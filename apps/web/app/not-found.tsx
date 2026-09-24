import StateScreen from "../components/StateScreen";
import { site } from "../lib/copy";

/** Any address with no route. Renders inside layout.tsx, so its CSS and fonts apply. */
export default function NotFound() {
  const copy = site.notFound;
  return <StateScreen pose="shrug" title={copy.title} body={copy.body} action={{ label: copy.action, href: "/" }} />;
}
