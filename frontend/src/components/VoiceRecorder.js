import { useRef, useState, useEffect } from "react";
import { Mic, Square, Play, Pause, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const MAX_SECONDS = 600; // 10 minutes

function fmt(s) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export default function VoiceRecorder({ onChange }) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [blobUrl, setBlobUrl] = useState(null);
  const [playing, setPlaying] = useState(false);
  const mediaRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const audioRef = useRef(null);

  useEffect(() => () => clearInterval(timerRef.current), []);

  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => e.data.size > 0 && chunksRef.current.push(e.data);
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setBlobUrl(URL.createObjectURL(blob));
        onChange?.(blob);
        stream.getTracks().forEach((t) => t.stop());
      };
      mediaRef.current = mr;
      mr.start();
      setRecording(true);
      setSeconds(0);
      setBlobUrl(null);
      onChange?.(null);
      timerRef.current = setInterval(() => {
        setSeconds((s) => {
          if (s + 1 >= MAX_SECONDS) stop();
          return s + 1;
        });
      }, 1000);
    } catch (e) {
      alert("Micro inaccessible. Autorisez l'accès au microphone.");
    }
  };

  const stop = () => {
    clearInterval(timerRef.current);
    if (mediaRef.current && mediaRef.current.state !== "inactive") mediaRef.current.stop();
    setRecording(false);
  };

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (playing) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setPlaying(!playing);
  };

  const reset = () => {
    setBlobUrl(null);
    setSeconds(0);
    onChange?.(null);
  };

  return (
    <div className="rounded-xl border border-border bg-secondary/40 p-5" data-testid="voice-recorder">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`h-3 w-3 rounded-full ${recording ? "bg-red-500 rec-pulse" : "bg-muted-foreground/40"}`} />
          <span className="font-mono text-lg tabular-nums" data-testid="voice-timer">{fmt(seconds)}</span>
          <span className="text-xs text-muted-foreground">/ 10:00 max</span>
        </div>
        <div className="flex gap-2">
          {!recording && !blobUrl && (
            <Button type="button" onClick={start} data-testid="voice-start-btn" className="rounded-full">
              <Mic className="h-4 w-4 mr-2" /> Enregistrer
            </Button>
          )}
          {recording && (
            <Button type="button" variant="destructive" onClick={stop} data-testid="voice-stop-btn" className="rounded-full">
              <Square className="h-4 w-4 mr-2" /> Arrêter
            </Button>
          )}
          {blobUrl && !recording && (
            <>
              <Button type="button" variant="secondary" onClick={togglePlay} data-testid="voice-play-btn" className="rounded-full">
                {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              </Button>
              <Button type="button" variant="ghost" onClick={reset} data-testid="voice-reset-btn" className="rounded-full">
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </div>
      {blobUrl && (
        <audio ref={audioRef} src={blobUrl} onEnded={() => setPlaying(false)} className="w-full" controls data-testid="voice-audio" />
      )}
      {!blobUrl && !recording && (
        <p className="text-sm text-muted-foreground">
          Enregistrez un message vocal pour présenter votre motivation (jusqu'à 10 minutes).
        </p>
      )}
    </div>
  );
}
