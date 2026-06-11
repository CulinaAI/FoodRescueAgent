import { Devvit } from "@devvit/public-api";

// ─── Config ────────────────────────────────────────────────────────────────
const AGENT_URL = "https://api.fracc.culinaai.co/analyze";
const API_KEY   = "fR4_s3cr3t_k3y_999";
const MAX_IMAGES = 3;

// Quick pre-filter: at least one food-rescue keyword must appear.
// The full LLM intent check runs inside the agent.
const FOOD_KW = [
  "leftover", "going bad", "expir", "wast", "rescue",
  "wilting", "overripe", "fridge", "spoil", "use up",
  "before it goes", "don't want to waste", "help me use",
  "use them up", "running out", "about to go",
];

function looksLikeFoodRescue(text: string): boolean {
  const lower = text.toLowerCase();
  return FOOD_KW.some((kw) => lower.includes(kw));
}

// ─── Devvit setup ──────────────────────────────────────────────────────────
Devvit.configure({
  redditAPI: true,
  http: true,       // enables outbound fetch()
});

// ─── PostCreate trigger ────────────────────────────────────────────────────
Devvit.addTrigger({
  event: "PostCreate",
  onEvent: async (event, _context) => {
    const post      = event.post;
    const subreddit = event.subreddit;
    if (!post || !subreddit) return;

    const title    = post.title ?? "";
    const selftext = post.selftext ?? "";
    const text     = `${title}\n\n${selftext}`.trim();

    // Quick keyword gate — saves LLM calls for clearly unrelated posts
    if (!looksLikeFoodRescue(text)) return;

    // Collect images from post URL / gallery (up to MAX_IMAGES)
    const images: string[] = [];
    const imageExts = [".jpg", ".jpeg", ".png", ".gif", ".webp"];

    const url = post.url ?? "";
    const ext = url.toLowerCase().split("?")[0].slice(url.lastIndexOf("."));
    if (imageExts.includes(ext)) {
      try {
        const imgResp = await fetch(url);
        if (imgResp.ok) {
          const buf = await imgResp.arrayBuffer();
          images.push(
            btoa(String.fromCharCode(...new Uint8Array(buf)))
          );
        }
      } catch {
        // image download failed — proceed without image
      }
    }

    const postUrl = `https://reddit.com/r/${subreddit.name}/comments/${post.id}`;

    // Call our GCP food-rescue agent
    try {
      const resp = await fetch(AGENT_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": API_KEY,
        },
        body: JSON.stringify({
          text,
          platform: "reddit",
          idempotency_key: `reddit:${post.id}`,
          source_metadata: {
            subreddit: subreddit.name,
            post_title: title,
            post_url: postUrl,
            reddit_post_id: post.id,
          },
          images: images.slice(0, MAX_IMAGES),
        }),
      });
      console.log(`[culina-fracc] analyzed post ${post.id}: HTTP ${resp.status}`);
    } catch (err) {
      console.error(`[culina-fracc] fetch failed for post ${post.id}:`, err);
    }
  },
});

export default Devvit;
