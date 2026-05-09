const FLAGS: Record<string, boolean> = {
  default_to_v2: true,
};

export function isFlagEnabled(flag: string): boolean {
  return FLAGS[flag] ?? false;
}
