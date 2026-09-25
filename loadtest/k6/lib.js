// Shared helpers for the ExperimentOS k6 scripts.
//
// Configuration (all via -e / environment):
//   BASE_URL         default http://localhost:8000
//   SEED_FILE        JSON written by loadtest/seed.py (path relative to THIS
//                    directory or absolute). Provides api_key + experiment_keys.
//   API_KEY          overrides seed file
//   EXPERIMENT_KEYS  comma-separated, overrides seed file
//   PROFILE          smoke | 100 | 500 | 1000 | 5000 | ramp   (default smoke)
//   DURATION         steady-state duration per fixed-rate profile (default 2m)
//   USER_POOL        number of distinct user ids to draw from (default 100000)
//   HOST_HEADER      optional Host header (e.g. testing a pod via port-forward)
//   SUMMARY_FILE     optional path for the JSON end-of-test summary

const DEFAULT_SEED = '../seed.json';

function loadSeed() {
  const path = __ENV.SEED_FILE || DEFAULT_SEED;
  try {
    return JSON.parse(open(path));
  } catch (e) {
    if (__ENV.SEED_FILE) {
      throw new Error(`Cannot read SEED_FILE=${path}: ${e}`);
    }
    return {};
  }
}

const seed = loadSeed();

export const BASE_URL = (__ENV.BASE_URL || seed.base_url || 'http://localhost:8000').replace(/\/$/, '');
export const API_KEY = __ENV.API_KEY || seed.api_key || '';
export const EXPERIMENT_KEYS = (__ENV.EXPERIMENT_KEYS ? __ENV.EXPERIMENT_KEYS.split(',') : seed.experiment_keys || [])
  .map((k) => k.trim())
  .filter(Boolean);
export const USER_POOL = parseInt(__ENV.USER_POOL || '100000', 10);

if (!API_KEY) {
  throw new Error('No API key: run loadtest/seed.py (SEED_FILE) or pass -e API_KEY=...');
}

export function headers() {
  const h = { 'Content-Type': 'application/json', 'X-API-Key': API_KEY };
  if (__ENV.HOST_HEADER) {
    h.Host = __ENV.HOST_HEADER;
  }
  return h;
}

export function randomUserId() {
  return `user-${Math.floor(Math.random() * USER_POOL)}`;
}

// Fixed-rate profiles matching the plan's benchmark ladder (section 45).
// preAllocatedVUs assumes ~50ms responses; maxVUs leaves headroom for when the
// system slows down. If k6 reports dropped_iterations, the target rate was
// NOT achieved - report that, don't hide it.
const RATES = { smoke: 5, 100: 100, 500: 500, 1000: 1000, 5000: 5000 };

export function scenarioFor(execName) {
  const profile = __ENV.PROFILE || 'smoke';
  const duration = __ENV.DURATION || (profile === 'smoke' ? '15s' : '2m');

  if (profile === 'ramp') {
    return {
      [execName]: {
        executor: 'ramping-arrival-rate',
        startRate: 50,
        timeUnit: '1s',
        preAllocatedVUs: 200,
        maxVUs: 3000,
        stages: [
          { target: 100, duration: '30s' },
          { target: 100, duration: '1m' },
          { target: 500, duration: '30s' },
          { target: 500, duration: '1m' },
          { target: 1000, duration: '30s' },
          { target: 1000, duration: '1m' },
          { target: 5000, duration: '1m' },
          { target: 5000, duration: '1m' },
          { target: 0, duration: '15s' },
        ],
      },
    };
  }

  const rate = RATES[profile];
  if (!rate) {
    throw new Error(`Unknown PROFILE=${profile}; use one of ${Object.keys(RATES).join(', ')}, ramp`);
  }
  return {
    [execName]: {
      executor: 'constant-arrival-rate',
      rate,
      timeUnit: '1s',
      duration,
      preAllocatedVUs: Math.max(5, Math.ceil(rate * 0.05)),
      maxVUs: Math.max(20, rate),
    },
  };
}

export function summaryOutputs(data, textSummary) {
  const out = { stdout: textSummary(data, { indent: ' ', enableColors: true }) };
  if (__ENV.SUMMARY_FILE) {
    out[__ENV.SUMMARY_FILE] = JSON.stringify(data, null, 2);
  }
  return out;
}
