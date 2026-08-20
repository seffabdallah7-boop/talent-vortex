import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageCircle, X, Send, Bot, Headset, Loader2, Paperclip, Mic, Square, ArrowLeft, Trash2 } from "lucide-react";
import api, { sendChatAttachment } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ChatMessageBubble from "@/components/ChatMessageBubble";
import { toast } from "sonner";

const fmtTime = (iso) => { try { return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };
const relTime = (iso) => {
  try {
    const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "à l'instant";
    if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
    if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
    return `le ${new Date(iso).toLocaleDateString("fr-FR")}`;
  } catch { return ""; }
};

function anonId() {
  let id = localStorage.getItem("ai_session");
  if (!id) {
    id = "anon_" + Math.random().toString(36).slice(2, 12);
    localStorage.setItem("ai_session", id);
  }
  return id;
}

export default function ChatWidget() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("support");
  const [aiMsgs, setAiMsgs] = useState([]);
  const [supMsgs, setSupMsgs] = useState([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [adminPresence, setAdminPresence] = useState(null);
  const [chatMeta, setChatMeta] = useState({ active: false, unread: 0 });
  const [firstUnread, setFirstUnread] = useState(null);
  const [otherTyping, setOtherTyping] = useState(false);
  const typingRef = useRef(0);
  const pingTyping = () => { const n = Date.now(); if (n - typingRef.current > 2500) { typingRef.current = n; api.post("/chat/typing").catch(() => {}); } };
  const scrollRef = useRef(null);
  const unreadRef = useRef(null);
  const fileInputRef = useRef(null);
  const recRef = useRef(null);
  const chunksRef = useRef([]);
  const [uploading, setUploading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [voicePreview, setVoicePreview] = useState(null);
  const cancelRef = useRef(false);
  const sessionId = user?.user_id || anonId();

  const scrollDown = () => setTimeout(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight), 50);

  useEffect(() => {
    if (open && tab === "ai") {
      api.get(`/ai/history?session_id=${sessionId}`).then(({ data }) => { setAiMsgs(data); scrollDown(); }).catch(() => {});
    }
  }, [open, tab, sessionId]);

  const loadSupport = () => api.get("/chat/messages").then(({ data }) => { setSupMsgs(data.messages || []); setFirstUnread(data.first_unread || null); setOtherTyping(!!data.other_typing); }).catch(() => {});

  useEffect(() => {
    if (!open || tab !== "support" || !user) return;
    loadSupport();
    const int = setInterval(loadSupport, 2000);
    return () => clearInterval(int);
  }, [open, tab, user]);

  useEffect(() => {
    if (!user) return;
    const ping = () => api.post("/presence/ping").catch(() => {});
    ping();
    const t = setInterval(ping, 30000);
    return () => clearInterval(t);
  }, [user]);

  useEffect(() => {
    if (!open || tab !== "support" || !user) return;
    const load = () => api.get("/presence/admin").then(({ data }) => setAdminPresence(data)).catch(() => {});
    load();
    const int = setInterval(load, 15000);
    return () => clearInterval(int);
  }, [open, tab, user]);

  useEffect(() => {
    if (tab === "support" && firstUnread && unreadRef.current) {
      setTimeout(() => unreadRef.current?.scrollIntoView({ block: "center", behavior: "smooth" }), 80);
    } else {
      scrollDown();
    }
  }, [aiMsgs, supMsgs, firstUnread, tab]);

  useEffect(() => {
    if (!user || user.role !== "candidate") return;
    const load = () => api.get("/chat/unread").then(({ data }) => setChatMeta(data)).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [user, open, tab, supMsgs.length]);

  useEffect(() => {
    const h = () => { setOpen(true); setTab("support"); };
    window.addEventListener("open-support-chat", h);
    return () => window.removeEventListener("open-support-chat", h);
  }, []);

  useEffect(() => {
    if (!open) return;
    window.history.pushState({ chatOpen: true }, "");
    const onPop = () => setOpen(false);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [open]);

  const sendAi = async () => {
    if (!text.trim() || sending) return;
    const msg = text.trim();
    setText("");
    setAiMsgs((m) => [...m, { role: "user", text: msg }]);
    setSending(true);
    try {
      const { data } = await api.post("/ai/chat", { session_id: sessionId, message: msg });
      setAiMsgs((m) => [...m, { role: "assistant", text: data.reply }]);
    } catch (e) {
      setAiMsgs((m) => [...m, { role: "assistant", text: "Erreur, réessayez." }]);
    } finally {
      setSending(false);
    }
  };

  const sendSupport = async () => {
    if (!text.trim() || sending || chatLocked) return;
    const msg = text.trim();
    setText("");
    setSending(true);
    try {
      const { data } = await api.post("/chat/messages", { text: msg });
      setSupMsgs((m) => [...m, data]);
    } catch (e) {
      console.error("Échec de l'envoi du message", e);
      toast.error("Échec de l'envoi du message. Réessayez.");
      setText(msg);
    }
    setSending(false);
  };

  const onPickFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const { data } = await sendChatAttachment({ file, text: "" });
      setSupMsgs((m) => [...m, data]);
    } catch { toast.error("Échec de l'envoi du fichier"); }
    finally { setUploading(false); }
  };

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      cancelRef.current = false;
      mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        if (cancelRef.current) { chunksRef.current = []; return; }
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setVoicePreview({ url: URL.createObjectURL(blob), blob });
      };
      recRef.current = mr;
      mr.start();
      setRecording(true);
    } catch { toast.error("Micro inaccessible."); }
  };
  const stopRec = () => { if (recRef.current?.state !== "inactive") recRef.current.stop(); };
  const cancelRec = () => { cancelRef.current = true; stopRec(); };
  const discardVoice = () => { setVoicePreview((v) => { if (v?.url) URL.revokeObjectURL(v.url); return null; }); };
  const sendVoice = async () => {
    if (!voicePreview) return;
    setUploading(true);
    try {
      const { data } = await sendChatAttachment({ file: voicePreview.blob, filename: "message-vocal.webm", text: "" });
      setSupMsgs((m) => [...m, data]);
      discardVoice();
    } catch { toast.error("Échec de l'envoi du vocal"); }
    finally { setUploading(false); }
  };

  const editMsg = async (m, newText) => { try { await api.put(`/chat/messages/${m.id}`, { text: newText }); loadSupport(); } catch { toast.error("Échec de la modification"); } };
  const deleteMsg = async (m) => { try { await api.delete(`/chat/messages/${m.id}`); loadSupport(); } catch { toast.error("Échec de la suppression"); } };

  const onSend = () => (tab === "ai" ? sendAi() : sendSupport());
  const isCandidate = user && user.role === "candidate";
  const chatLocked = isCandidate && !chatMeta.active;

  return (
    <>
      <motion.button
        data-testid="chat-toggle-btn"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => { setOpen((o) => !o); setTab("support"); }}
        className={`fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full bg-primary text-primary-foreground shadow-xl items-center justify-center ${open ? "hidden" : "flex"}`}
      >
        {open ? <X className="h-6 w-6" /> : <MessageCircle className="h-6 w-6" />}
        {!open && isCandidate && chatMeta.unread > 0 && (
          <span data-testid="chat-unread-badge" className="absolute -top-1 -right-1 h-5 min-w-5 px-1 rounded-full bg-destructive text-white text-[10px] font-bold flex items-center justify-center">{chatMeta.unread}</span>
        )}
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.96 }}
            transition={{ duration: 0.2 }}
            className="fixed z-50 flex flex-col overflow-hidden glass shadow-2xl inset-0 w-full h-full rounded-none sm:inset-auto sm:left-auto sm:bottom-4 sm:right-6 sm:w-[92vw] sm:max-w-sm sm:h-[540px] sm:rounded-2xl"
            data-testid="chat-panel"
          >
            <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-border bg-primary text-primary-foreground">
              <div className="flex items-center gap-2 min-w-0">
                <button onClick={() => window.history.back()} className="sm:hidden opacity-90 hover:opacity-100 shrink-0" aria-label="Retour" data-testid="chat-back-btn"><ArrowLeft className="h-5 w-5" /></button>
                {tab === "ai" ? <Bot className="h-4 w-4" /> : <Headset className="h-4 w-4" />}
                <span className="text-sm font-semibold truncate" data-testid="chat-header-title">{tab === "ai" ? "Assistant IA" : "Messagerie recruteur"}</span>
              </div>
              <button onClick={() => window.history.back()} className="hidden sm:block opacity-80 hover:opacity-100" aria-label="Fermer" data-testid="chat-close-btn"><X className="h-4 w-4" /></button>
            </div>

            {tab === "support" && isCandidate && (
              <div className="px-4 py-2 border-b border-border flex items-center gap-2 text-xs bg-background/40" data-testid="admin-presence">
                <span className={`h-2 w-2 rounded-full ${adminPresence?.online ? "bg-green-500" : "bg-muted-foreground/40"}`} />
                <span className="text-muted-foreground">{adminPresence?.online ? "Administrateur en ligne" : adminPresence?.last_seen ? `Hors ligne · vu ${relTime(adminPresence.last_seen)}` : "Administrateur hors ligne"}</span>
              </div>
            )}

            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 bg-background/60">
              {tab === "ai" ? (
                <>
                  {aiMsgs.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center mt-8">
                      Bonjour ! Posez-moi vos questions sur les offres et le recrutement.
                    </p>
                  )}
                  {aiMsgs.map((m, i) => (
                    <Bubble key={`${i}-${m.role}`} mine={m.role === "user"} text={m.text} />
                  ))}
                  {sending && <div className="text-muted-foreground text-sm flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> ...</div>}
                </>
              ) : !user ? (
                <p className="text-sm text-muted-foreground text-center mt-8">Connectez-vous pour discuter avec l'administrateur.</p>
              ) : !isCandidate ? (
                <p className="text-sm text-muted-foreground text-center mt-8">Le support en direct est destiné aux candidats. Utilisez la messagerie de l'administration.</p>
              ) : (
                <>
                  {chatLocked && (
                    <div className="rounded-xl bg-secondary/60 border border-border p-4 text-center text-sm text-muted-foreground" data-testid="chat-locked-notice">
                      La messagerie sera disponible dès que le recruteur l'aura activée.
                    </div>
                  )}
                  {!chatLocked && supMsgs.length === 0 && <p className="text-sm text-muted-foreground text-center mt-8">Écrivez au recruteur, il vous répondra ici.</p>}
                  {supMsgs.map((m) => (
                    <div key={m.id}>
                      {firstUnread === m.id && (
                        <div ref={unreadRef} className="flex items-center gap-2 my-2" data-testid="unread-divider">
                          <div className="flex-1 h-px bg-primary/40" />
                          <span className="text-[10px] font-semibold text-primary uppercase tracking-wide">Nouveaux messages</span>
                          <div className="flex-1 h-px bg-primary/40" />
                        </div>
                      )}
                      <ChatMessageBubble m={m} mine={m.sender_role === "candidate"} editable onEdit={editMsg} onDelete={deleteMsg} />
                    </div>
                  ))}
                  {otherTyping && <p className="text-xs text-muted-foreground italic px-1 animate-pulse" data-testid="typing-indicator">Le recruteur est en train d'écrire…</p>}
                </>
              )}
            </div>

            {tab === "support" && isCandidate && (
              <div className="p-3 border-t border-border bg-background">
                {voicePreview ? (
                  <div className="flex items-center gap-2" data-testid="voice-preview">
                    <audio controls src={voicePreview.url} className="flex-1 h-10" data-testid="voice-preview-audio" />
                    <button onClick={discardVoice} disabled={uploading} data-testid="voice-delete-btn" title="Supprimer le vocal" className="h-9 w-9 shrink-0 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors"><Trash2 className="h-4 w-4 text-destructive" /></button>
                    <Button size="icon" onClick={sendVoice} disabled={uploading} data-testid="voice-send-btn" className="rounded-full shrink-0">{uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</Button>
                  </div>
                ) : recording ? (
                  <div className="flex items-center gap-2" data-testid="voice-recording">
                    <span className="flex-1 flex items-center gap-2 text-sm text-red-500 font-medium"><span className="h-2.5 w-2.5 rounded-full bg-red-500 animate-pulse" /> Enregistrement en cours…</span>
                    <button onClick={cancelRec} data-testid="voice-cancel-btn" title="Annuler" className="h-9 px-4 rounded-full border border-border text-sm hover:bg-secondary transition-colors">Annuler</button>
                    <Button size="icon" onClick={stopRec} data-testid="voice-stop-btn" className="rounded-full shrink-0 bg-red-500 hover:bg-red-600 text-white"><Square className="h-4 w-4" /></Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    {isCandidate && !chatLocked && (
                      <>
                        <input ref={fileInputRef} type="file" accept="image/*,application/pdf,.doc,.docx,.txt,.xls,.xlsx" onChange={onPickFile} className="hidden" data-testid="chat-file-input" />
                        <button onClick={() => fileInputRef.current?.click()} disabled={uploading} data-testid="chat-attach-btn" title="Joindre un fichier" className="h-9 w-9 shrink-0 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors">
                          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
                        </button>
                        <button onClick={startRec} data-testid="chat-voice-btn" title="Message vocal" className="h-9 w-9 shrink-0 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors">
                          <Mic className="h-4 w-4" />
                        </button>
                      </>
                    )}
                    <Input
                      data-testid="chat-input"
                      value={text}
                      onChange={(e) => { setText(e.target.value); if (!chatLocked) pingTyping(); }}
                      onKeyDown={(e) => e.key === "Enter" && onSend()}
                      placeholder={chatLocked ? "En attente de l'administrateur…" : "Votre message..."}
                      disabled={chatLocked}
                      className="rounded-full"
                    />
                    <Button size="icon" onClick={onSend} disabled={sending || chatLocked} data-testid="chat-send-btn" className="rounded-full shrink-0">
                      <Send className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function Bubble({ mine, text, time, read }) {
  const showMeta = time || (mine && read !== undefined);
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[80%]">
        <div className={`rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap ${mine ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-secondary text-secondary-foreground rounded-bl-sm"}`}>
          {text}
        </div>
        {showMeta && (
          <div className={`mt-1 flex items-center gap-1.5 text-[10px] text-muted-foreground ${mine ? "justify-end" : "justify-start"}`}>
            {time && <span>{fmtTime(time)}</span>}
            {mine && read !== undefined && <span data-testid="msg-read-status">{read ? "✓✓ Vu" : "✓ Envoyé"}</span>}
          </div>
        )}
      </div>
    </motion.div>
  );
}
