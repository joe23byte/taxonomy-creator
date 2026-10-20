import { useState } from "react";
import { FileJson, FileSpreadsheet, FileText } from "lucide-react";
import { Dialog, DialogContent } from "./ui/dialog";
import { Select } from "./ui/primitives";
import { cn } from "@/lib/utils";

const SHEETS = ["Taxonomy", "Interaction Assignments", "Review Queue", "Taxonomy Changes"];

export function ExportDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [sheet, setSheet] = useState("");
  const csvHref = sheet ? `/api/export/csv?sheet=${encodeURIComponent(sheet)}` : "/api/export/csv";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Export results" description="Exports reflect the current saved taxonomy and assignments, including manual corrections.">
        <div className="space-y-2">
          <Option href="/api/export/xlsx" icon={<FileSpreadsheet />} title="Excel workbook" recommended
            text="Four sheets: Taxonomy, Interaction Assignments (one row per intent), Review Queue, Taxonomy Changes." />
          <div className="rounded-xl border border-zinc-200 p-4">
            <div className="flex items-start gap-3">
              <Icon><FileText /></Icon>
              <div className="flex-1">
                <p className="text-sm font-medium text-zinc-900">CSV</p>
                <p className="text-xs text-zinc-500">A single sheet, or all sheets as a ZIP archive.</p>
                <div className="mt-2 flex gap-2">
                  <Select value={sheet} onChange={(e) => setSheet(e.target.value)} className="h-8 text-[13px]">
                    <option value="">All sheets (.zip)</option>
                    {SHEETS.map((s) => <option key={s} value={s}>{s}</option>)}
                  </Select>
                  <a href={csvHref} className="inline-flex h-8 items-center rounded-lg bg-zinc-900 px-3 text-[13px] font-medium text-white hover:bg-zinc-800">Download</a>
                </div>
              </div>
            </div>
          </div>
          <Option href="/api/export/json" icon={<FileJson />} title="JSON" text="Complete export including all taxonomy nodes (with retired/merged), assignments and history." />
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Icon({ children }: { children: React.ReactNode }) {
  return <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-zinc-100 text-zinc-600 [&_svg]:size-4">{children}</div>;
}

function Option({ href, icon, title, text, recommended }: { href: string; icon: React.ReactNode; title: string; text: string; recommended?: boolean }) {
  return (
    <a href={href} className={cn("flex items-start gap-3 rounded-xl border p-4 transition hover:bg-zinc-50", recommended ? "border-blue-200 bg-blue-50/30" : "border-zinc-200")}>
      <Icon>{icon}</Icon>
      <div>
        <p className="text-sm font-medium text-zinc-900">{title} {recommended && <span className="ml-1 text-xs font-normal text-blue-600">Recommended</span>}</p>
        <p className="text-xs text-zinc-500">{text}</p>
      </div>
    </a>
  );
}
