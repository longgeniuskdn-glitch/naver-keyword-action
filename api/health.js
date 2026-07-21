export default function handler(req, res) {
  const configured = {
    analyzerKey: Boolean(process.env.ANALYZER_API_KEY),
    naverApiHub: Boolean(
      process.env.NAVER_HUB_CLIENT_ID && process.env.NAVER_HUB_CLIENT_SECRET
    ),
    naverSearchAd: Boolean(
      process.env.NAVER_SEARCHAD_API_KEY &&
        process.env.NAVER_SEARCHAD_SECRET_KEY &&
        process.env.NAVER_SEARCHAD_CUSTOMER_ID
    ),
  };

  res.status(200).json({
    ok: configured.analyzerKey && configured.naverApiHub,
    checkedAt: new Date().toISOString(),
    configured,
  });
}
