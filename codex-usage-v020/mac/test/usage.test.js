'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeUsage } = require('../src/usage');

test('주간 한도를 가장 긴 창으로 인식한다', () => {
  const usage = normalizeUsage({
    rateLimits: {
      primary: { usedPercent: 39, windowDurationMins: 10080, resetsAt: 1760000000 },
      secondary: { usedPercent: 12, windowDurationMins: 300, resetsAt: 1759000000 },
      planType: 'plus'
    }
  });
  assert.equal(usage.weekly.remainingPercent, 61);
  assert.equal(usage.weekly.windowDurationMins, 10080);
  assert.equal(usage.shortTerm.remainingPercent, 88);
  assert.equal(usage.planType, 'plus');
});

test('snake_case 응답도 처리한다', () => {
  const usage = normalizeUsage({
    rate_limits: {
      primary: { used_percent: 25.2, window_minutes: 300, resets_at: 1761000000 },
      secondary: { used_percent: 55.6, window_minutes: 10080, resets_at: 1762000000 },
      plan_type: 'pro'
    }
  });
  assert.equal(usage.shortTerm.remainingPercent, 75);
  assert.equal(usage.weekly.remainingPercent, 44);
  assert.equal(usage.planType, 'pro');
});

test('rateLimitsByLimitId.codex 응답도 처리한다', () => {
  const usage = normalizeUsage({
    rateLimitsByLimitId: {
      codex: {
        primary: { usedPercent: 10, windowDurationMins: 300 },
        secondary: { usedPercent: 90, windowDurationMins: 10080 }
      }
    }
  });
  assert.equal(usage.shortTerm.remainingPercent, 90);
  assert.equal(usage.weekly.remainingPercent, 10);
});
