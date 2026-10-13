/** Attributes for fields of API keys, tokens and secrets, so password managers leave them alone.
 *
 *  Browsers ignore autocomplete="off" on password fields, and a text field followed by a password field (key and secret) looks like
 *  a login form to them: they fill in a saved user name and password. "new-password" is never filled with a saved login; the data-*
 *  attributes opt out of 1Password, LastPass, Bitwarden and Dashlane, which do not always follow autocomplete. */
const IGNORED = { 'data-1p-ignore': '', 'data-lpignore': 'true', 'data-bwignore': '', 'data-form-type': 'other' } as const;

/** For a secret shown as dots (type="password"): an API key, a token, a secret key. */
export const secretField = { autocomplete: 'new-password', ...IGNORED } as const;

/** For a visible key or ID next to a secret (e.g. the key of a Modal token), so it is not taken for a user name. */
export const keyField = { autocomplete: 'off', ...IGNORED } as const;
