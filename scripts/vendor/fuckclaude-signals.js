/*! Vendored from https://github.com/LinXiaoTao/FuckClaude src/config/signals.ts
 * commit e4aadac01d7a1456e98db71d4da34fe27b3bee52, transpiled with esbuild@0.24.0 (iife, global FuckClaudeSignals).
 * Copyright (c) 2026 LinXiaoTao. MIT License, see FUCKCLAUDE-LICENSE.txt. Regenerate with update_fuckclaude_signals.py. */
var FuckClaudeSignals = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);
  var signals_exports = {};
  __export(signals_exports, {
    CLAUDE_TIMEZONES: () => CLAUDE_TIMEZONES,
    CN_TIMEZONES: () => CN_TIMEZONES,
    GREATER_CN_TIMEZONES: () => GREATER_CN_TIMEZONES,
    SIGNALS: () => SIGNALS,
    riskBand: () => riskBand,
    scoreCnBrowser: () => scoreCnBrowser,
    scoreCnDevice: () => scoreCnDevice,
    scoreEmojiVendor: () => scoreEmojiVendor,
    scoreLanguages: () => scoreLanguages,
    scoreTimezone: () => scoreTimezone,
    signalVerdict: () => signalVerdict
  });
  const CN_TIMEZONES = [
    "Asia/Shanghai",
    "Asia/Urumqi",
    "Asia/Chongqing",
    "Asia/Chungking",
    "Asia/Harbin",
    "Asia/Kashgar"
  ];
  const CLAUDE_TIMEZONES = ["Asia/Shanghai", "Asia/Urumqi"];
  const GREATER_CN_TIMEZONES = ["Asia/Hong_Kong", "Asia/Macau"];
  const FONTS_SC = [
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "SimSun",
    "NSimSun",
    "SimHei",
    "KaiTi",
    "FangSong",
    "DengXian",
    "PingFang SC",
    "Hiragino Sans GB",
    "STHeiti",
    "STSong",
    "Songti SC",
    "Source Han Sans CN",
    "Source Han Sans SC",
    "Noto Sans CJK SC",
    "Noto Serif CJK SC",
    "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei"
  ];
  const FONTS_TC = [
    "Microsoft JhengHei",
    "PMingLiU",
    "MingLiU",
    "DFKai-SB",
    "PingFang TC",
    "PingFang HK",
    "Source Han Sans TW",
    "Noto Sans CJK TC"
  ];
  const FONTS_CN_VENDOR = [
    "MiSans",
    // Xiaomi HyperOS / MIUI
    "MIUI",
    // legacy Xiaomi
    "HarmonyOS Sans SC",
    // Huawei
    "HarmonyOS Sans",
    // Huawei
    "HONOR Sans",
    // Honor
    "OPPO Sans",
    // OPPO / OnePlus (CN)
    "vivo Sans",
    // vivo
    "Alibaba PuHuiTi",
    // Alibaba
    "Alibaba Sans",
    // Alibaba
    "DingTalk JinBuTi",
    // DingTalk
    "Douyin Sans",
    // ByteDance / Douyin
    "HYQiHei",
    // HanYi, bundled by several CN apps
    "FZShuSong-Z01S",
    // Founder faces installed with WPS Office
    "FZKai-Z03S",
    "FZHei-B01S",
    "FZFangSong-Z02S"
  ];
  const CN_BROWSER_PATTERNS = [
    [/micromessenger|wxwork/i, "WeChat"],
    [/mqqbrowser|qqbrowser|\bqq\//i, "QQ Browser"],
    [/quark/i, "Quark"],
    [/ucbrowser|ucweb/i, "UC Browser"],
    [/baiduboxapp|bidubrowser|baidubrowser/i, "Baidu"],
    [/miuibrowser|xiaomi\/|mibrowser/i, "Mi Browser"],
    [/huaweibrowser/i, "Huawei Browser"],
    [/heytapbrowser|oppobrowser/i, "HeyTap (OPPO)"],
    [/vivobrowser/i, "vivo Browser"],
    [/sogoumobilebrowser|\bmetasr\b|\bse 2\.x\b/i, "Sogou"],
    [/maxthon/i, "Maxthon"],
    [/360se|360ee|qihoobrowser|\bqhbrowser\b/i, "360 Browser"],
    [/2345explorer|2345browser/i, "2345"],
    [/lbbrowser/i, "Liebao"],
    [/theworld/i, "TheWorld"],
    [/aweme|bytedancewebview|newsarticle|toutiaomicroapp/i, "Douyin / Toutiao"],
    [/alipayclient/i, "Alipay"],
    [/dingtalk/i, "DingTalk"],
    [/weibo/i, "Weibo"],
    [/xiaohongshu|xhsminiapp/i, "Xiaohongshu"],
    [/\bbilibili\b/i, "Bilibili"]
  ];
  const CN_DEVICE_PATTERNS = [
    [/harmonyos|openharmony/i, "HarmonyOS", 1],
    [/huawei|\bhonor\b/i, "Huawei / Honor", 0.8],
    [/meizu/i, "Meizu", 0.8],
    [/nubia|\bzte\b/i, "ZTE / nubia", 0.7],
    [/xiaomi|redmi|\bpoco\b|\bm2\d{3}[a-z0-9]+\b/i, "Xiaomi", 0.6],
    [/oppo|\bpd[a-z]m\d{2}\b/i, "OPPO", 0.6],
    [/vivo|\bv2\d{3}[a-z]{1,2}\b/i, "vivo", 0.6],
    [/realme|\brmx\d{4}\b/i, "realme", 0.6],
    [/oneplus/i, "OnePlus", 0.6],
    [/\blenovo\b|\bzuk\b/i, "Lenovo", 0.5]
  ];
  function getTimezone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch {
      return "";
    }
  }
  function scoreTimezone(tz) {
    if (CLAUDE_TIMEZONES.includes(tz) || CN_TIMEZONES.includes(tz)) return 1;
    if (GREATER_CN_TIMEZONES.includes(tz)) return 0.6;
    return 0;
  }
  function detectTimezone() {
    const tz = getTimezone();
    return { raw: tz || "unknown", score: scoreTimezone(tz) };
  }
  function detectTimezoneOffset() {
    const offset = (/* @__PURE__ */ new Date()).getTimezoneOffset();
    const utcHours = -offset / 60;
    const sign = utcHours >= 0 ? "+" : "-";
    const raw = `UTC${sign}${Math.abs(utcHours)}`;
    return { raw, score: offset === -480 ? 0.7 : 0 };
  }
  function normLangs() {
    const list = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language];
    return list.map((l) => (l || "").toLowerCase());
  }
  function scoreLanguages(langs) {
    const list = langs.map((l) => (l || "").toLowerCase()).filter(Boolean);
    const isTW = (l) => l.startsWith("zh-tw") || l.includes("hant") && l.includes("tw");
    const isHKMO = (l) => l.startsWith("zh-hk") || l.startsWith("zh-mo");
    const isTrad = (l) => isTW(l) || isHKMO(l) || l.includes("hant");
    const firstTrad = list.findIndex(isTrad);
    const isHansCN = (l, i) => l.startsWith("zh-cn") || l.includes("hans") || l === "zh" && (firstTrad === -1 || i < firstTrad);
    const kept = list.map((l, i) => ({ l, i })).filter(({ l, i }) => !isTW(l) && !(l === "zh" && firstTrad !== -1 && i > firstTrad));
    const primary = kept[0];
    if (!primary) return 0;
    if (isHansCN(primary.l, primary.i)) return 1;
    if (isHKMO(primary.l) || primary.l.includes("hant")) return 0.5;
    if (kept.some(({ l, i }) => isHansCN(l, i))) return 0.7;
    if (kept.some(({ l }) => l.startsWith("zh"))) return 0.4;
    return 0;
  }
  function detectLanguage() {
    const langs = normLangs();
    return { raw: langs.join(", ") || "unknown", score: scoreLanguages(langs) };
  }
  function detectIntlLocale() {
    let locale = "";
    try {
      locale = Intl.DateTimeFormat().resolvedOptions().locale || "";
    } catch {
      locale = "";
    }
    const l = locale.toLowerCase();
    let score = 0;
    if (l.startsWith("zh-cn") || l.includes("hans") || l === "zh") score = 1;
    else if (l.startsWith("zh") && !l.startsWith("zh-tw")) score = 0.5;
    return { raw: locale || "unknown", score };
  }
  function isFontAvailable(font, ctx) {
    const testString = "\u4E2D\u6587\u5B57\u4F53\u68C0\u6D4BABCabc012";
    const size = "72px";
    const bases = ["monospace", "sans-serif", "serif"];
    return bases.some((base) => {
      ctx.font = `${size} ${base}`;
      const baseWidth = ctx.measureText(testString).width;
      ctx.font = `${size} "${font}", ${base}`;
      const testWidth = ctx.measureText(testString).width;
      return Math.abs(testWidth - baseWidth) > 0.5;
    });
  }
  function detectFonts() {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return { raw: "canvas unavailable", score: 0 };
    const sc = FONTS_SC.filter((f) => isFontAvailable(f, ctx));
    const tc = FONTS_TC.filter((f) => isFontAvailable(f, ctx));
    let score = 0;
    if (sc.length >= 1) score = Math.min(1, 0.75 + 0.08 * sc.length);
    else if (tc.length >= 1) score = 0.2;
    const hit = [...sc, ...tc];
    const raw = hit.length ? hit.slice(0, 4).join(", ") + (hit.length > 4 ? "\u2026" : "") : "none detected";
    return { raw, score };
  }
  function detectVendorFonts() {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return { raw: "canvas unavailable", score: 0 };
    const hit = FONTS_CN_VENDOR.filter((f) => isFontAvailable(f, ctx));
    const score = hit.length >= 2 ? 1 : hit.length === 1 ? 0.8 : 0;
    const raw = hit.length ? hit.slice(0, 3).join(", ") + (hit.length > 3 ? "\u2026" : "") : "none detected";
    return { raw, score };
  }
  function uaData() {
    return navigator.userAgentData;
  }
  function scoreCnBrowser(probe) {
    for (const [re, name] of CN_BROWSER_PATTERNS) {
      if (re.test(probe)) return { name, score: 1 };
    }
    return { name: null, score: 0 };
  }
  function detectCnBrowser() {
    const brands = (uaData()?.brands ?? []).map((b) => b.brand).join(" ");
    const { name, score } = scoreCnBrowser(`${navigator.userAgent} ${brands}`);
    return { raw: name ?? "none detected", score };
  }
  function scoreCnDevice(probe) {
    for (const [re, name, score] of CN_DEVICE_PATTERNS) {
      if (re.test(probe)) return { name, score };
    }
    return { name: null, score: 0 };
  }
  async function detectDeviceVendor() {
    let extra = "";
    try {
      const high = await uaData()?.getHighEntropyValues?.(["model", "platform", "platformVersion"]);
      if (high) extra = ` ${String(high.model ?? "")} ${String(high.platform ?? "")}`;
    } catch {
    }
    const { name, score } = scoreCnDevice(`${navigator.userAgent}${extra}`);
    return { raw: name ?? "none detected", score };
  }
  function scoreEmojiVendor(probe) {
    const p = probe.toLowerCase();
    let vendor = "Unknown";
    if (/iphone|ipad|ipod|mac/.test(p)) vendor = "Apple";
    else if (/android/.test(p)) vendor = "Google";
    else if (/win/.test(p)) vendor = "Microsoft";
    else if (/cros/.test(p)) vendor = "Google";
    else if (/linux/.test(p)) vendor = "Linux / Other";
    const vendorScore = {
      Apple: 0.25,
      Microsoft: 0.4,
      Google: 0.35,
      "Linux / Other": 0.5,
      Unknown: 0.4
    };
    return { vendor, score: vendorScore[vendor] ?? 0.4 };
  }
  function detectEmoji() {
    const ua = (navigator.userAgent || "").toLowerCase();
    const platform = (navigator.platform || "").toLowerCase();
    const { vendor, score } = scoreEmojiVendor(`${platform} ${ua}`);
    return { raw: `${vendor} style`, score };
  }
  function detectWebrtcLeak() {
    return new Promise((resolve) => {
      if (typeof window === "undefined" || !window.RTCPeerConnection) {
        resolve({ raw: "no leak detected", score: 0 });
        return;
      }
      let resolved = false;
      const ips = [];
      let pc = null;
      const finish = () => {
        if (resolved) return;
        resolved = true;
        try {
          if (pc) pc.close();
        } catch {
        }
        if (ips.length === 0) {
          resolve({ raw: "no leak detected", score: 0 });
        } else {
          const raw = ips.slice(0, 2).join(", ");
          resolve({ raw: `candidate leak (${raw})`, score: 0.5 });
        }
      };
      try {
        pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
        pc.onicecandidate = (e) => {
          if (!e.candidate || !e.candidate.candidate) {
            finish();
            return;
          }
          const match = /([0-9]{1,3}(\.[0-9]{1,3}){3}|[a-f0-9]{1,4}(:[a-f0-9]{1,4}){7})/i.exec(e.candidate.candidate);
          if (match && match[1] && !ips.includes(match[1])) {
            ips.push(match[1]);
          }
        };
        pc.createDataChannel("");
        pc.createOffer().then((sdp) => pc?.setLocalDescription(sdp)).catch(() => finish());
      } catch {
        finish();
      }
      setTimeout(finish, 1e3);
    });
  }
  const ICON = {
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    clockOffset: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v4h4"/></svg>',
    globe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 3 2.6 15 0 18M12 3c-2.6 3-2.6 15 0 18"/></svg>',
    type: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 6V5h14v1M12 5v14M9 19h6"/></svg>',
    typeBox: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8.6 15.5 12 8l3.4 7.5M9.8 13h4.4"/></svg>',
    compass: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m15.2 8.8-1.7 4.7-4.7 1.7 1.7-4.7z"/></svg>',
    phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 17.5h2"/></svg>',
    sliders: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h16M4 16h16"/><circle cx="9" cy="8" r="2.2"/><circle cx="15" cy="16" r="2.2"/></svg>',
    shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    smile: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8.5 14.5s1.4 2 3.5 2 3.5-2 3.5-2"/><path d="M9 9.5h.01M15 9.5h.01"/></svg>'
  };
  const SIGNALS = [
    { id: "timezone", weight: 24, claudeUsed: true, icon: ICON.clock, detect: detectTimezone },
    { id: "language", weight: 18, icon: ICON.globe, detect: detectLanguage },
    { id: "fonts", weight: 14, icon: ICON.type, detect: detectFonts },
    { id: "vendorFonts", weight: 10, icon: ICON.typeBox, detect: detectVendorFonts },
    { id: "webrtcLeak", weight: 10, icon: ICON.shield, detect: detectWebrtcLeak },
    { id: "cnBrowser", weight: 8, icon: ICON.compass, detect: detectCnBrowser },
    { id: "deviceVendor", weight: 6, icon: ICON.phone, detect: detectDeviceVendor },
    { id: "intlLocale", weight: 4, icon: ICON.sliders, detect: detectIntlLocale },
    { id: "timezoneOffset", weight: 3, icon: ICON.clockOffset, detect: detectTimezoneOffset },
    { id: "emoji", weight: 3, icon: ICON.smile, detect: detectEmoji }
  ];
  function riskBand(total) {
    if (total <= 30) return "low";
    if (total <= 60) return "medium";
    return "high";
  }
  function signalVerdict(score) {
    if (score >= 0.6) return "high";
    if (score >= 0.25) return "medium";
    return "low";
  }
  return __toCommonJS(signals_exports);
})();
