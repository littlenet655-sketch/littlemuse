/** Pure password-reset input rules (mirrors backend: 6-digit code, 8+ password). */
export function validateResetInput(code: string, password: string, confirm: string): string | null {
  if (code.trim().length !== 6) return 'Enter the 6-digit code from your email.';
  if (password.length < 8) return 'New password must be at least 8 characters long.';
  if (password !== confirm) return 'The new passwords do not match.';
  return null;
}
