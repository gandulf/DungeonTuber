import type { DownloadItem } from '../types';

export type JobKind = 'downloads' | 'analysis';

export interface DownloadStatus {
  pending: number;
  done: number;
  failed: number;
  items: DownloadItem[];
}

/** The YouTube imports of the server: the queue of the current run (finished items stay until the next run starts). */
export const downloads = $state<DownloadStatus>({ pending: 0, done: 0, failed: 0, items: [] });

/** Takes over a status of the server; returns true when a running import just finished. */
export function setDownloads(status: DownloadStatus): boolean {
  const finished = downloads.pending > 0 && status.pending === 0;
  Object.assign(downloads, status);
  return finished;
}

/** The analysis queue of the server (Voxalyzer), shaped like the downloads. */
export const analysis = $state<DownloadStatus>({ pending: 0, done: 0, failed: 0, items: [] });

export function setAnalysis(status: DownloadStatus): boolean {
  const finished = analysis.pending > 0 && status.pending === 0;
  Object.assign(analysis, status);
  return finished;
}

export const jobs = (kind: JobKind): DownloadStatus => (kind === 'downloads' ? downloads : analysis);
