import crypto from "node:crypto";

const HUB_BASE_URL = "https://naverapihub.apigw.ntruss.com";
const SEARCH_AD_BASE_URL = "https://api.searchad.naver.com";
const MAX_KEYWORDS = 5;
const MAX_RELATED = 20;

function setCors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type,X-Analyzer-Key");
}

function json(res, status, body) {
  setCors(res);
  res.status(status).json(body);
}

function requiredEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing environment variable: ${name}`);
  return value;
}

function optionalEnv(name) {
  return process.env[name]?.trim() || null;
}

function verifyAnalyzerKey(req) {
  const expected = requiredEnv("ANALYZER_API_KEY");
  const received = req.headers["x-analyzer-key"];
  if (typeof received !== "string") return false;

  const expectedBuffer = Buffer.from(expected);
  const receivedBuffer = Buffer.from(received);
  return (
    expectedBuffer.length === receivedBuffer.length &&
    crypto.timingSafeEqual(expectedBuffer, receivedBuffer)
  );
}

function cleanKeyword(value) {
  if (typeof value !== "string") return "";
  return value.trim().replace(/\s+/g, " ");
}

function normalizeKeyword(value) {
  return cleanKeyword(value).replace(/\s+/g, "").toLocaleLowerCase("ko-KR");
}

function uniqueKeywords(values) {
  const seen = new Set();
  const output = [];
  for (const raw of values) {
    const keyword = cleanKeyword(raw);
    const normalized = normalizeKeyword(keyword);
    if (!keyword || seen.has(normalized)) continue;
    seen.add(normalized);
    output.push(keyword);
  }
  return output;
}

function kstDate(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function addDays(dateString, amount) {
  const [year, month, day] = dateString.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

function average(values) {
  const valid = values.filter((value) => Number.isFinite(value));
  if (!valid.length) return null;
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function round(value, digits = 2) {
  if (!Number.isFinite(value)) return null;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function percentChange(current, previous) {
  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) {
    return null;
  }
  return round(((current - previous) / previous) * 100);
}

async function fetchJson(url, options = {}, label = "API") {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(options.headers || {}),
      },
    });

    const text = await response.text();
    let payload;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = { raw: text };
    }

    if (!response.ok) {
      const error = new Error(`${label} failed with HTTP ${response.status}`);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  } finally {
    clearTimeout(timeout);
  }
}

function hubHeaders() {
  return {
    "X-NCP-APIGW-API-KEY-ID": requiredEnv("NAVER_HUB_CLIENT_ID"),
    "X-NCP-APIGW-API-KEY": requiredEnv("NAVER_HUB_CLIENT_SECRET"),
  };
}

async function fetchTrend(keywords, trendDays) {
  const today = kstDate();
  const endDate = addDays(today, -1);
  const startDate = addDays(endDate, -(trendDays - 1));

  const payload = await fetchJson(
    `${HUB_BASE_URL}/search-trend/v1/search`,
    {
      method: "POST",
      headers: {
        ...hubHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        startDate,
        endDate,
        timeUnit: "date",
        keywordGroups: keywords.map((keyword) => ({
          groupName: keyword,
          keywords: [keyword],
        })),
      }),
    },
    "NAVER API HUB Search Trend"
  );

  const byTitle = new Map(
    (payload?.results || []).map((result) => [
      normalizeKeyword(result.title),
      result,
    ])
  );

  return {
    startDate,
    endDate,
    results: keywords.map((keyword) => {
      const result = byTitle.get(normalizeKeyword(keyword));
      const data = (result?.data || [])
        .map((entry) => ({
          period: entry.period,
          ratio: Number(entry.ratio),
        }))
        .filter((entry) => Number.isFinite(entry.ratio))
        .sort((a, b) => a.period.localeCompare(b.period));

      const ratios = data.map((entry) => entry.ratio);
      const last7 = ratios.slice(-7);
      const previous7 = ratios.slice(-14, -7);
      const last30 = ratios.slice(-30);
      const previous30 = ratios.slice(-60, -30);

      const avg7 = average(last7);
      const prevAvg7 = average(previous7);
      const avg30 = average(last30);
      const prevAvg30 = average(previous30);

      return {
        keyword,
        latestRatio: data.length ? round(data.at(-1).ratio) : null,
        average7d: round(avg7),
        previousAverage7d: round(prevAvg7),
        change7dPct: percentChange(avg7, prevAvg7),
        average30d: round(avg30),
        previousAverage30d: round(prevAvg30),
        change30dPct: percentChange(avg30, prevAvg30),
        peakDate:
          data.length > 0
            ? data.reduce((peak, item) =>
                item.ratio > peak.ratio ? item : peak
              ).period
            : null,
        daily: data,
      };
    }),
  };
}

function parseSearchCount(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return { raw: value, exact: value, min: value, maxExclusive: value + 1 };
  }

  const text = String(value ?? "").trim().replace(/\s+/g, "");
  const lessThan = text.match(/^<(\d+)$/);
  if (lessThan) {
    const maxExclusive = Number(lessThan[1]);
    return { raw: value, exact: null, min: 0, maxExclusive };
  }

  const numeric = Number(text.replace(/,/g, ""));
  if (Number.isFinite(numeric)) {
    return { raw: value, exact: numeric, min: numeric, maxExclusive: numeric + 1 };
  }

  return { raw: value, exact: null, min: null, maxExclusive: null };
}

function combineSearchCounts(pcRaw, mobileRaw) {
  const pc = parseSearchCount(pcRaw);
  const mobile = parseSearchCount(mobileRaw);
  const exact =
    pc.exact !== null && mobile.exact !== null ? pc.exact + mobile.exact : null;
  const min =
    pc.min !== null && mobile.min !== null ? pc.min + mobile.min : null;
  const maxExclusive =
    pc.maxExclusive !== null && mobile.maxExclusive !== null
      ? pc.maxExclusive + mobile.maxExclusive
      : null;

  return {
    pc: pc.raw,
    mobile: mobile.raw,
    exactTotal: exact,
    totalRange:
      exact !== null
        ? { min: exact, maxExclusive: exact + 1 }
        : min !== null && maxExclusive !== null
          ? { min, maxExclusive }
          : null,
  };
}

function searchAdHeaders(method, uri) {
  const apiKey = requiredEnv("NAVER_SEARCHAD_API_KEY");
  const secretKey = requiredEnv("NAVER_SEARCHAD_SECRET_KEY");
  const customerId = requiredEnv("NAVER_SEARCHAD_CUSTOMER_ID");
  const timestamp = Date.now().toString();
  const message = `${timestamp}.${method}.${uri}`;
  const signature = crypto
    .createHmac("sha256", secretKey)
    .update(message)
    .digest("base64");

  return {
    "Content-Type": "application/json; charset=UTF-8",
    "X-Timestamp": timestamp,
    "X-API-KEY": apiKey,
    "X-Customer": customerId,
    "X-Signature": signature,
  };
}

async function fetchSearchAdKeyword(keyword) {
  const uri = "/keywordstool";
  const url = new URL(`${SEARCH_AD_BASE_URL}${uri}`);
  url.searchParams.set("hintKeywords", keyword);
  url.searchParams.set("showDetail", "1");

  const payload = await fetchJson(
    url,
    {
      method: "GET",
      headers: searchAdHeaders("GET", uri),
    },
    "NAVER Search Ad Keyword Tool"
  );

  const list = Array.isArray(payload?.keywordList) ? payload.keywordList : [];
  const normalized = normalizeKeyword(keyword);
  const exact =
    list.find((item) => normalizeKeyword(item.relKeyword) === normalized) ||
    list[0] ||
    null;

  if (!exact) {
    return {
      keyword,
      found: false,
      monthlySearches: null,
      competition: null,
      relatedKeywords: [],
    };
  }

  const relatedKeywords = list
    .filter((item) => normalizeKeyword(item.relKeyword) !== normalized)
    .slice(0, MAX_RELATED)
    .map((item) => ({
      keyword: item.relKeyword,
      monthlySearches: combineSearchCounts(
        item.monthlyPcQcCnt,
        item.monthlyMobileQcCnt
      ),
      competition: item.compIdx ?? null,
    }));

  return {
    keyword,
    found: true,
    matchedKeyword: exact.relKeyword,
    monthlySearches: combineSearchCounts(
      exact.monthlyPcQcCnt,
      exact.monthlyMobileQcCnt
    ),
    monthlyClicks: {
      pc: exact.monthlyAvePcClkCnt ?? null,
      mobile: exact.monthlyAveMobileClkCnt ?? null,
    },
    monthlyCtr: {
      pc: exact.monthlyAvePcCtr ?? null,
      mobile: exact.monthlyAveMobileCtr ?? null,
    },
    competition: exact.compIdx ?? null,
    averageAdDepth: exact.plAvgDepth ?? null,
    relatedKeywords,
  };
}

function parseBlogPostDate(value) {
  const text = String(value ?? "");
  if (!/^\d{8}$/.test(text)) return null;
  return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
}

function countRecentDates(dateStrings, checkedDate) {
  const thresholds = {
    one: addDays(checkedDate, -1),
    seven: addDays(checkedDate, -7),
    thirty: addDays(checkedDate, -30),
  };

  const valid = dateStrings.filter(Boolean);
  return {
    within1d: valid.filter((date) => date >= thresholds.one).length,
    within7d: valid.filter((date) => date >= thresholds.seven).length,
    within30d: valid.filter((date) => date >= thresholds.thirty).length,
    sampledItems: valid.length,
  };
}

async function fetchSearchFreshness(keyword) {
  const headers = hubHeaders();
  const checkedDate = kstDate();

  const blogUrl = new URL(`${HUB_BASE_URL}/search/v1/blog`);
  blogUrl.searchParams.set("query", keyword);
  blogUrl.searchParams.set("display", "100");
  blogUrl.searchParams.set("start", "1");
  blogUrl.searchParams.set("sort", "date");

  const newsUrl = new URL(`${HUB_BASE_URL}/search/v1/news`);
  newsUrl.searchParams.set("query", keyword);
  newsUrl.searchParams.set("display", "100");
  newsUrl.searchParams.set("start", "1");
  newsUrl.searchParams.set("sort", "date");

  const [blog, news] = await Promise.all([
    fetchJson(blogUrl, { method: "GET", headers }, "NAVER API HUB Blog Search"),
    fetchJson(newsUrl, { method: "GET", headers }, "NAVER API HUB News Search"),
  ]);

  const blogDates = (blog?.items || []).map((item) =>
    parseBlogPostDate(item.postdate)
  );
  const newsDates = (news?.items || []).map((item) => {
    const date = new Date(item.pubDate);
    return Number.isNaN(date.getTime()) ? null : kstDate(date);
  });

  return {
    blog: {
      totalIndexedResults: Number(blog?.total ?? 0),
      ...countRecentDates(blogDates, checkedDate),
      note: "최근 문서 수는 날짜순 상위 100개 표본 기준입니다.",
    },
    news: {
      totalIndexedResults: Number(news?.total ?? 0),
      ...countRecentDates(newsDates, checkedDate),
      note: "최근 문서 수는 날짜순 상위 100개 표본 기준입니다.",
    },
  };
}

function sourceError(error) {
  return {
    message: error?.message || "Unknown API error",
    status: error?.status || null,
    details: error?.payload || null,
  };
}

export default async function handler(req, res) {
  if (req.method === "OPTIONS") {
    setCors(res);
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return json(res, 405, { error: "Method not allowed. Use POST." });
  }

  try {
    if (!verifyAnalyzerKey(req)) {
      return json(res, 401, { error: "Invalid or missing X-Analyzer-Key." });
    }

    const keywords = uniqueKeywords(req.body?.keywords || []);
    const trendDays = Math.min(
      Math.max(Number(req.body?.trendDays || 90), 30),
      365
    );

    if (!keywords.length) {
      return json(res, 400, { error: "keywords must contain at least one keyword." });
    }
    if (keywords.length > MAX_KEYWORDS) {
      return json(res, 400, {
        error: `A maximum of ${MAX_KEYWORDS} keywords can be analyzed per request.`,
      });
    }

    const checkedAt = new Date().toISOString();
    const searchAdConfigured = [
      optionalEnv("NAVER_SEARCHAD_API_KEY"),
      optionalEnv("NAVER_SEARCHAD_SECRET_KEY"),
      optionalEnv("NAVER_SEARCHAD_CUSTOMER_ID"),
    ].every(Boolean);

    let trend = null;
    let trendError = null;
    try {
      trend = await fetchTrend(keywords, trendDays);
    } catch (error) {
      trendError = sourceError(error);
    }

    const analyses = await Promise.all(
      keywords.map(async (keyword) => {
        const trendData =
          trend?.results?.find(
            (item) => normalizeKeyword(item.keyword) === normalizeKeyword(keyword)
          ) || null;

        const [searchVolumeResult, freshnessResult] = await Promise.allSettled([
          searchAdConfigured
            ? fetchSearchAdKeyword(keyword)
            : Promise.resolve(null),
          fetchSearchFreshness(keyword),
        ]);

        return {
          keyword,
          searchVolume:
            searchVolumeResult.status === "fulfilled"
              ? searchVolumeResult.value
              : null,
          searchVolumeError:
            searchVolumeResult.status === "rejected"
              ? sourceError(searchVolumeResult.reason)
              : null,
          trend: trendData,
          freshness:
            freshnessResult.status === "fulfilled"
              ? freshnessResult.value
              : null,
          freshnessError:
            freshnessResult.status === "rejected"
              ? sourceError(freshnessResult.reason)
              : null,
        };
      })
    );

    return json(res, 200, {
      checkedAt,
      timezone: "Asia/Seoul",
      dataMeaning: {
        monthlySearches:
          "네이버 검색광고 키워드 도구의 월간 규모 지표입니다. 실시간 검색량이 아닙니다.",
        trend:
          "NAVER API HUB 검색어 트렌드의 일간 상대지수입니다. 절대 검색량이 아닙니다.",
        freshness:
          "NAVER API HUB 블로그·뉴스 검색의 현재 결과와 날짜순 상위 100개 표본입니다.",
      },
      sourceStatus: {
        naverApiHubConfigured: Boolean(
          optionalEnv("NAVER_HUB_CLIENT_ID") &&
            optionalEnv("NAVER_HUB_CLIENT_SECRET")
        ),
        searchAdConfigured,
        trendError,
      },
      analyses,
    });
  } catch (error) {
    return json(res, 500, {
      error: error?.message || "Unexpected server error",
    });
  }
}
