import { useEffect, useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import api from "@/lib/api";

let _cache = null;

const flag = (code) =>
  (code || "").toUpperCase().replace(/./g, (c) => String.fromCodePoint(127397 + c.charCodeAt(0)));

export function CountrySelect({ mode = "country", value, onChange, testId, placeholder }) {
  const [open, setOpen] = useState(false);
  const [countries, setCountries] = useState(_cache || []);

  useEffect(() => {
    if (_cache) return;
    api.get("/countries").then(({ data }) => { _cache = data; setCountries(data); }).catch(() => {});
  }, []);

  const labelKey = mode === "nationality" ? "nationality" : "name";
  const selected = countries.find((c) => c[labelKey] === value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button" variant="outline" role="combobox" aria-expanded={open}
          className="mt-1.5 w-full justify-between font-normal capitalize" data-testid={testId}
        >
          {value ? (
            <span className="flex items-center gap-2 truncate">
              {selected && <span className="text-base leading-none">{flag(selected.code)}</span>}
              <span className="truncate">{value}</span>
            </span>
          ) : (
            <span className="text-muted-foreground normal-case">{placeholder || "Sélectionner…"}</span>
          )}
          <ChevronsUpDown className="h-4 w-4 opacity-50 shrink-0" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
        <Command>
          <CommandInput placeholder="Rechercher…" data-testid={testId ? `${testId}-search` : undefined} />
          <CommandList>
            <CommandEmpty>Aucun résultat.</CommandEmpty>
            <CommandGroup>
              {countries.map((c) => (
                <CommandItem
                  key={c.code} value={c[labelKey]}
                  onSelect={() => { onChange(c[labelKey]); setOpen(false); }}
                  className="capitalize cursor-pointer"
                  data-testid={testId ? `${testId}-opt-${c.code}` : undefined}
                >
                  <span className="mr-2 text-base leading-none">{flag(c.code)}</span>
                  <span className="truncate">{c[labelKey]}</span>
                  <Check className={cn("ml-auto h-4 w-4", value === c[labelKey] ? "opacity-100" : "opacity-0")} />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
