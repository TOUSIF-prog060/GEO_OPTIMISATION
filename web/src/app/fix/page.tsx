"use client";

import { Bot, FilePenLine, Flag, ShieldCheck, Target, Wrench } from "lucide-react";

import { Section } from "@/components/section";
import AgentView from "@/views/agent";
import GapsView from "@/views/gaps";
import WriteView from "@/views/write";

export default function FixPage() {
  return (
    <Section
      step={3}
      title="Fix gaps"
      lede="Find where competitors are shown and Sephora is not, decide what to do, and get website content drafted from approved facts. Nothing is published without a person approving it."
      help={{
        id: "fix",
        steps: [
          { icon: Target, title: "Gaps are found", text: "Places where a competitor beats Sephora, ranked so the most worthwhile come first." },
          { icon: FilePenLine, title: "Fixes are drafted", text: "The assistant writes content using only facts from your knowledge base." },
          { icon: ShieldCheck, title: "You approve", text: "Every action and draft waits for your approval. You stay in control." },
        ],
      }}
      tabs={[
        {
          id: "gaps",
          label: "Gaps to fix",
          description: "Where Sephora loses to competitors, most important first.",
          icon: Flag,
          content: <GapsView />,
        },
        {
          id: "write",
          label: "Write content",
          description: "Drafts for product and help pages, built from approved facts.",
          icon: Wrench,
          content: <WriteView />,
        },
        {
          id: "agent",
          label: "Do it for me",
          description: "Runs every step automatically and stops for your approval.",
          icon: Bot,
          content: <AgentView />,
        },
      ]}
    />
  );
}
