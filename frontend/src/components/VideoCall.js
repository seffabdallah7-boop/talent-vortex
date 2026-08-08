import { X } from "lucide-react";

export default function VideoCall({ room, audioOnly, title, onClose }) {
  const src = `https://meet.jit.si/${encodeURIComponent(room)}#config.prejoinPageEnabled=false${audioOnly ? "&config.startAudioOnly=true" : ""}`;
  return (
    <div className="fixed inset-0 z-[70] bg-black/90 flex flex-col" data-testid="video-call-modal">
      <div className="flex items-center justify-between px-4 py-2 text-white">
        <span className="font-medium">{title || (audioOnly ? "Appel audio" : "Appel vidéo")}</span>
        <button onClick={onClose} data-testid="video-call-close" className="h-9 w-9 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center">
          <X className="h-5 w-5" />
        </button>
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
