import re
p = "src/factory/scriptgen.py"
s = open(p, encoding="utf-8").read()
new_func = '''def build_prompt(verse: dict, fmt: str) -> str:
    return f"""You are an expert devotional growth strategist and content writer for Instagram Reels. Given a Shiv Chalisa verse, produce a JSON object for a high-retention, scroll-stopping Instagram Reel script.

Verse (Devanagari): {verse['devanagari']}
Roman: {verse['roman']}
Meaning (Hindi): {verse['meaning_hi']}
Meaning (English): {verse['meaning_en']}

Format: {fmt}  (meaning=explain meaning; story=symbolism/story; when=when devotees chant; recital=recite verse with brief intro)

Growth & Retention Requirements:
- narration_hi: 70-110 Hindi words (Devanagari), powerful yet calm devotional tone, structured for 28-45s spoken duration. The first 3 seconds must create an immediate emotional hook or curiosity gap.
- Hooks: Provide 5 distinct viral retention hooks. Tag each style in hook_styles matching one of: (question | benefit | story_tease | fear_to_courage | curiosity). Make them scroll-stopping and highly relatable to modern life hurdles or spiritual depth.
- caption_hi, caption_roman: Include SEO-optimized description text containing terms like "Shiv Chalisa meaning", "Shiv Chalisa arth", and a strong organic engagement CTA pointing to link in bio (free PDF + audio). Do NOT promise comment-triggered DMs.
- hashtags: 3-5 targeted devotional hashtags.
- seo_keywords: 3-5 high-search keywords.
- visual_keywords: exactly 6 dynamic visual tags.
- image_prompts: exactly 3 cinematic, stylised, calm image descriptions (no real people, no text overlay).
- est_seconds: integer between 28 and 45.
- Safety: No health-cure, wealth, or guaranteed miracle claims; frame benefits around inner strength, focus, and devotion.

Return ONLY valid JSON matching keys: hooks, hook_styles, narration_hi, caption_hi, caption_roman, hashtags, seo_keywords, visual_keywords, image_prompts, est_seconds."""


'''
s = re.sub(r"def build_prompt\(verse: dict, fmt: str\) -> str:.*?def generate_one", new_func + "def generate_one", s, count=1, flags=re.S)
open(p, "w", encoding="utf-8").write(s)
print("done")
