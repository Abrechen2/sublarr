export interface ParsedArgs {
  readonly positional: readonly string[];
  readonly values: Readonly<Record<string, string | undefined>>;
  readonly flags: Readonly<Record<string, boolean>>;
}

/**
 * Split CLI arguments into positional values, named value-flags and named
 * boolean-flags, so flag placement no longer matters: `--dry-run target msg`
 * and `target --dry-run msg` parse identically. `valueFlags` (e.g. `--file`)
 * consume the following argument as their value; `booleanFlags` (e.g.
 * `--dry-run`) consume none — both are removed from `positional`, and every
 * declared `booleanFlags` entry is reported in `flags` (true if present,
 * false if not), so callers read presence from this one parse instead of
 * re-scanning the raw argv themselves.
 */
export function parseArgs(
  argv: readonly string[],
  valueFlags: readonly string[],
  booleanFlags: readonly string[],
): ParsedArgs {
  const positional: string[] = [];
  const values: Record<string, string | undefined> = {};
  const flags: Record<string, boolean> = {};
  for (const flag of booleanFlags) {
    flags[flag] = false;
  }

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (valueFlags.includes(arg)) {
      values[arg] = argv[i + 1];
      i++;
    } else if (booleanFlags.includes(arg)) {
      flags[arg] = true;
    } else {
      positional.push(arg);
    }
  }

  return { positional, values, flags };
}
