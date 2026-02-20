/**
 * Lighthouse CI configuration for Frontend performance testing
 * Run with: lhci autorun
 */

module.exports = {
  ci: {
    collect: {
      url: ['http://localhost:5765/'],
      numberOfRuns: 3,
      startServerCommand: 'npm run dev',
      startServerReadyPattern: 'Local:',
      startServerReadyTimeout: 30000,
    },
    assert: {
      assertions: {
        'categories:performance': ['error', { minScore: 0.8 }],
        'categories:accessibility': ['error', { minScore: 0.9 }],
        'categories:best-practices': ['error', { minScore: 0.8 }],
        'categories:seo': ['warn', { minScore: 0.7 }],
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
