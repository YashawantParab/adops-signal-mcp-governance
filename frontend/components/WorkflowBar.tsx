"use client";

import Link from "next/link";
import { Check } from "lucide-react";

const steps = [
  { label: "Prioritize", detail: "Risk queue", href: "/dashboard" },
  { label: "Diagnose", detail: "Evidence review", href: "/agent" },
  { label: "Decide", detail: "Human approval", href: "/recommendations" },
  { label: "Verify", detail: "Audit and learn", href: "/audit-logs" }
];

export function WorkflowBar({ currentStep }: { currentStep: 1 | 2 | 3 | 4 }) {
  return (
    <nav aria-label="Incident resolution workflow" className="mb-6 border-y border-line bg-white">
      <ol className="grid grid-cols-2 md:grid-cols-4">
        {steps.map((step, index) => {
          const stepNumber = index + 1;
          const isCurrent = stepNumber === currentStep;
          const isComplete = stepNumber < currentStep;
          return (
            <li
              key={step.label}
              className={`border-line even:border-l md:border-l md:first:border-l-0 ${index >= 2 ? "border-t md:border-t-0" : ""}`}
            >
              <Link
                href={step.href}
                aria-current={isCurrent ? "step" : undefined}
                className={`focus-ring flex min-h-16 items-center gap-3 px-3 py-3 md:px-4 ${
                  isCurrent ? "bg-ink text-white" : "text-slate-600 hover:bg-slate-50 hover:text-ink"
                }`}
              >
                <span
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${
                    isCurrent
                      ? "border-white bg-white text-ink"
                      : isComplete
                        ? "border-emerald-600 bg-emerald-600 text-white"
                        : "border-slate-300 bg-white text-slate-500"
                  }`}
                >
                  {isComplete ? <Check size={14} aria-hidden="true" /> : stepNumber}
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">{step.label}</span>
                  <span className={`block text-xs ${isCurrent ? "text-slate-300" : "text-slate-500"}`}>{step.detail}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
