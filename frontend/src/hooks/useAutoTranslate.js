import { useEffect } from "react";
import i18n from "@/i18n";
import { FR_EN } from "@/lib/uiDict";

const EN_FR = Object.fromEntries(Object.entries(FR_EN).map(([fr, en]) => [en, fr]));
const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "IFRAME", "TEXTAREA", "INPUT", "CODE", "PRE"]);
const ATTRS = ["placeholder", "aria-label", "title"];

const lang = () => (i18n.resolvedLanguage || i18n.language || "fr").slice(0, 2);

function translateNodeValue(value, map) {
  if (!value) return null;
  const key = value.trim();
  if (!key) return null;
  const val = map[key];
  if (val === undefined || val === key) return null;
  return value.replace(key, val);
}

function walk(root, map) {
  if (!root) return;
  if (root.nodeType === Node.TEXT_NODE) {
    const r = translateNodeValue(root.nodeValue, map);
    if (r !== null) root.nodeValue = r;
    return;
  }
  if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;

  const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const p = node.parentElement;
      if (!p || SKIP_TAGS.has(p.tagName) || p.isContentEditable) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes = [];
  let n;
  while ((n = tw.nextNode())) nodes.push(n);
  for (const node of nodes) {
    const r = translateNodeValue(node.nodeValue, map);
    if (r !== null) node.nodeValue = r;
  }

  if (root.querySelectorAll) {
    root.querySelectorAll("[placeholder],[aria-label],[title]").forEach((el) => {
      ATTRS.forEach((attr) => {
        const v = el.getAttribute(attr);
        if (v && map[v.trim()] && map[v.trim()] !== v.trim()) el.setAttribute(attr, map[v.trim()]);
      });
    });
  }
}

export default function useAutoTranslate() {
  useEffect(() => {
    let raf = 0;
    const runFull = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => walk(document.body, lang() === "en" ? FR_EN : EN_FR));
    };
    runFull();
    i18n.on("languageChanged", runFull);

    const mo = new MutationObserver((muts) => {
      if (lang() !== "en") return; // new nodes are already FR
      for (const m of muts) {
        m.addedNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE) {
            const r = translateNodeValue(node.nodeValue, FR_EN);
            if (r !== null) node.nodeValue = r;
          } else if (node.nodeType === Node.ELEMENT_NODE) {
            walk(node, FR_EN);
          }
        });
      }
    });
    mo.observe(document.body, { childList: true, subtree: true });

    return () => {
      i18n.off("languageChanged", runFull);
      mo.disconnect();
      cancelAnimationFrame(raf);
    };
  }, []);
}
