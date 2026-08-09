import { useRef, useState } from "react";
import { Play, Pause, Volume2 } from "lucide-react";

const SPEEDS = [1, 1.25, 1.5, 2];

export const AudioPlayer = ({ src, label = "Message vocal", testId }) => {
  const ref = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [progress, setProgress] = useState(0);

  const toggle = () => {
    const a = ref.current;
    if (!a) return;
    if (a.paused) { a.play(); setPlaying(true); }
    else { a.pause(); setPlaying(false); }
  };

  const cycleSpeed = () => {
    const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
    setSpeed(next);
    if (ref.current) ref.current.playbackRate = next;
  };

  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-secondary/40 px-4 py-3" data-testid={testId}>
      <button onClick={toggle} data-testid={testId ? `${testId}-play` : undefined} className="h-9 w-9 shrink-0 rounded-full bg-primary text-primary-foreground flex items-center justify-center hover:opacity-90 transition-opacity">
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 ml-0.5" />}
      </button>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-1.5"><Volume2 className="h-3.5 w-3.5" /> {label}</div>
        <div className="h-1.5 w-full rounded-full bg-border overflow-hidden">
          <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
        </div>
      </div>
      <button onClick={cycleSpeed} data-testid={testId ? `${testId}-speed` : undefined} className="shrink-0 rounded-full border border-border px-2.5 py-1 text-xs font-mono font-semibold hover:bg-secondary transition-colors">
        {speed}x
      </button>
      <audio
        ref={ref}
        src={src}
        onEnded={() => { setPlaying(false); setProgress(0); }}
        onTimeUpdate={(e) => { const a = e.target; if (a.duration) setProgress((a.currentTime / a.duration) * 100); }}
        className="hidden"
      />
    </div>
  );
};

export default AudioPlayer;
