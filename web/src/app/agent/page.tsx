import { redirect } from "next/navigation";

// Old address kept working after the dashboard was reorganised into five sections.
export default function Redirect() {
  redirect("/fix?tab=agent");
}
