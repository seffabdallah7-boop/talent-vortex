import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageCircle, X, Send, Bot, Headset, Loader2, Video, Phone } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import VideoCall from "@/components/VideoCall";

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
  const [tab, setTab] = useState("ai");
  const [aiMsgs, setAiMsgs] = useState([]);
  const [supMsgs, setSupMsgs] = useState([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [call, setCall] = useState(null);
  const [adminPresence, setAdminPresence] = useState(null);
  const scrollRef = useRef(null);
  const sessionId = user?.user_id || anonId();

  const scrollDown = () => setTimeout(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight), 50);

  useEffect(() => {
    if (open && tab === "ai") {
      api.get(`/ai/history?session_id=${sessionId}`).then(({ data }) => { setAiMsgs(data); scrollDown(); }).catch(() => {});
    }
  }, [open, tab, sessionId]);

  useEffect(() => {
    if (!open || tab !== "support" || !user) return;
    const load = () => api.get("/chat/messages").then(({ data }) => setSupMsgs(data)).catch(() => {});
    load();
    const int = setInterval(load, 4000);
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

  useEffect(() => { scrollDown(); }, [aiMsgs, supMsgs]);

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
    if (!text.trim() || sending) return;
    const msg = text.trim();
    setText("");
    setSending(true);
    try {
      const { data } = await api.post("/chat/messages", { text: msg });
      setSupMsgs((m) => [...m, data]);
    } catch (e) {}
    setSending(false);
  };

  const onSend = () => (tab === "ai" ? sendAi() : sendSupport());
  const isCandidate = user && user.role === "candidate";

  return (
    <>
      {call && <VideoCall room={call.room} audioOnly={call.audioOnly} onClose={() => setCall(null)} />}
      <motion.button
        data-testid="chat-toggle-btn"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full bg-primary text-primary-foreground shadow-xl flex items-center justify-center"
      >
        {open ? <X className="h-6 w-6" /> : <MessageCircle className="h-6 w-6" />}
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.96 }}
            transition={{ duration: 0.2 }}
            className="fixed bottom-24 right-6 z-50 w-[92vw] max-w-sm h-[540px] rounded-2xl glass shadow-2xl flex flex-col overflow-hidden"
            data-testid="chat-panel"
          >
            <div className="flex border-b border-border">
              <button
                onClick={() => setTab("ai")}
                data-testid="chat-tab-ai"
                className={`flex-1 py-3 text-sm font-semibold flex items-center justify-center gap-2 transition-colors ${tab === "ai" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
              >
                <Bot className="h-4 w-4" /> Assistant IA
              </button>
              <button
                onClick={() => setTab("support")}
                data-testid="chat-tab-support"
                className={`flex-1 py-3 text-sm font-semibold flex items-center justify-center gap-2 transition-colors ${tab === "support" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
              >
                <Headset className="h-4 w-4" /> Support
              </button>
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
                    <Bubble key={i} mine={m.role === "user"} text={m.text} />
                  ))}
                  {sending && <div className="text-muted-foreground text-sm flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> ...</div>}
                </>
              ) : !user ? (
                <p className="text-sm text-muted-foreground text-center mt-8">Connectez-vous pour discuter avec l'administrateur.</p>
              ) : !isCandidate ? (
                <p className="text-sm text-muted-foreground text-center mt-8">Le support en direct est destiné aux candidats. Utilisez la messagerie de l'administration.</p>
              ) : (
                <>
                  {supMsgs.length === 0 && <p className="text-sm text-muted-foreground text-center mt-8">Écrivez à l'administrateur, il vous répondra ici.</p>}
                  {supMsgs.map((m) => (
                    <Bubble key={m.id} mine={m.sender_role === "candidate"} text={m.text} time={m.created_at} read={m.read} />
                  ))}
                </>
              )}
            </div>

            {tab === "support" && isCandidate && (
              <div className="px-3 pt-2 flex gap-2">
                <Button size="sm" variant="outline" className="rounded-full flex-1" onClick={() => setCall({ room: `recrutai-chat-${user.user_id}`, audioOnly: false })} data-testid="chat-video-call-btn"><Video className="h-4 w-4 mr-1" /> Vidéo</Button>
                <Button size="sm" variant="outline" className="rounded-full flex-1" onClick={() => setCall({ room: `recrutai-chat-${user.user_id}`, audioOnly: true })} data-testid="chat-audio-call-btn"><Phone className="h-4 w-4 mr-1" /> Audio</Button>
              </div>
            )}
            {(tab === "ai" || isCandidate) && (
              <div className="p-3 border-t border-border flex gap-2 bg-background">
                <Input
                  data-testid="chat-input"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && onSend()}
                  placeholder="Votre message..."
                  className="rounded-full"
                />
                <Button size="icon" onClick={onSend} disabled={sending} data-testid="chat-send-btn" className="rounded-full shrink-0">
                  <Send className="h-4 w-4" />
                </Button>
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
