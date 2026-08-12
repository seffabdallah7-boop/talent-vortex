import { BACKEND_URL } from "@/lib/api";
import { X } from "lucide-react";

export function ImageLightbox({ src, alt = "", open, onClose }) {
  if (!open || !src) return null;
  const resolved = typeof src === "string" && src.startsWith("/") ? `${BACKEND_URL}${src}` : src;
  return (
    <div
      onClick={onClose}
      data-testid="image-lightbox"
      className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <button
        onClick={onClose}
        data-testid="lightbox-close"
        className="absolute top-4 right-4 h-10 w-10 rounded-full bg-white/10 text-white flex items-center justify-center hover:bg-white/20 transition-colors"
      >
        <X className="h-5 w-5" />
      </button>
      <img
        src={resolved}
        alt={alt}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[90vh] max-w-[90vw] rounded-xl object-contain shadow-2xl"
      />
    </div>
  );
}

export default ImageLightbox;
