/**
 * Whether a change in the folder `path` (a file added, removed, renamed or moved there) can change the contents of `directory`:
 * the change is inside the directory, or in its parent, where the directory itself can be renamed, moved or deleted.
 */
export function affectsDirectory(path: string, directory: string | null | undefined): boolean {
  const dir = directory?.replace(/\/+$/, '');
  if (!dir) return false;
  return path === dir || path.startsWith(dir + '/') || path === dir.slice(0, dir.lastIndexOf('/'));
}
