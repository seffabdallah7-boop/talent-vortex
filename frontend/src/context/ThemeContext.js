import { createContext, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const ThemeContext = createContext(null);

function apply(primary, fg) {
  document.documentElement.style.setProperty("--primary", primary);
  document.documentElement.style.setProperty("--primary-foreground", fg);
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState({ primary: "220 100% 33%", primary_foreground: "0 0% 100%", name: "Bleu Corporate" });

  useEffect(() => {
    api.get("/settings/theme").then(({ data }) => {
      setThemeState(data);
      apply(data.primary, data.primary_foreground);
    }).catch(() => {});
  }, []);

  const saveTheme = async (primary, primary_foreground, name) => {
    const { data } = await api.put("/settings/theme", { primary, primary_foreground, name });
    setThemeState(data);
    apply(data.primary, data.primary_foreground);
    return data;
  };

  const previewTheme = (primary, fg) => apply(primary, fg);

  return (
    <ThemeContext.Provider value={{ theme, saveTheme, previewTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);
