import { useEffect, useRef } from "react";
import { Phone, PhoneOff, Video } from "lucide-react";

export default function IncomingCall({ call, onAccept, onDecline }) {
  const ringRef = useRef(null);

  useEffect(() => {
    // simple ring via Web Audio (repeating soft beep)
    let ctx, interval;
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      const beep = () => {
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.value = 660;
        g.gain.setValueAtTime(0.0001, ctx.currentTime);
        g.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.05);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.5);
        o.connect(g); g.connect(ctx.destination);
        o.start(); o.stop(ctx.currentTime + 0.55);
      };
      beep();
      interval = setInterval(beep, 1500);
      ringRef.current = { ctx, interval };
      if (navigator.vibrate) navigator.vibrate([300, 200, 300]);
    } catch (e) { console.debug("son de sonnerie indisponible", e); }
    return () => {
      if (interval) clearInterval(interval);
      try { ctx && ctx.close(); } catch (e) { console.debug("fermeture AudioContext", e); }
    };
  }, []);

  if (!call) return null;
  return (
    <div className="fixed inset-0 z-[80] bg-black/70 flex items-center justify-center p-4" data-testid="incoming-call-modal">
      <div className="w-full max-w-sm rounded-3xl bg-card border border-border p-8 text-center shadow-2xl">
        <div className="h-20 w-20 rounded-full bg-primary/15 text-primary flex items-center justify-center mx-auto mb-4 animate-pulse">
          {call.mode === "audio" ? <Phone className="h-9 w-9" /> : <Video className="h-9 w-9" />}
        </div>
        <p className="label-caps text-primary mb-1">Appel entrant</p>
        <h2 className="font-display text-2xl font-semibold mb-1">{call.caller_name || "Recruteur"}</h2>
        <p className="text-sm text-muted-foreground mb-8">vous appelle en {call.mode === "audio" ? "audio" : "vidéo"}…</p>
        <div className="flex items-center justify-center gap-6">
          <button onClick={onDecline} data-testid="decline-call-btn" className="h-14 w-14 rounded-full bg-destructive text-white flex items-center justify-center hover:scale-105 transition-transform">
            <PhoneOff className="h-6 w-6" />
          </button>
          <button onClick={onAccept} data-testid="accept-call-btn" className="h-14 w-14 rounded-full bg-green-500 text-white flex items-center justify-center hover:scale-105 transition-transform">
            <Phone className="h-6 w-6" />
          </button>
        </div>
      </div>
    </div>
  );
}
