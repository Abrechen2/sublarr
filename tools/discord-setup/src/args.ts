export interface ParsedArgs {
  readonly positional: readonly string[];
  readonly values: Readonly<Record<string, string | undefined>>;
}

/**
 * Split CLI arguments into positional values and named flags, so flag
 * placement no longer matters: `--dry-run target msg` and `target --dry-run
 * msg` parse identically. `valueFlags` (e.g. `--file`) consume the following
 * argument as their value; `booleanFlags` (e.g. `--dry-run`) consume none —
 * both are simply removed from `positional`.
 */
export function parseArgs(
  argv: readonly string[],
  valueFlags: readonly string[],
  booleanFlags: readonly string[],
): ParsedArgs {
  const positional: string[] = [];
  const values: Record<string, string | undefined> = {};

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (valueFlags.includes(arg)) {
      values[arg] = argv[i + 1];
      i++;
    } else if (!booleanFlags.includes(arg)) {
      positional.push(arg);
    }
  }

  return { positional, values };
}
