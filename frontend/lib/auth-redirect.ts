const DEFAULT_POST_AUTH_REDIRECT = '/workspaces';

export function resolvePostAuthRedirect(
  redirect: string | null | undefined
): string {
  if (!redirect || !redirect.startsWith('/') || redirect.startsWith('//')) {
    return DEFAULT_POST_AUTH_REDIRECT;
  }
  return redirect;
}
