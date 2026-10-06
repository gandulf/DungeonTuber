// Collecting files for upload: plain files, picked folders and dropped folders (keeping their structure).

export interface UploadItem {
  file: File;
  /** Path relative to the target folder, e.g. `Album/Disc 1/song.mp3`. */
  path: string;
}

export const isMp3 = (name: string) => name.toLowerCase().endsWith('.mp3');

export function itemsFromFiles(files: Iterable<File>): UploadItem[] {
  return [...files].map((file) => ({ file, path: file.webkitRelativePath || file.name }));
}

function readEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
}

async function walk(entry: FileSystemEntry, prefix: string, out: UploadItem[]) {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
    out.push({ file, path: prefix + entry.name });
  } else if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    // readEntries returns the entries in batches until it yields an empty one
    for (let batch = await readEntries(reader); batch.length; batch = await readEntries(reader)) {
      for (const child of batch) await walk(child, `${prefix}${entry.name}/`, out);
    }
  }
}

/** Files of a drop event; dropped folders are traversed recursively. */
export async function itemsFromDrop(transfer: DataTransfer | null): Promise<UploadItem[]> {
  if (!transfer) return [];
  const entries = [...transfer.items].map((item) => item.webkitGetAsEntry?.()).filter((entry): entry is FileSystemEntry => !!entry);
  if (!entries.length) return itemsFromFiles(transfer.files);
  const out: UploadItem[] = [];
  for (const entry of entries) await walk(entry, '', out);
  return out;
}
