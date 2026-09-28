export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
        <rect width="32" height="32" rx="7" fill="#FFF200" />
        <path
          d="M16 6c-4.4 0-8 3.4-8 7.7C8 19.5 16 26 16 26s8-6.5 8-12.3C24 9.4 20.4 6 16 6zm0 10.6a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"
          fill="#782B90"
        />
      </svg>
      {!compact && (
        <div className="leading-tight">
          <div className="text-sm font-bold tracking-tight text-white">Savo SiteScout</div>
          <div className="text-[11px] text-white/70">Chennai expansion</div>
        </div>
      )}
    </div>
  );
}
