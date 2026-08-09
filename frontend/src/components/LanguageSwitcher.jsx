import { useTranslation } from "react-i18next";

export const LanguageSwitcher = () => {
  const { i18n } = useTranslation();
  const lang = (i18n.resolvedLanguage || i18n.language || "fr").slice(0, 2);
  return (
    <div className="inline-flex rounded-full border border-border overflow-hidden text-xs" data-testid="lang-switcher">
      {["fr", "en"].map((l) => (
        <button
          key={l}
          onClick={() => i18n.changeLanguage(l)}
          data-testid={`lang-${l}`}
          className={`px-2.5 py-1.5 font-semibold uppercase transition-colors ${lang === l ? "bg-primary text-primary-foreground" : "hover:bg-secondary"}`}
        >
          {l}
        </button>
      ))}
    </div>
  );
};

export default LanguageSwitcher;
