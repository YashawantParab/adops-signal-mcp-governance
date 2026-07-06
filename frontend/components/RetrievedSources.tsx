import { BookOpen } from "lucide-react";

import type { PlaybookSource } from "@/types";

function backendLabel(source: PlaybookSource): string {
  const backend = source.search_backend === "pgvector_cosine_distance" ? "pgvector cosine similarity" : "in-memory cosine (fallback)";
  return `${backend} · ${source.embedding_provider} embeddings`;
}

export function RetrievedSources({ sources }: { sources: PlaybookSource[] }) {
  if (!sources.length) {
    return (
      <section className="panel rounded-md p-5">
        <div className="flex items-center gap-2">
          <BookOpen className="text-slate-400" size={16} aria-hidden="true" />
          <h3 className="text-base font-semibold">Playbook Evidence (RAG)</h3>
        </div>
        <p className="mt-2 text-sm text-slate-500">No AdOps playbook section matched this question closely enough to cite.</p>
      </section>
    );
  }

  return (
    <section className="panel rounded-md p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <BookOpen className="text-slate-400" size={16} aria-hidden="true" />
          <h3 className="text-base font-semibold">Playbook Evidence (RAG)</h3>
        </div>
        <span className="rounded-md border border-line bg-slate-50 px-2 py-1 text-xs font-medium text-slate-600">
          {backendLabel(sources[0])}
        </span>
      </div>
      <p className="mt-1 text-sm text-slate-500">
        Retrieved from <code className="text-xs">data/adops_docs</code> by vector similarity and passed to the diagnosis as guidance, not campaign-specific proof.
      </p>
      <div className="mt-4 space-y-3">
        {sources.map((source, index) => (
          <div key={`${source.source}-${index}`} className="rounded-md border border-line p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold">{source.title}</p>
              <span className="text-xs font-medium text-accent">similarity {source.score.toFixed(2)}</span>
            </div>
            <p className="mt-1 text-xs uppercase tracking-wide text-slate-400">{source.source}</p>
            <p className="mt-2 text-sm leading-5 text-slate-700">{source.snippet}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
