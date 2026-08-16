import { useEffect, useState } from "react";
import { ChevronsUpDown, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import api from "@/lib/api";

let _cache = null;
const flag = (code) =>
  (code || "").toUpperCase().replace(/./g, (c) => String.fromCodePoint(127397 + c.charCodeAt(0)));

export function WhatsappIcon({ className = "h-4 w-4" }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z" />
    </svg>
  );
}

export function WhatsappInput({ value, onChange, testId }) {
  const [open, setOpen] = useState(false);
  const [countries, setCountries] = useState(_cache || []);
  const [dial, setDial] = useState("+33");
  const [num, setNum] = useState("");

  useEffect(() => {
    if (_cache) { setCountries(_cache); return; }
    api.get("/countries").then(({ data }) => { _cache = data; setCountries(data); }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!value || countries.length === 0) return;
    const digits = value.replace(/[^\d+]/g, "");
    const dials = countries.map((c) => c.dial).filter(Boolean).sort((a, b) => b.length - a.length);
    const match = dials.find((d) => digits.startsWith(d));
    if (match) { setDial(match); setNum(digits.slice(match.length)); }
    else { setNum(digits.replace(/^\+/, "")); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countries]);

  const emit = (d, n) => {
    const clean = (n || "").replace(/\D/g, "");
    onChange(clean ? `${d}${clean}` : "");
  };

  const selected = countries.find((c) => c.dial === dial);

  return (
    <div className="mt-1.5 flex gap-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" role="combobox" className="w-32 justify-between font-normal shrink-0" data-testid={testId ? `${testId}-dial` : undefined}>
            <span className="flex items-center gap-1.5 truncate">
              {selected && <span className="text-base leading-none">{flag(selected.code)}</span>} {dial}
            </span>
            <ChevronsUpDown className="h-4 w-4 opacity-50 shrink-0" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="start">
          <Command>
            <CommandInput placeholder="Rechercher un pays…" />
            <CommandList>
              <CommandEmpty>Aucun résultat.</CommandEmpty>
              <CommandGroup>
                {countries.filter((c) => c.dial).map((c) => (
                  <CommandItem
                    key={c.code} value={`${c.name} ${c.dial}`}
                    onSelect={() => { setDial(c.dial); setOpen(false); emit(c.dial, num); }}
                    className="cursor-pointer"
                    data-testid={testId ? `${testId}-dial-opt-${c.code}` : undefined}
                  >
                    <span className="mr-2 text-base leading-none">{flag(c.code)}</span>
                    <span className="truncate flex-1">{c.name}</span>
                    <span className="text-muted-foreground ml-2">{c.dial}</span>
                    <Check className={cn("ml-2 h-4 w-4", dial === c.dial ? "opacity-100" : "opacity-0")} />
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      <Input
        type="tel" inputMode="tel" value={num} placeholder="6 12 34 56 78"
        onChange={(e) => { setNum(e.target.value); emit(dial, e.target.value); }}
        data-testid={testId} className="flex-1"
      />
    </div>
  );
}
