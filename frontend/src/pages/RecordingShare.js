import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api, { fileUrl } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Loader2, Sparkles, ArrowLeft, Lock } from "lucide-react";

export default function RecordingShare() {
  const { token } = useParams();
  const [rec, setRec] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/recordings/shared/${token}`)
      .then(({ data }) => setRec(data))
      .catch(() => setError("Ce lien est invalide ou l'enregistrement a été supprimé."))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <div className="App">
      <Navbar />
      <div className="max-w-4xl mx-auto px-5 py-10">
        <Link to="/admin" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6" data-testid="share-back-link">
          <ArrowLeft className="h-4 w-4" /> Retour à l'espace admin
        </Link>

        {loading ? (
          <div className="flex justify-center py-24"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>
        ) : error ? (
          <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground" data-testid="share-error">
            <Lock className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
            {error}
          </div>
        ) : (
          <div data-testid="share-recording">
            <div className="flex items-center gap-2 text-xs text-primary mb-2"><Lock className="h-3.5 w-3.5" /> Lien protégé — réservé aux administrateurs</div>
            <h1 className="font-display text-3xl font-semibold mb-1" data-testid="share-title">{rec.title}</h1>
            <p className="text-sm text-muted-foreground mb-6">{rec.candidate_name ? `${rec.candidate_name} • ` : ""}{new Date(rec.created_at).toLocaleString("fr-FR")}</p>
            <video src={fileUrl(rec.video_file_id)} controls className="w-full rounded-2xl bg-black mb-6" data-testid="share-video" />
            {rec.summary && (
              <div className="rounded-2xl bg-primary/5 border border-primary/20 p-4 mb-4">
                <p className="text-xs font-semibold text-primary mb-1 flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> Résumé IA</p>
                <p className="text-sm whitespace-pre-wrap" data-testid="share-summary">{rec.summary}</p>
              </div>
            )}
            {rec.transcript && (
              <details className="rounded-2xl bg-secondary/40 p-4">
                <summary className="text-xs font-semibold cursor-pointer">Transcription complète</summary>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap mt-2">{rec.transcript}</p>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
