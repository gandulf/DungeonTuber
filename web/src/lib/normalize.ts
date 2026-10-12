// Normalizing the metadata of songs with the matches of AcoustID / MusicBrainz (see core/musiclookup.py).
import type { LookupCandidate, Normalized, Track } from './types';

/** Matches at or above this score are applied without asking (batch normalize). */
export const SURE_SCORE = 95;

/** The file name for a match: "Artist - Title", without characters a file name cannot have. */
export function fileNameFor(candidate: LookupCandidate): string {
  return (candidate.artist ? `${candidate.artist} - ${candidate.title}` : candidate.title).replace(/[\\/:*?"<>|]/g, '_').trim();
}

const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

/** The best match when it is sure: at least SURE_SCORE, and every other sure match names the same song (the same
 *  recording often is on several albums). Two different songs above the threshold are ambiguous: null. */
export function sureMatch(candidates: LookupCandidate[], threshold = SURE_SCORE): LookupCandidate | null {
  const sure = candidates.filter((candidate) => candidate.score >= threshold);
  if (!sure.length) return null;
  const best = sure.reduce((a, b) => (b.score > a.score ? b : a));
  return sure.every((other) => same(other.title, best.title) && same(other.artist, best.artist)) ? best : null;
}

export interface MetadataPatch {
  title?: string;
  artist?: string;
  album?: string;
  track?: number;
  name?: string;
  normalized?: Normalized;
}

/** The flag a song gets for the metadata of a match. */
export const normalizedFlag = (candidate: LookupCandidate): Normalized => ({ source: candidate.source, recording_id: candidate.recording_id });

/** What a match changes in a song, including the normalized flag (empty when the song is normalized with it already). */
export function metadataPatch(track: Track, candidate: LookupCandidate): MetadataPatch {
  const patch: MetadataPatch = {};
  if (track.normalized?.recording_id !== candidate.recording_id || track.normalized?.source !== candidate.source) patch.normalized = normalizedFlag(candidate);
  if (candidate.title && candidate.title !== track.title) patch.title = candidate.title;
  if (candidate.artist && candidate.artist !== track.artist) patch.artist = candidate.artist;
  if (candidate.album && candidate.album !== track.album) patch.album = candidate.album;
  if (candidate.track && candidate.track !== track.track) patch.track = candidate.track;
  const name = fileNameFor(candidate);
  if (name && name !== track.file.replace(/\.mp3$/i, '')) patch.name = name;
  return patch;
}
