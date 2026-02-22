/**
 * Test anime constants for E2E tests.
 * These match real entries in the dev Sonarr instance.
 * My Dress-Up Darling: sonarr series 1, 12 episodes (S01)
 * Akame ga Kill: sonarr series 2, 24 episodes (S01)
 */

export const ANIME = {
  dressDarling: {
    title: 'My Dress-Up Darling',
    titlePart: 'Dress-Up',
    season: 1,
    episodeCount: 12,
    firstEpisode: 'S01E01',
    lastEpisode: 'S01E12',
  },
  akameGaKill: {
    title: 'Akame ga Kill',
    titlePart: 'Akame',
    season: 1,
    episodeCount: 24,
    firstEpisode: 'S01E01',
    lastEpisode: 'S01E24',
  },
} as const;

export type AnimeName = keyof typeof ANIME;
