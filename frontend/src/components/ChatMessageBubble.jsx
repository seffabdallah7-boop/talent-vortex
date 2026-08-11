import { useState } from "react";
import { fileUrl } from "@/lib/api";
import AudioPlayer from "@/components/AudioPlayer";
import { FileText, Pencil, Trash2, Check, X } from "lucide-react";

const fmtTime = (iso) => { try { return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };

export default function ChatMessageBubble({ m, mine, editable, onEdit, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(m.text || "");
  const att = m.attachment;
  const bubbleCls = mine ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-secondary text-secondary-foreground rounded-bl-sm";

  return (
    <div className={`group flex ${mine ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[80%]">
        <div className={`rounded-2xl px-3.5 py-2 text-sm ${bubbleCls}`} data-testid={`msg-${m.id}`}>
          {m.deleted ? (
            <span className="italic opacity-70">Message supprimé</span>
          ) : editing ? (
            <div className="flex items-center gap-1.5">
              <input
                value={val}
                onChange={(e) => setVal(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && val.trim()) { onEdit(m, val.trim()); setEditing(false); } }}
                className="rounded px-2 py-1 text-foreground bg-background text-sm w-44 border border-border"
                data-testid={`edit-input-${m.id}`}
                autoFocus
              />
              <button onClick={() => { if (val.trim()) { onEdit(m, val.trim()); setEditing(false); } }} data-testid={`edit-save-${m.id}`} title="Enregistrer"><Check className="h-4 w-4" /></button>
              <button onClick={() => { setEditing(false); setVal(m.text || ""); }} title="Annuler"><X className="h-4 w-4" /></button>
            </div>
          ) : (
            <>
              {att && att.kind === "image" && (
                <img src={fileUrl(att.file_id)} alt={att.filename} onClick={() => window.open(fileUrl(att.file_id), "_blank")} className="rounded-lg max-h-52 mb-1 cursor-pointer" data-testid={`att-img-${m.id}`} />
              )}
              {att && att.kind === "audio" && (
                <div className="mb-1 w-56"><AudioPlayer src={fileUrl(att.file_id)} label="Message vocal" testId={`att-audio-${m.id}`} /></div>
              )}
              {att && att.kind === "file" && (
                <a href={fileUrl(att.file_id)} target="_blank" rel="noreferrer" className="flex items-center gap-2 underline mb-1 break-all" data-testid={`att-file-${m.id}`}>
                  <FileText className="h-4 w-4 shrink-0" /> {att.filename}
                </a>
              )}
              {m.text && <span className="whitespace-pre-wrap">{m.text}</span>}
            </>
          )}
        </div>
        <div className={`mt-1 flex items-center gap-1.5 text-[10px] text-muted-foreground ${mine ? "justify-end" : "justify-start"}`}>
          <span>{fmtTime(m.created_at)}</span>
          {m.edited && !m.deleted && <span>· modifié</span>}
          {mine && m.read !== undefined && <span data-testid={`msg-read-status-${m.id}`}>{m.read ? "✓✓ Vu" : "✓ Envoyé"}</span>}
          {editable && mine && !m.deleted && (
            <span className="opacity-0 group-hover:opacity-100 flex items-center gap-1.5 transition-opacity">
              {!att && <button onClick={() => setEditing(true)} data-testid={`edit-btn-${m.id}`} title="Modifier"><Pencil className="h-3 w-3" /></button>}
              <button onClick={() => onDelete(m)} data-testid={`delete-btn-${m.id}`} title="Supprimer"><Trash2 className="h-3 w-3" /></button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
