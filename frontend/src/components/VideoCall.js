import { useState, useRef } from "react";
import { X, Link2, Check, Circle, Loader2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

export default function VideoCall({ room, audioOnly, title, onClose, recordCtx }) {
  const [copied, setCopied] = useState(false);
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);
  const videoRec = useRef(null);
  const audioRec = useRef(null);
  const vChunks = useRef([]);
  const aChunks = useRef([]);
  const streams = useRef([]);

  const inviteUrl = `https://meet.jit.si/${encodeURIComponent(room)}`;
  const src = `${inviteUrl}#config.prejoinPageEnabled=false&config.disableDeepLinking=true${audioOnly ? "&config.startAudioOnly=true" : ""}`;

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      window.prompt("Copiez le lien d'invitation :", inviteUrl);
    }
  };

  const startRecording = async () => {
    try {
      const display = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
      streams.current.push(display);
      let mic = null;
      try { mic = await navigator.mediaDevices.getUserMedia({ audio: true }); streams.current.push(mic); } catch { /* mic optional */ }

      const ac = new (window.AudioContext || window.webkitAudioContext)();
      const dest = ac.createMediaStreamDestination();
      if (display.getAudioTracks().length) ac.createMediaStreamSource(new MediaStream(display.getAudioTracks())).connect(dest);
      if (mic) ac.createMediaStreamSource(mic).connect(dest);
      const mixedAudio = dest.stream.getAudioTracks()[0];

      const videoStream = new MediaStream([display.getVideoTracks()[0], ...(mixedAudio ? [mixedAudio] : [])]);
      const audioStream = mixedAudio ? new MediaStream([mixedAudio]) : null;

      vChunks.current = []; aChunks.current = [];
      const vr = new MediaRecorder(videoStream, { mimeType: "video/webm" });
      vr.ondataavailable = (e) => { if (e.data.size) vChunks.current.push(e.data); };
      vr.onstop = () => finalize();
      videoRec.current = vr;
      if (audioStream) {
        const ar = new MediaRecorder(audioStream, { mimeType: "audio/webm" });
        ar.ondataavailable = (e) => { if (e.data.size) aChunks.current.push(e.data); };
        audioRec.current = ar;
        ar.start();
      }
      vr.start();
      display.getVideoTracks()[0].addEventListener("ended", () => { if (videoRec.current?.state === "recording") stopRecording(); });
      setRecording(true);
      toast.success("Enregistrement démarré");
    } catch (e) {
      toast.error("Impossible de démarrer l'enregistrement (partage d'écran refusé ?)");
    }
  };

  const stopRecording = () => {
    setRecording(false);
    try { audioRec.current?.state === "recording" && audioRec.current.stop(); } catch { /* noop */ }
    try { videoRec.current?.state === "recording" && videoRec.current.stop(); } catch { /* noop */ }
  };

  const finalize = async () => {
    streams.current.forEach((s) => s.getTracks().forEach((t) => t.stop()));
    streams.current = [];
    const videoBlob = new Blob(vChunks.current, { type: "video/webm" });
    const audioBlob = aChunks.current.length ? new Blob(aChunks.current, { type: "audio/webm" }) : null;
    if (!videoBlob.size) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("title", recordCtx?.title || title || "Entretien enregistré");
      if (recordCtx?.candidate_id) fd.append("candidate_id", recordCtx.candidate_id);
      if (recordCtx?.candidate_name) fd.append("candidate_name", recordCtx.candidate_name);
      if (recordCtx?.interview_id) fd.append("interview_id", recordCtx.interview_id);
      fd.append("video", videoBlob, "entretien.webm");
      if (audioBlob) fd.append("audio", audioBlob, "entretien-audio.webm");
      await api.post("/recordings", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Enregistrement sauvegardé — résumé IA en cours dans « Enregistrements ».");
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Échec de l'envoi de l'enregistrement");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black/90 flex flex-col" data-testid="video-call-modal">
      <div className="flex items-center justify-between px-4 py-2 text-white">
        <span className="font-medium flex items-center gap-2">
          {title || (audioOnly ? "Appel audio" : "Appel vidéo")}
          {recording && <span className="flex items-center gap-1 text-red-400 text-xs"><Circle className="h-2.5 w-2.5 fill-red-500 animate-pulse" /> REC</span>}
        </span>
        <div className="flex items-center gap-2">
          {recordCtx && (
            recording ? (
              <button onClick={stopRecording} data-testid="stop-recording-btn" className="h-9 px-3 rounded-full bg-red-500 hover:bg-red-600 flex items-center gap-2 text-sm transition-colors">
                <span className="h-2.5 w-2.5 rounded-sm bg-white" /> Arrêter
              </button>
            ) : (
              <button onClick={startRecording} disabled={uploading} data-testid="start-recording-btn" className="h-9 px-3 rounded-full bg-white/10 hover:bg-white/20 flex items-center gap-2 text-sm transition-colors">
                {uploading ? <><Loader2 className="h-4 w-4 animate-spin" /> Envoi…</> : <><Circle className="h-3.5 w-3.5 text-red-400 fill-red-500" /> Enregistrer</>}
              </button>
            )
          )}
          <button onClick={copyInvite} data-testid="copy-invite-link" className="h-9 px-3 rounded-full bg-white/10 hover:bg-white/20 flex items-center gap-2 text-sm transition-colors">
            {copied ? <><Check className="h-4 w-4 text-green-400" /> Lien copié</> : <><Link2 className="h-4 w-4" /> Inviter</>}
          </button>
          <button onClick={() => { if (recording) stopRecording(); onClose(); }} data-testid="video-call-close" className="h-9 w-9 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center">
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>
      <iframe
        title="appel"
        src={src}
        allow="camera; microphone; fullscreen; display-capture; autoplay; clipboard-write"
        className="flex-1 w-full border-0"
      />
    </div>
  );
}
