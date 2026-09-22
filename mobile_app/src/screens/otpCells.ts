/**
 * Pure six-cell OTP input logic (no React Native imports — unit-tested).
 *
 * The cells are a fixed-length array of single digits. Typing a character in a
 * cell advances focus; backspacing an empty cell moves focus back; pasting or
 * OS-level OTP autofill (which lands as multi-character text in one cell)
 * distributes the digits forward across the remaining cells.
 */

export const OTP_LENGTH = 6;

/** Fresh empty cell state. */
export function emptyOtpCells(): string[] {
  return Array.from({ length: OTP_LENGTH }, () => '');
}

/**
 * Build cell state from a raw code (dev code, resend response): digits only,
 * capped at the cell count.
 */
export function cellsFromCode(code: string | undefined): string[] {
  const cells = emptyOtpCells();
  if (!code) return cells;
  const digits = code.replace(/\D/g, '').slice(0, OTP_LENGTH);
  for (let i = 0; i < digits.length; i += 1) {
    cells[i] = digits[i] ?? '';
  }
  return cells;
}

/**
 * Apply text typed, pasted, or autofilled into a cell. Multi-character input
 * distributes digits forward from that cell. Returns the new cells plus the
 * index the focus should move to.
 */
export function applyOtpInput(
  cells: string[],
  index: number,
  raw: string,
): { cells: string[]; focus: number } {
  const next = [...cells];
  const digits = raw.replace(/\D/g, '').slice(0, OTP_LENGTH - index);
  if (digits.length === 0) {
    // Cleared (e.g. selected char deleted): stay on this cell.
    next[index] = '';
    return { cells: next, focus: index };
  }
  for (let i = 0; i < digits.length; i += 1) {
    next[index + i] = digits[i] ?? '';
  }
  return { cells: next, focus: Math.min(index + digits.length, OTP_LENGTH - 1) };
}

/**
 * Backspace on an already-empty cell moves focus back and clears the previous
 * cell (the key event fires before onChangeText, so the caller handles this
 * case when the current cell is empty).
 */
export function applyOtpBackspace(
  cells: string[],
  index: number,
): { cells: string[]; focus: number } {
  const next = [...cells];
  if (index <= 0) return { cells: next, focus: 0 };
  next[index - 1] = '';
  return { cells: next, focus: index - 1 };
}

/** True when every cell holds a digit — the code is submittable. */
export function isOtpComplete(cells: string[]): boolean {
  return cells.length === OTP_LENGTH && cells.every((cell) => /^\d$/.test(cell));
}
