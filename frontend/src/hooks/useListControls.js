import { useState, useMemo, useCallback, useEffect } from "react";

// Reusable pagination + multi-selection for admin lists.
// selectId: (item) => unique id. Default uses item.id.
export function useListControls(items, { pageSize = 15, selectId = (x) => x.id } = {}) {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(() => new Set());

  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const pageItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, page, pageSize]);

  const pageIds = useMemo(() => pageItems.map(selectId), [pageItems, selectId]);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));

  const toggle = useCallback((id) => {
    setSelected((prev) => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }, []);

  const toggleAllPage = useCallback(() => {
    setSelected((prev) => {
      const n = new Set(prev);
      const every = pageIds.length > 0 && pageIds.every((id) => n.has(id));
      if (every) pageIds.forEach((id) => n.delete(id));
      else pageIds.forEach((id) => n.add(id));
      return n;
    });
  }, [pageIds]);

  const clear = useCallback(() => setSelected(new Set()), []);

  return {
    page, setPage, totalPages, total, pageItems, pageSize,
    selected, selectedCount: selected.size, toggle, toggleAllPage, allPageSelected, clear,
    selectedIds: () => [...selected],
  };
}
