// k6 load test for the SDK evaluation endpoint: POST /api/v1/evaluate/
//
//   python loadtest/seed.py --base-url http://localhost:8000 --out loadtest/seed.json
//   k6 run -e PROFILE=100  loadtest/k6/evaluate.js
//   k6 run -e PROFILE=ramp -e SUMMARY_FILE=loadtest/results/evaluate-ramp.json loadtest/k6/evaluate.js
//
// Thresholds encode the plan's *targets* (section 47): evaluation P95 < 50ms.
// A failed threshold is a result to report, not something to tune away.
import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.1.0/index.js';

import { BASE_URL, EXPERIMENT_KEYS, headers, randomUserId, scenarioFor, summaryOutputs } from './lib.js';

if (EXPERIMENT_KEYS.length === 0) {
  throw new Error('No experiment keys: use SEED_FILE or -e EXPERIMENT_KEYS=a,b');
}

// How many experiment keys per request (SDKs usually batch). Default: all seeded keys.
const KEYS_PER_REQUEST = parseInt(__ENV.KEYS_PER_REQUEST || `${EXPERIMENT_KEYS.length}`, 10);

const assignedRate = new Rate('evaluate_assigned');
const serverEvalTime = new Trend('evaluate_server_waiting', true);

export const options = {
  scenarios: scenarioFor('evaluate'),
  discardResponseBodies: false,
  thresholds: {
    // Plan target: assignment evaluation P95 < 50ms (measured client-side, so it
    // includes network + auth + serialization - stricter than server-side).
    'http_req_duration{name:evaluate}': ['p(95)<50', 'p(99)<150'],
    'http_req_failed{name:evaluate}': ['rate<0.01'],
    checks: ['rate>0.99'],
    // Every seeded experiment is RUNNING with 100% allocation, so every
    // evaluation should be assigned; a drop means degraded behaviour.
    evaluate_assigned: ['rate>0.99'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

function pickKeys() {
  if (KEYS_PER_REQUEST >= EXPERIMENT_KEYS.length) {
    return EXPERIMENT_KEYS;
  }
  const start = Math.floor(Math.random() * EXPERIMENT_KEYS.length);
  const keys = [];
  for (let i = 0; i < KEYS_PER_REQUEST; i++) {
    keys.push(EXPERIMENT_KEYS[(start + i) % EXPERIMENT_KEYS.length]);
  }
  return keys;
}

export default function () {
  const payload = JSON.stringify({
    user_id: randomUserId(),
    experiment_keys: pickKeys(),
    context: { country: 'US', platform: 'web', plan: Math.random() < 0.2 ? 'pro' : 'free' },
  });

  const res = http.post(`${BASE_URL}/api/v1/evaluate/`, payload, {
    headers: headers(),
    tags: { name: 'evaluate' },
  });
  serverEvalTime.add(res.timings.waiting);

  let evaluations = null;
  const ok = check(res, {
    'status 200': (r) => r.status === 200,
    'has evaluations': (r) => {
      try {
        evaluations = r.json('evaluations');
        return evaluations !== null && typeof evaluations === 'object';
      } catch (e) {
        return false;
      }
    },
  });

  if (ok && evaluations) {
    for (const key of Object.keys(evaluations)) {
      assignedRate.add(evaluations[key].assigned === true);
    }
  } else {
    assignedRate.add(false);
  }
}

export function handleSummary(data) {
  return summaryOutputs(data, textSummary);
}
