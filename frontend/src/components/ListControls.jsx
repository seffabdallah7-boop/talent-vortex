import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Trash2, X, CheckSquare } from "lucide-react";

// Standard admin list header: "Sélectionner" toggle (top-left) + Pager (top-right).
export function ListToolbar({ lc, onBulkDelete, testId = "list", showPager = true }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2">
        <Button variant={lc.selectMode ? "default" : "outline"} size="sm" className="rounded-full" onClick={lc.toggleSelectMode} data-testid={`${testId}-toggle-select`}>
          <CheckSquare className="h-4 w-4 mr-2" /> {lc.selectMode ? "Annuler" : "Sélectionner"}
        </Button>
        {lc.selectMode && <BulkBar count={lc.selectedCount} onDelete={onBulkDelete} onClear={lc.clear} testId={`${testId}-bulk`} />}
      </div>
      {showPager && <Pager page={lc.page} totalPages={lc.totalPages} total={lc.total} onPage={lc.setPage} testId={`${testId}-pager-top`} />}
    </div>
  );
}

export function Pager({ page, totalPages, total, onPage, testId = "pager" }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-between gap-3 pt-4" data-testid={testId}>
      <span className="text-xs text-muted-foreground">{total} élément{total > 1 ? "s" : ""} • page {page}/{totalPages}</span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="icon" className="rounded-full h-8 w-8" disabled={page <= 1} onClick={() => onPage(page - 1)} data-testid={`${testId}-prev`}><ChevronLeft className="h-4 w-4" /></Button>
        <span className="text-sm font-medium tabular-nums">{page} / {totalPages}</span>
        <Button variant="outline" size="icon" className="rounded-full h-8 w-8" disabled={page >= totalPages} onClick={() => onPage(page + 1)} data-testid={`${testId}-next`}><ChevronRight className="h-4 w-4" /></Button>
      </div>
    </div>
  );
}

export function BulkBar({ count, onDelete, onClear, testId = "bulk" }) {
  if (count === 0) return null;
  return (
    <div className="flex items-center gap-2 rounded-full border border-primary/30 bg-primary/5 px-3 py-1.5" data-testid={`${testId}-bar`}>
      <span className="text-sm font-semibold text-primary">{count} sélectionné{count > 1 ? "s" : ""}</span>
      <Button size="sm" variant="outline" className="rounded-full h-7 text-destructive border-destructive/40 hover:bg-destructive/10" onClick={onDelete} data-testid={`${testId}-delete`}><Trash2 className="h-3.5 w-3.5 mr-1" /> Supprimer</Button>
      <button onClick={onClear} data-testid={`${testId}-clear`} className="h-7 w-7 rounded-full border border-border flex items-center justify-center text-muted-foreground hover:bg-secondary transition-colors"><X className="h-3.5 w-3.5" /></button>
    </div>
  );
}
