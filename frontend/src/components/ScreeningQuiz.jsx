import { useState, useEffect } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Sparkles, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function ScreeningQuiz({ app, open, onClose, onDone }) {
  const questions = app?.screening?.questions || [];
  const [answers, setAnswers] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (open) { setAnswers(questions.map(() => "")); setDone(false); }
  }, [open, app?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    if (answers.some((a) => !a.trim())) { toast.error("Merci de répondre à toutes les questions."); return; }
    setSubmitting(true);
    try {
      await api.post(`/applications/${app.id}/screening`, { answers });
      setDone(true);
      onDone && onDone();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Envoi impossible");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="screening-quiz">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-primary" /> Examen de pré-qualification</DialogTitle>
        </DialogHeader>
        {done ? (
          <div className="py-10 text-center space-y-3" data-testid="screening-done">
            <CheckCircle2 className="h-12 w-12 text-primary mx-auto" />
            <p className="font-medium">Merci ! Vos réponses ont été transmises au recruteur.</p>
            <Button className="rounded-full" onClick={onClose}>Fermer</Button>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">Quelques questions rapides pour compléter votre candidature à <b>{app?.job_title}</b>.</p>
            {questions.map((q, i) => (
              <div key={`screening-q-${i}`} data-testid={`screening-q-${i}`}>
                <Label className="text-sm">{i + 1}. {q}</Label>
                <Textarea
                  rows={2}
                  className="mt-1.5"
                  data-testid={`screening-answer-${i}`}
                  value={answers[i] || ""}
                  onChange={(e) => setAnswers((prev) => prev.map((a, idx) => (idx === i ? e.target.value : a)))}
                />
              </div>
            ))}
            <Button className="rounded-full w-full h-11" onClick={submit} disabled={submitting} data-testid="screening-submit-btn">
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Envoyer mes réponses"}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
