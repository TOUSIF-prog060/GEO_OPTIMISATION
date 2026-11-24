// Plain-language definitions shown by the "?" buttons. Each has a one-line meaning and a
// concrete example, so nobody needs analytics vocabulary to read the dashboard.

export type Term = { title: string; meaning: string; example?: string };

export const GLOSSARY: Record<string, Term> = {
  mention_rate: {
    title: "How often AI names the brand",
    meaning: "Out of all the answers we collected, the share that mention the brand at least once.",
    example: "41% means the brand appeared in 41 of every 100 answers.",
  },
  share_of_voice: {
    title: "Share of brand mentions",
    meaning: "When an answer names any of the tracked brands, how the mentions split between them.",
    example: "29% means Sephora got 29 of every 100 brand mentions; the rest went to Nykaa and Tira.",
  },
  round: {
    title: "A round of questions",
    meaning: "One batch of questions sent to one AI engine at one time. Each round is saved so results can be compared later.",
    example: "30 questions asked to Gemini on 24 Nov is one round.",
  },
  engine: {
    title: "AI engine",
    meaning: "An AI assistant people ask for advice: ChatGPT, Gemini, Perplexity, Claude or Google AI Mode.",
  },
  gap: {
    title: "A gap",
    meaning: "A place where a competitor is visible in AI answers and the brand is not, or is shown less well.",
    example: "“Sephora is named in 10% of sunscreen answers, Nykaa in 60%.”",
  },
  priority: {
    title: "Priority score",
    meaning: "How much a gap is worth fixing first: bigger gaps backed by more answers score higher, harder fixes score lower.",
  },
  list_position: {
    title: "Position in the list",
    meaning: "When an AI answer gives a numbered list, where the brand appears. 1 is the top.",
  },
  citation_share: {
    title: "Sources from the brand's website",
    meaning: "The share of links an AI answer cites that point to the brand's own website.",
  },
  confidence: {
    title: "Confidence",
    meaning: "How sure we can be the result is real and not chance. More answers means more confidence.",
  },
  interval: {
    title: "Likely range",
    meaning: "The true value probably lies inside this range. A wide range means we need more answers to be sure.",
  },
  odds: {
    title: "Odds compared with the usual case",
    meaning: "How much more (above 1×) or less (below 1×) likely an answer is to name the brand than for the most common setting.",
    example: "10× for shortlist questions means far more likely than for budget questions.",
  },
  pr_auc: {
    title: "Model score",
    meaning: "How well a model picks out the answers that name the brand, on questions it never saw. Higher is better; guessing scores about the brand's overall rate.",
  },
  retest: {
    title: "Re-test",
    meaning: "Asking the same questions again after publishing new content, to see whether AI answers changed.",
  },
  accuracy: {
    title: "Measurement accuracy",
    meaning: "How often our automatic reading of answers agrees with what a person sees. High agreement means the numbers can be trusted.",
  },
  draft: {
    title: "Draft",
    meaning: "Website content written by the assistant from your approved facts, waiting for a person to approve it.",
  },
  agent: {
    title: "The agent",
    meaning: "Runs the whole cycle for you: asks the questions, measures, finds gaps and drafts fixes, then stops for your approval.",
  },
};
