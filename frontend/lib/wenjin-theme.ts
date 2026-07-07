export const WENJIN_THEMES = ["mineral", "graphite"] as const;

export type WenjinTheme = (typeof WENJIN_THEMES)[number];

export const DEFAULT_WENJIN_THEME: WenjinTheme = "mineral";
export const WENJIN_THEME_STORAGE_KEY = "wenjin-theme";

export function isWenjinTheme(value: unknown): value is WenjinTheme {
  return (
    typeof value === "string" &&
    (WENJIN_THEMES as readonly string[]).includes(value)
  );
}

const serializedDefaultTheme = JSON.stringify(DEFAULT_WENJIN_THEME);
const serializedStorageKey = JSON.stringify(WENJIN_THEME_STORAGE_KEY);
const serializedThemes = JSON.stringify(WENJIN_THEMES);

export const WENJIN_THEME_INIT_SCRIPT = `(function(){try{var theme=${serializedDefaultTheme};var raw=localStorage.getItem(${serializedStorageKey});var allowed=${serializedThemes};if(raw){var parsed=JSON.parse(raw);var candidate=parsed&&parsed.state&&parsed.state.theme;if(allowed.indexOf(candidate)!==-1){theme=candidate;}}document.documentElement.setAttribute("data-wjn-theme",theme);}catch(_){document.documentElement.setAttribute("data-wjn-theme",${serializedDefaultTheme});}})();`;
