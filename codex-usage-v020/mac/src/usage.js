'use strict';
function numberOrNull(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
function readField(obj, camel, snake) {
  if (!obj || typeof obj !== 'object') return null;
  if (obj[camel] !== undefined) return obj[camel];
  if (obj[snake] !== undefined) return obj[snake];
  return null;
}
function normalizeBucket(bucket) {
  if (!bucket) return null;
  const usedPercent = numberOrNull(readField(bucket, 'usedPercent', 'used_percent'));
  const windowDurationMins = numberOrNull(readField(bucket, 'windowDurationMins', 'window_minutes'));
  const resetsAt = numberOrNull(readField(bucket, 'resetsAt', 'resets_at'));
  if (usedPercent === null || windowDurationMins === null) return null;
  return {
    usedPercent,
    remainingPercent: Math.max(0, Math.min(100, Math.round(100 - usedPercent))),
    windowDurationMins,
    resetsAt
  };
}
function pickRateLimits(result) {
  if (!result || typeof result !== 'object') return null;
  if (result.rateLimitsByLimitId?.codex) return result.rateLimitsByLimitId.codex;
  if (result.rateLimits) return result.rateLimits;
  if (result.rate_limits) return result.rate_limits;
  if (result.primary || result.secondary) return result;
  return null;
}
function normalizeUsage(result) {
  const limits = pickRateLimits(result);
  if (!limits) return null;
  const buckets = [normalizeBucket(limits.primary), normalizeBucket(limits.secondary)]
    .filter(Boolean)
    .sort((a, b) => a.windowDurationMins - b.windowDurationMins);
  if (!buckets.length) return null;
  const weekly = buckets.find((b) => b.windowDurationMins === 10080) || buckets[buckets.length - 1];
  const shortTerm = buckets.find((b) => b.windowDurationMins === 300) || (buckets.length > 1 ? buckets[0] : null);
  return {
    weekly,
    shortTerm: shortTerm === weekly ? null : shortTerm,
    planType: limits.planType || limits.plan_type || result.planType || result.plan_type || null,
    resetCredits: result.rateLimitResetCredits || result.rate_limit_reset_credits || null,
    updatedAt: Math.floor(Date.now() / 1000)
  };
}
module.exports = { normalizeBucket, normalizeUsage };
