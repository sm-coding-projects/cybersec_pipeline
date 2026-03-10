import { useState, type ReactNode } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";

export interface Column<T> {
  key: string;
  header: string;
  sortable?: boolean;
  className?: string;
  render: (item: T) => ReactNode;
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (item: T) => void;
  sortBy?: string;
  sortOrder?: "asc" | "desc";
  onSort?: (key: string, order: "asc" | "desc") => void;
  emptyMessage?: string;
  className?: string;
}

export default function Table<T>({
  columns,
  data,
  onRowClick,
  sortBy: controlledSortBy,
  sortOrder: controlledSortOrder,
  onSort,
  emptyMessage = "No data available",
  className = "",
}: TableProps<T>) {
  const [internalSortBy, setInternalSortBy] = useState<string>("");
  const [internalSortOrder, setInternalSortOrder] = useState<"asc" | "desc">("asc");

  const sortBy = controlledSortBy ?? internalSortBy;
  const sortOrder = controlledSortOrder ?? internalSortOrder;

  function handleSort(key: string) {
    const newOrder = sortBy === key && sortOrder === "asc" ? "desc" : "asc";
    if (onSort) {
      onSort(key, newOrder);
    } else {
      setInternalSortBy(key);
      setInternalSortOrder(newOrder);
    }
  }

  function getSortIcon(key: string) {
    if (sortBy !== key) {
      return <ChevronsUpDown className="h-3 w-3 text-text-muted" />;
    }
    return sortOrder === "asc" ? (
      <ChevronUp className="h-3 w-3 text-accent" />
    ) : (
      <ChevronDown className="h-3 w-3 text-accent" />
    );
  }

  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="w-full">
        <thead>
          <tr className="border-b border-border">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`text-left px-4 py-3 text-[10px] font-mono font-semibold text-text-muted uppercase tracking-wider ${
                  col.sortable ? "cursor-pointer select-none hover:text-text-secondary transition-colors" : ""
                } ${col.className || ""}`}
                onClick={() => col.sortable && handleSort(col.key)}
              >
                <div className="flex items-center gap-1.5">
                  {col.header}
                  {col.sortable && getSortIcon(col.key)}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-12 text-center text-text-muted text-sm font-mono"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((item, index) => (
              <tr
                key={index}
                className={`transition-colors ${
                  onRowClick
                    ? "cursor-pointer hover:bg-surface-elevated"
                    : ""
                }`}
                onClick={() => onRowClick?.(item)}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`px-4 py-3 text-sm ${col.className || ""}`}
                  >
                    {col.render(item)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export function Pagination({
  page,
  totalPages,
  onPageChange,
  className = "",
}: PaginationProps) {
  if (totalPages <= 1) return null;

  const pages: (number | "...")[] = [];

  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (page > 3) pages.push("...");
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) {
      pages.push(i);
    }
    if (page < totalPages - 2) pages.push("...");
    pages.push(totalPages);
  }

  return (
    <div className={`flex items-center justify-between pt-4 ${className}`}>
      <p className="text-xs font-mono text-text-muted">
        Page {page} of {totalPages}
      </p>
      <div className="flex items-center gap-1">
        <button
          className="px-2 py-1 text-xs font-mono rounded text-text-secondary hover:text-text-primary hover:bg-surface-elevated disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
        >
          Prev
        </button>
        {pages.map((p, i) =>
          p === "..." ? (
            <span key={`ellipsis-${i}`} className="px-2 py-1 text-xs font-mono text-text-muted">
              ...
            </span>
          ) : (
            <button
              key={p}
              className={`px-2.5 py-1 text-xs font-mono rounded transition-colors ${
                p === page
                  ? "bg-accent/20 text-accent"
                  : "text-text-secondary hover:text-text-primary hover:bg-surface-elevated"
              }`}
              onClick={() => onPageChange(p)}
            >
              {p}
            </button>
          )
        )}
        <button
          className="px-2 py-1 text-xs font-mono rounded text-text-secondary hover:text-text-primary hover:bg-surface-elevated disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
        >
          Next
        </button>
      </div>
    </div>
  );
}
