"use client";

import { BarChart3, Lightbulb, ListChecks, Search, TrendingUp } from "lucide-react";

import { Section } from "@/components/section";
import DriversView from "@/views/drivers";
import VisibilityView from "@/views/visibility";

export default function ResultsPage() {
  return (
    <Section
      step={2}
      title="See results"
      lede="How often AI assistants name Sephora India compared with Nykaa and Tira, where it shows up and where it does not, and what makes the difference."
      help={{
        id: "results",
        steps: [
          { icon: Search, title: "Answers are read", text: "Each answer is checked for brand names, their place in any list, and the websites it cites." },
          { icon: BarChart3, title: "Numbers are counted", text: "We count how often each brand appears, overall and by product and engine." },
          { icon: Lightbulb, title: "Patterns are explained", text: "A model shows which kinds of questions and engines make Sephora appear." },
        ],
      }}
      tabs={[
        {
          id: "visibility",
          label: "Brand comparison",
          description: "How often each brand is named, per round of questions.",
          icon: ListChecks,
          content: <VisibilityView />,
        },
        {
          id: "drivers",
          label: "What drives visibility",
          description: "Which questions and engines make Sephora appear, from 700+ answers.",
          icon: TrendingUp,
          content: <DriversView />,
        },
      ]}
    />
  );
}
