import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import captions from "../public/captions.en.json";
import type { Caption } from "@remotion/captions";

type SubtitleCue = Caption & {
  startFrame: number;
  endFrame: number;
  lines: string[];
};
const subtitleCues: SubtitleCue[] = captions.cues;

/** Narration subtitles, separate from the video's editorial product callouts. */
export function Subtitles() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const timeMs = (frame * 1000) / fps;
  const cue = subtitleCues.find(
    (item) => timeMs >= item.startMs && timeMs < item.endMs,
  );
  if (!cue) return null;
  return (
    <div
      data-subtitle="en"
      style={{
        position: "absolute",
        bottom: 28,
        left: 160,
        right: 160,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          padding: "12px 24px",
          borderRadius: 10,
          background: "rgba(4, 10, 20, 0.93)",
          color: "#ffffff",
          fontSize: 34,
          fontWeight: 500,
          lineHeight: 1.3,
          textAlign: "center",
          textShadow: "0 2px 4px #000",
          boxShadow: "0 3px 20px #0005",
        }}
      >
        {cue.lines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
    </div>
  );
}
