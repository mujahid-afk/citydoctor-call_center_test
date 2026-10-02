const KEYS: Array<[string, string]> = [
  ["1", ""], ["2", "ABC"], ["3", "DEF"],
  ["4", "GHI"], ["5", "JKL"], ["6", "MNO"],
  ["7", "PQRS"], ["8", "TUV"], ["9", "WXYZ"],
  ["*", ""], ["0", "+"], ["#", ""],
];

export function DialPad({ onPress, disabled }: { onPress: (key: string) => void; disabled?: boolean }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {KEYS.map(([key, letters]) => (
        <button
          key={key}
          type="button"
          disabled={disabled}
          onClick={() => onPress(key)}
          className="flex h-12 flex-col items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-800 shadow-sm hover:bg-slate-50 active:bg-slate-100 disabled:opacity-50"
        >
          <span className="text-lg font-semibold leading-none">{key}</span>
          <span className="mt-0.5 h-3 text-[9px] font-medium tracking-widest text-slate-400">{letters}</span>
        </button>
      ))}
    </div>
  );
}
