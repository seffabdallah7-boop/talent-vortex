import { useState } from "react";
import { X, Link2, Check } from "lucide-react";

export default function VideoCall({ room, audioOnly, title, onClose }) {
  const [copied, setCopied] = useState(false);
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

  return (
    <div className="fixed inset-0 z-[70] bg-black/90 flex flex-col" data-testid="video-call-modal">
      <div className="flex items-center justify-between px-4 py-2 text-white">
        <span className="font-medium">{title || (audioOnly ? "Appel audio" : "Appel vidéo")}</span>
        <div className="flex items-center gap-2">
          <button
            onClick={copyInvite}
            data-testid="copy-invite-link"
            className="h-9 px-3 rounded-full bg-white/10 hover:bg-white/20 flex items-center gap-2 text-sm transition-colors"
          >
            {copied ? <><Check className="h-4 w-4 text-green-400" /> Lien copié</> : <><Link2 className="h-4 w-4" /> Inviter</>}
          </button>
          <button onClick={onClose} data-testid="video-call-close" className="h-9 w-9 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center">
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
