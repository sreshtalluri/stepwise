const SUPPORTED_DOMAINS = [
  "youtube.com",
  "www.youtube.com",
  "youtu.be",
  "m.youtube.com",
  "tiktok.com",
  "www.tiktok.com",
  "vm.tiktok.com",
  "instagram.com",
  "www.instagram.com",
];

export function validateVideoUrl(input: string): {
  valid: boolean;
  error?: string;
} {
  if (!input.trim()) {
    return { valid: false, error: "Please enter a URL" };
  }

  let url: URL;
  try {
    url = new URL(input);
  } catch {
    return { valid: false, error: "Invalid URL format" };
  }

  if (!["http:", "https:"].includes(url.protocol)) {
    return { valid: false, error: "URL must use HTTP or HTTPS" };
  }

  const hostname = url.hostname.toLowerCase();
  const isSupported = SUPPORTED_DOMAINS.some(
    (domain) => hostname === domain || hostname.endsWith("." + domain)
  );

  if (!isSupported) {
    return {
      valid: false,
      error: "Unsupported platform. Try TikTok, YouTube, or Instagram",
    };
  }

  return { valid: true };
}
