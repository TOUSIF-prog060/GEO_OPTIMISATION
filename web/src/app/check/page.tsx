"use client";

import { BadgeCheck, GitCompareArrows, RefreshCcw, Scale } from "lucide-react";

import { Section } from "@/components/section";
import AccuracyView from "@/views/accuracy";
import RetestView from "@/views/retest";

export default function CheckPage() {
  return (
    <Section
      step={4}
      title="Check it worked"
      lede="After publishing changes, ask the same questions again and compare. And check how far the measurements themselves can be trusted."
      help={{
        id: "check",
        steps: [
          { icon: RefreshCcw, title: "Ask again", text: "The same questions go back to the same engines after your changes are live." },
          { icon: GitCompareArrows, title: "Compare before and after", text: "We show what changed for each brand, and whether the change is bigger than normal variation." },
          { icon: Scale, title: "Check our accuracy", text: "Automatic tests and people's labels show how reliable the numbers are." },
        ],
      }}
      tabs={[
        {
          id: "retest",
          label: "Before and after",
          description: "Re-ask questions and see whether visibility changed.",
          icon: RefreshCcw,
          content: <RetestView />,
        },
        {
          id: "accuracy",
          label: "Can we trust the numbers?",
          description: "How often the automatic reading agrees with people and tests.",
          icon: BadgeCheck,
          content: <AccuracyView />,
        },
      ]}
    />
  );
}
