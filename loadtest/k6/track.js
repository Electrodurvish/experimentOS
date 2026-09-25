// k6 load test for event ingestion: POST /api/v1/events/track/
//
//   k6 run -e PROFILE=1000 loadtest/k6/track.js
//   k6 run -e PROFILE=500 -e DUPLICATE_RATE=0.1 loadtest/k6/track.js
//
// The API only enqueues to Kafka (202 Accepted); this measures the HTTP
// ingestion path. End-to-end throughput (Kafka -> consumer -> ClickHouse) must
// be read from the consumer's events_consumed_total counter - see
// docs/load-testing.md.
//
// DUPLICATE_RATE (0..1) re-sends a previously used event_id so the consumer's
// Redis SETNX de-duplication can be verified afterwards (count of
// events_consumed_total{result="duplicate"} should match "track_duplicates_sent").
import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.1.0/index.js';

import { BASE_URL, headers, randomUserId, scenarioFor, summaryOutputs } from './lib.js';

const DUPLICATE_RATE = parseFloat(__ENV.DUPLICATE_RATE || '0');
const EVENT_NAMES = ['purchase', 'signup', 'add_to_cart', 'page_view'];

const duplicatesSent = new Counter('track_duplicates_sent');
const uniqueSent = new Counter('track_unique_sent');

export const options = {
  scenarios: scenarioFor('track'),
  thresholds: {
    // Plan target: API P95 < 200ms.
    'http_req_duration{name:track}': ['p(95)<200'],
    'http_req_failed{name:track}': ['rate<0.01'],
    checks: ['rate>0.99'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

// Per-VU memory of sent ids to replay as duplicates.
const recent = [];

function uuid4() {
  // RFC4122-ish v4 id; uniqueness is what matters here.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export default function () {
  let eventId;
  if (DUPLICATE_RATE > 0 && recent.length > 0 && Math.random() < DUPLICATE_RATE) {
    eventId = recent[Math.floor(Math.random() * recent.length)];
    duplicatesSent.add(1);
  } else {
    eventId = `${__VU}-${__ITER}-${uuid4()}`;
    uniqueSent.add(1);
    recent.push(eventId);
    if (recent.length > 1000) {
      recent.shift();
    }
  }

  const payload = JSON.stringify({
    event_id: eventId,
    user_id: randomUserId(),
    event_name: EVENT_NAMES[Math.floor(Math.random() * EVENT_NAMES.length)],
    value: Math.round(Math.random() * 10000) / 100,
    metadata: { source: 'k6' },
  });

  const res = http.post(`${BASE_URL}/api/v1/events/track/`, payload, {
    headers: headers(),
    tags: { name: 'track' },
  });

  check(res, {
    'status 202': (r) => r.status === 202,
    'echoes event_id': (r) => {
      try {
        return r.json('event_id') === eventId;
      } catch (e) {
        return false;
      }
    },
  });
}

export function handleSummary(data) {
  return summaryOutputs(data, textSummary);
}
