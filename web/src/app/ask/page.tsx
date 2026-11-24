"use client";

import { MessagesSquare, Send, Sparkles } from "lucide-react";

import { Section } from "@/components/section";
import AskView from "@/views/ask";

export default function AskPage() {
  return (
    <Section
      step={1}
      title="Ask AI"
      lede="Send shopping questions to AI assistants, the way a customer would, and keep every answer. Everything else in the app is built on these answers."
      help={{
        id: "ask",
        steps: [
          { icon: MessagesSquare, title: "Pick questions", text: "Type your own question, or tick ready-made questions from the question list." },
          { icon: Send, title: "Ask the engines", text: "We send them to each AI engine that is switched on. This takes about a minute." },
          { icon: Sparkles, title: "Read the answers", text: "See which brands each answer named, with its sources. Results flow into step 2." },
        ],
      }}
    >
      <AskView />
    </Section>
  );
}
