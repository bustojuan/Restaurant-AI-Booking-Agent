export const openingHeadline =
  "Your restaurants. Your order.\nAI makes the calls.";

export type StoryNote = {
  title: string;
  detail?: string;
  results?: {
    restaurant: string;
    explanation: string;
    color: string;
  }[];
};

/** Explain what the viewer is seeing without requiring technical vocabulary. */
export const storyNotes: Record<string, StoryNote> = {
  selection: {
    title: "Choose the order we contact restaurants",
    detail: "Drag your shortlist into your preferred order.",
  },
  configuration: {
    title: "Tell us what works for you",
    detail: "4 guests · 21:00 · up to 30 minutes earlier or later.",
  },
  outcome: {
    title: "Three choices. One confirmed table.",
    results: [
      {
        restaurant: "First restaurant",
        explanation: "No tables available for this request.",
        color: "#e5bc81",
      },
      {
        restaurant: "Second restaurant",
        explanation: "22:30 offered; your latest allowed time is 21:30.",
        color: "#e7a6ad",
      },
      {
        restaurant: "Third restaurant",
        explanation: "Confirmed for 4 guests at 21:00.",
        color: "#8ed8bb",
      },
    ],
  },
  history: {
    title: "See every contact behind your booking",
    detail: "One request, three restaurant contacts, one decision trail.",
  },
  "history-filtered": {
    title: "Compare the three restaurant responses",
    detail: "No availability → unsuitable time → confirmed table.",
  },
  "graph-before": {
    title: "Prepare the request before making contact",
    detail:
      "Planning sets the brief. Research adds context. Supervisor routes the work.",
  },
  "graph-after": {
    title: "Check the result, then save what happened",
    detail: "Review the evidence, summarise the outcome and check consistency.",
  },
  "graph-return": {
    title: "Supervisor decides what happens next",
    detail: "The previous restaurant’s saved result returns to Supervisor.",
  },
  offer: {
    title: "Why the second offer was rejected",
    detail: "21:00 requested. 22:30 offered. Latest allowed: 21:30.",
  },
  policy: {
    title: "The offer is one hour beyond your limit",
    detail: "22:30 is 90 minutes after 21:00; only 30 minutes are allowed.",
  },
  tool: {
    title: "See how the backend handled the contact",
    detail: "Open the recorded operation and its saved result.",
  },
  replay: {
    title: "Replay the decisions, step by step",
    detail:
      "Inspect recorded operations and timing without placing another call.",
  },
  confirmation: {
    title: "The final result has supporting evidence",
    detail: "The saved confirmation matches the requested party size and time.",
  },
  analytics: {
    title: "Understand outcomes across bookings",
    detail:
      "Compare confirmation rates, contact results and recorded durations.",
  },
  playground: {
    title: "Try a scenario before making a call",
    detail: "Run a separate simulation and inspect its results.",
  },
  "playground-result": {
    title: "Check the scenario’s result",
    detail: "Review its checks, then open the execution trace.",
  },
};
