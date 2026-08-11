import { useState, useEffect, useCallback, useRef } from "react";
import api, { sendChatAttachment } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import VideoCall from "@/components/VideoCall";
import { Avatar } from "@/components/Avatar";
import ChatMessageBubble from "@/components/ChatMessageBubble";
import { Video, Phone, Loader2, Paperclip, Mic, Square, Send, Trash2, Search, Archive, X, ArrowLeft, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

const chatTime = (iso) => { try { return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };
const relSeen = (iso) => {
  if (!iso) return "jamais";
  try {
    const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "à l'instant";
    if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
    if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
    return `le ${new Date(iso).toLocaleDateString("fr-FR")}`;
  } catch { return ""; }
};

export default function Messages({ onOpenProfile, focus }) {
  const [convs, setConvs] = useState([]);
  const [active, setActive] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [firstUnread, setFirstUnread] = useState(null);
  const [text, setText] = useState("");
  const [call, setCall] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [recording, setRecording] = useState(false);
  const fileInputRef = useRef(null);
  const recRef = useRef(null);
  const chunksRef = useRef([]);
  const unreadRef = useRef(null);
  const [candidates, setCandidates] = useState([]);
  const [convFilter, setConvFilter] = useState("active");
  const [convSearch, setConvSearch] = useState("");
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [otherTyping, setOtherTyping] = useState(false);
  const typingRef = useRef(0);
  const pingTyping = () => { const n = Date.now(); if (active && n - typingRef.current > 2500) { typingRef.current = n; api.post("/chat/typing", { candidate_id: active.candidate_id }).catch(() => {}); } };

  useEffect(() => { if (focus?.candidate_id) setActive(focus); }, [focus]);
  useEffect(() => { api.get("/candidates").then(({ data }) => setCandidates(data)).catch(() => {}); }, []);

  const loadConvs = useCallback(() => api.get("/chat/conversations").then(({ data }) => setConvs(data)).catch(() => {}), []);
  useEffect(() => {
    loadConvs();
    const int = setInterval(loadConvs, 5000);
    return () => clearInterval(int);
  }, [loadConvs]);

  useEffect(() => {
    if (!active) return;
    const load = () => api.get(`/chat/messages?candidate_id=${active.candidate_id}`).then(({ data }) => {
      if (Array.isArray(data)) { setMsgs(data); }
      else { setMsgs(data.messages || []); setFirstUnread(data.first_unread || null); setOtherTyping(!!data.other_typing); }
    }).catch(() => {});
    load();
    const int = setInterval(load, 2000);
    return () => clearInterval(int);
  }, [active]);

  useEffect(() => {
    if (firstUnread && unreadRef.current) setTimeout(() => unreadRef.current?.scrollIntoView({ block: "center", behavior: "smooth" }), 100);
  }, [firstUnread, msgs]);

  const send = async () => {
    if (!text.trim() || !active) return;
    const { data } = await api.post("/chat/messages", { text: text.trim(), candidate_id: active.candidate_id });
    setMsgs((m) => [...m, data]);
    setText("");
  };

  const reload = () => active && api.get(`/chat/messages?candidate_id=${active.candidate_id}`).then(({ data }) => { setMsgs(Array.isArray(data) ? data : (data.messages || [])); setFirstUnread(Array.isArray(data) ? null : (data.first_unread || null)); }).catch(() => {});

  const onPickFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !active) return;
    setUploading(true);
    try { const { data } = await sendChatAttachment({ file, candidateId: active.candidate_id, text: "" }); setMsgs((m) => [...m, data]); }
    catch { toast.error("Échec de l'envoi du fichier"); }
    finally { setUploading(false); }
  };

  const startRec = async () => {
    if (!active) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setUploading(true);
        try { const { data } = await sendChatAttachment({ file: blob, filename: "vocal.webm", candidateId: active.candidate_id, text: "" }); setMsgs((m) => [...m, data]); }
        catch { toast.error("Échec de l'envoi du vocal"); }
        finally { setUploading(false); }
      };
      recRef.current = mr;
      mr.start();
      setRecording(true);
    } catch { toast.error("Micro inaccessible."); }
  };
  const stopRec = () => { if (recRef.current?.state !== "inactive") recRef.current.stop(); setRecording(false); };

  const editMsg = async (m, t) => { try { await api.put(`/chat/messages/${m.id}`, { text: t }); reload(); } catch { toast.error("Échec de la modification"); } };
  const deleteMsg = async (m) => { try { await api.delete(`/chat/messages/${m.id}`); reload(); } catch { toast.error("Échec de la suppression"); } };

  const toggleActive = async () => {
    if (!active) return;
    const na = !(convs.find((c) => c.candidate_id === active.candidate_id)?.active);
    try { await api.put(`/chat/conversations/${active.candidate_id}/active`, { active: na }); toast.success(na ? "Conversation activée — le candidat peut y accéder." : "Conversation désactivée."); loadConvs(); }
    catch { toast.error("Action impossible"); }
  };
  const startConv = async (candId) => {
    const c = candidates.find((x) => x.user_id === candId);
    if (!c) return;
    try { await api.put(`/chat/conversations/${candId}/active`, { active: true }); toast.success("Discussion activée"); loadConvs(); setActive({ candidate_id: candId, candidate_name: c.name, picture: c.picture }); }
    catch { toast.error("Impossible de démarrer la discussion"); }
  };
  const deleteConv = async (candId) => {
    if (!window.confirm("Supprimer définitivement cette conversation et tous ses messages ?")) return;
    try { await api.delete(`/chat/conversations/${candId}`); toast.success("Conversation supprimée"); if (active?.candidate_id === candId) setActive(null); loadConvs(); }
    catch { toast.error("Suppression impossible"); }
  };
  const toggleConvActive = async (candidateId, currentActive) => {
    try { await api.put(`/chat/conversations/${candidateId}/active`, { active: !currentActive }); toast.success(!currentActive ? "Conversation activée — le candidat peut y accéder." : "Conversation désactivée."); loadConvs(); }
    catch { toast.error("Échec de mise à jour"); }
  };

  // Sélection multiple
  const toggleSelect = (candId) => setSelected((prev) => { const n = new Set(prev); n.has(candId) ? n.delete(candId) : n.add(candId); return n; });
  const exitSelect = () => { setSelectMode(false); setSelected(new Set()); };
  const bulkDelete = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(`Supprimer définitivement ${selected.size} conversation(s) et leurs messages ?`)) return;
    const ids = [...selected];
    await Promise.all(ids.map((id) => api.delete(`/chat/conversations/${id}`).catch(() => {})));
    toast.success(`${ids.length} conversation(s) supprimée(s)`);
    if (active && selected.has(active.candidate_id)) setActive(null);
    exitSelect(); loadConvs();
  };
  const bulkArchive = async () => {
    if (selected.size === 0) return;
    const ids = [...selected];
    await Promise.all(ids.map((id) => api.put(`/chat/conversations/${id}/active`, { active: false }).catch(() => {})));
    toast.success(`${ids.length} conversation(s) archivée(s)`);
    exitSelect(); loadConvs();
  };

  const activeConv = active ? (convs.find((c) => c.candidate_id === active.candidate_id) || active) : null;

  const shownConvs = convs.filter((c) => {
    if (!(convFilter === "all" || (convFilter === "active" ? c.active : !c.active))) return false;
    const q = convSearch.trim().toLowerCase();
    if (!q) return true;
    return [c.candidate_name, c.last_text].some((v) => (v || "").toLowerCase().includes(q));
  });

  return (
    <div>
      {call && <VideoCall room={call.room} audioOnly={call.audioOnly} onClose={() => setCall(null)} />}
      <h1 className="font-display text-3xl font-semibold mb-6">Messages</h1>
      <div className="grid md:grid-cols-3 gap-4 h-[calc(100vh-8rem)] min-h-[70vh]">
        <div className={`rounded-2xl border border-border bg-card flex-col overflow-hidden ${active ? "hidden md:flex" : "flex"}`}>
          <div className="p-2 border-b border-border space-y-2 shrink-0">
            <Select value="" onValueChange={startConv}>
              <SelectTrigger className="w-full rounded-full" data-testid="new-conv-select"><SelectValue placeholder="+ Nouvelle discussion" /></SelectTrigger>
              <SelectContent>
                {candidates.map((c) => <SelectItem key={c.user_id} value={c.user_id}>{c.name} — {c.email}</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input value={convSearch} onChange={(e) => setConvSearch(e.target.value)} placeholder="Rechercher un candidat..." className="rounded-full pl-9 h-9" data-testid="conv-search-input" />
            </div>
            <div className="inline-flex rounded-full border border-border p-0.5 w-full">
              {[["all", "Toutes"], ["active", "Actives"], ["inactive", "Inactives"]].map(([k, lbl]) => (
                <button key={k} onClick={() => setConvFilter(k)} data-testid={`conv-filter-${k}`} className={`flex-1 rounded-full px-2 py-1 text-xs font-medium transition-colors ${convFilter === k ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>{lbl}</button>
              ))}
            </div>
            {!selectMode ? (
              <button onClick={() => setSelectMode(true)} data-testid="select-mode-toggle" className="w-full text-xs font-medium text-muted-foreground hover:text-foreground py-1 transition-colors">Sélectionner</button>
            ) : (
              <div className="flex items-center gap-1.5" data-testid="bulk-toolbar">
                <span className="text-xs font-semibold text-muted-foreground mr-auto pl-1">{selected.size} sél.</span>
                <Button size="sm" variant="outline" className="rounded-full h-7 px-2 text-xs" onClick={bulkArchive} disabled={selected.size === 0} data-testid="bulk-archive-btn"><Archive className="h-3.5 w-3.5 mr-1" /> Archiver</Button>
                <Button size="sm" variant="outline" className="rounded-full h-7 px-2 text-xs text-destructive border-destructive/40 hover:bg-destructive/10" onClick={bulkDelete} disabled={selected.size === 0} data-testid="bulk-delete-btn"><Trash2 className="h-3.5 w-3.5 mr-1" /> Supprimer</Button>
                <button onClick={exitSelect} data-testid="bulk-cancel-btn" className="h-7 w-7 rounded-full border border-border flex items-center justify-center text-muted-foreground hover:bg-secondary transition-colors"><X className="h-3.5 w-3.5" /></button>
              </div>
            )}
          </div>
          <div className="flex-1 overflow-y-auto">
            {shownConvs.length === 0 ? <p className="p-6 text-sm text-muted-foreground">Aucune conversation.</p> : shownConvs.map((c) => (
              <div key={c.candidate_id} className={`group relative border-b border-border hover:bg-secondary transition-colors ${active?.candidate_id === c.candidate_id ? "bg-secondary" : ""} ${selectMode && selected.has(c.candidate_id) ? "bg-primary/5" : ""}`}>
                <button onClick={() => selectMode ? toggleSelect(c.candidate_id) : setActive(c)} data-testid={`conv-${c.candidate_id}`} className="w-full text-left p-4">
                  <div className="flex items-center gap-3">
                    {selectMode && (
                      <input type="checkbox" readOnly checked={selected.has(c.candidate_id)} data-testid={`conv-check-${c.candidate_id}`} className="h-4 w-4 shrink-0 accent-[hsl(var(--primary))]" />
                    )}
                    <div className="relative shrink-0">
                      <Avatar name={c.candidate_name} src={c.picture} size={40} />
                      <span className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-card ${c.online ? "bg-green-500" : "bg-muted-foreground/40"}`} data-testid={`conv-presence-${c.candidate_id}`} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-sm truncate">{c.candidate_name || "Candidat"}</span>
                        <span className="text-[10px] text-muted-foreground shrink-0" data-testid={`conv-time-${c.candidate_id}`}>{c.last_at ? chatTime(c.last_at) : ""}</span>
                      </div>
                      <div className="flex items-center justify-between gap-2 mt-0.5">
                        <p className="text-xs text-muted-foreground truncate">{c.last_text || (c.last_at ? "Pièce jointe" : "Discussion activée")}</p>
                        <div className="flex items-center gap-1 shrink-0">
                          {!c.active && <span className="text-[9px] rounded-full bg-muted px-1.5 py-0.5 text-muted-foreground" data-testid={`conv-inactive-${c.candidate_id}`}>inactive</span>}
                          {c.unread > 0 && <span className="h-5 min-w-5 px-1 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center">{c.unread}</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                </button>
                {!selectMode && (
                  <div className="absolute bottom-2 right-2 flex items-center gap-1 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                    <button onClick={(e) => { e.stopPropagation(); toggleConvActive(c.candidate_id, c.active); }} data-testid={`conv-toggle-active-${c.candidate_id}`} title={c.active ? "Désactiver la conversation" : "Activer la conversation"} className={`h-7 w-7 rounded-full bg-card border flex items-center justify-center transition-colors ${c.active ? "border-green-500/50 text-green-600 hover:bg-green-500/10" : "border-border text-muted-foreground hover:text-primary hover:border-primary"}`}>
                      {c.active ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); deleteConv(c.candidate_id); }} data-testid={`conv-delete-${c.candidate_id}`} title="Supprimer la conversation" className="h-7 w-7 rounded-full bg-card border border-border flex items-center justify-center text-muted-foreground hover:text-destructive hover:border-destructive transition-colors">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
        <div className={`md:col-span-2 rounded-2xl border border-border bg-card flex-col overflow-hidden ${active ? "flex" : "hidden md:flex"}`}>
          {!active ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">Sélectionnez une conversation</div>
          ) : (
            <>
              <div className="md:hidden flex items-center gap-2.5 overflow-x-auto px-3 py-2 border-b border-border shrink-0" data-testid="mobile-conv-strip">
                <button onClick={() => setActive(null)} data-testid="mobile-back-btn" title="Retour" className="shrink-0 h-10 w-10 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors"><ArrowLeft className="h-4 w-4" /></button>
                {shownConvs.map((c) => (
                  <button key={c.candidate_id} onClick={() => setActive(c)} data-testid={`strip-conv-${c.candidate_id}`} className="shrink-0 relative" title={c.candidate_name}>
                    <span className={`block rounded-full ${active?.candidate_id === c.candidate_id ? "ring-2 ring-primary ring-offset-2 ring-offset-card" : ""}`}>
                      <Avatar name={c.candidate_name} src={c.picture} size={40} />
                    </span>
                    <span className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-card ${c.online ? "bg-green-500" : "bg-muted-foreground/40"}`} />
                  </button>
                ))}
              </div>
              <div className="p-4 border-b border-border flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2 min-w-0">
                <button className="flex items-center gap-3 hover:opacity-80 text-left min-w-0" onClick={() => onOpenProfile(active.candidate_id)} data-testid="chat-open-profile">
                  <Avatar name={active.candidate_name} src={activeConv?.picture} size={40} />
                  <div>
                    <div className="font-medium">{active.candidate_name || "Candidat"}</div>
                    <div className="text-xs text-muted-foreground flex items-center gap-1.5" data-testid="active-presence">
                      <span className={`h-2 w-2 rounded-full ${activeConv?.online ? "bg-green-500" : "bg-muted-foreground/40"}`} />
                      {activeConv?.online ? "En ligne" : `Hors ligne · vu ${relSeen(activeConv?.last_seen)}`}
                    </div>
                  </div>
                </button>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" className="rounded-full" onClick={() => setCall({ room: `recrutai-chat-${active.candidate_id}`, audioOnly: false })} data-testid="admin-video-call-btn"><Video className="h-4 w-4" /></Button>
                  <Button size="sm" variant="outline" className="rounded-full" onClick={() => setCall({ room: `recrutai-chat-${active.candidate_id}`, audioOnly: true })} data-testid="admin-audio-call-btn"><Phone className="h-4 w-4" /></Button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {msgs.map((m) => (
                  <div key={m.id}>
                    {firstUnread === m.id && (
                      <div ref={unreadRef} className="flex items-center gap-2 my-2" data-testid="admin-unread-divider">
                        <div className="flex-1 h-px bg-primary/40" />
                        <span className="text-[10px] font-semibold text-primary uppercase tracking-wide">Nouveaux messages</span>
                        <div className="flex-1 h-px bg-primary/40" />
                      </div>
                    )}
                    <ChatMessageBubble m={m} mine={m.sender_role === "admin"} editable onEdit={editMsg} onDelete={deleteMsg} />
                  </div>
                ))}
                {otherTyping && <p className="text-xs text-muted-foreground italic animate-pulse" data-testid="admin-typing-indicator">{active?.candidate_name || "Le candidat"} est en train d'écrire…</p>}
              </div>
              <div className="p-3 border-t border-border flex items-center gap-2 shrink-0">
                <input ref={fileInputRef} type="file" accept="image/*,application/pdf,.doc,.docx,.txt,.xls,.xlsx" onChange={onPickFile} className="hidden" data-testid="admin-chat-file-input" />
                <button onClick={() => fileInputRef.current?.click()} disabled={uploading} data-testid="admin-attach-btn" title="Joindre un fichier" className="h-10 w-10 shrink-0 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors">
                  {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
                </button>
                <button onClick={recording ? stopRec : startRec} data-testid="admin-voice-btn" title="Message vocal" className={`h-10 w-10 shrink-0 rounded-full border flex items-center justify-center transition-colors ${recording ? "bg-red-500 text-white border-red-500 animate-pulse" : "border-border hover:bg-secondary"}`}>
                  {recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                </button>
                <Input value={text} onChange={(e) => { setText(e.target.value); pingTyping(); }} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Répondre..." className="rounded-full" data-testid="admin-chat-input" />
                <Button size="icon" onClick={send} className="rounded-full shrink-0" data-testid="admin-chat-send"><Send className="h-4 w-4" /></Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
