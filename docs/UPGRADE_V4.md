pages: 12
===== PAGE 1 =====
UPGRADE PROMPT v4: EDIT THE EXISTING BUILD IN
PLACE
Changes: (A) Pexels replaced by Pixabay + keyless
fallbacks, (B) Instagram publishing moves from my
own Meta developer app / Graph API to Make.com
(free plan), with a manual Business Suite fallback.
Do NOT rebuild from scratch. You are modifying the project already built from the v3 prompt
on this laptop (local project ~/chalisa or %USERPROFILE%\chalisa, Cloudflare Worker relay
in relay/, Supabase, KV, Telegram, YouTube). Preserve everything that works: scripts,
planner, rendering, buffer logic, autostart daemon, Factory API, site, secret hygiene.
0. WHAT CHANGES
Area Before (v3) After (v4)
Stock
visuals
Pexels (key
issuance now
paused)
Provider chain: Pixabay (optional key) -> Wikimedia
Commons (CC0/PD) -> Pollinations -> procedural
ffmpeg. Works with zero keys
IG
publishing
Worker calls
Instagram Graph
API with my Meta
app + token
Make.com free plan publishes at fixed slots using
its own approved Meta connection. No Meta
developer app, no token, no Graph API code running
Scheduler Worker cronpublishes Worker cron only manages the queue, alerts andcross-posting. Make pulls the next reel from theWorker at each slot
Engagement Auto replies +keyword DMs Removed (Make free credits cannot afford polling).CTA changes to link-in-bio
Analytics Worker pullsinsights Make fetches insights for one older reel per run andposts them to the Worker (piggyback). Optimizerruns on whatever metrics arrive
===== PAGE 2 =====
Fallback none
business_suite_manual: weekly batch export for
Meta Business Suite scheduling (me, about 15
min/week)
Everything not listed stays exactly as specified in v3.
1. RULES FOR EDITING AN EXISTING BUILD
1. Audit first, then change. Read the repo (README.md, docs/DECISIONS.md,
docs/VERIFICATION.md, git log), run the existing test suite and doctor.py, and write
docs/V4_AUDIT.md: what exists, what deviates from v3, which tests pass/fail. If the repo
differs from this prompt's assumptions, trust the repo and record the difference.
2. Snapshot and reversibility. Before any change: git tag pre-v4; copy the local SQLite
DB to backups/pre-v4/; export Supabase tables (queue, state) to JSON in
backups/pre-v4/; record the deployed Worker version (wrangler deployments list).
Write docs/ROLLBACK_V4.md with exact commands to return to the snapshot.
3. Feature flags, not deletions. Introduce publish.backend (section 4). Keep the Graph
API publisher/engagement code and its tests in the repo, dormant behind the flag. Do
not delete Meta-related code.
4. Migrations are additive and reversible. New columns/tables only; every migration has
an up and a down. Existing queued reels must survive (see 9).
5. Order of retirement: do NOT delete Meta secrets, the KV token or Graph API cron
steps until the Make route has completed three real successful posts (gate U9). Then
retire them as described in 7.
6. All v3 rules still apply: verify docs before coding (record in docs/API_NOTES.md),
evidence in docs/VERIFICATION.md, no secrets in files/logs/chat, secret scan blocks
commits and deploys, cost Rs 0, ask me only for missing inputs in section 8.
7. Keep all tests green at every commit. Add tests for every new behaviour. Small commits.
8. You cannot log into Make.com for me and the free plan has no Make API. Everything
inside Make is built by me from your exact guide (section 4.4). Everything else is yours.
2. CHANGE A: PIXABAY AND THE VISUAL PROVIDER CHAIN
2.1 Provider interface
Create or refactor to src/factory/visuals/providers/ with a common interface:
search(keywords, orientation, kind) -> [Asset], download(asset) -> Path, and
available() -> bool. Chain order comes from config: visuals.providers: [pixabay,
===== PAGE 3 =====
wikimedia_commons, pollinations, procedural].
A provider that lacks credentials, errors out, hits rate limits or returns nothing is skipped
automatically. A complete, good-looking reel must render with zero stock keys.
Keep the Pexels provider code, disabled unless a key is present.
2.2 Pixabay provider
Verify current docs at pixabay.com/api/docs: endpoints for images and videos,
parameters (key, q max length, lang, safesearch, per_page, orientation/filter
options, video size variants), the rate limit (default about 100 requests per 60 seconds),
caching requirement (cache search results for 24 h), and the rule against permanent
hotlinking. Record in API_NOTES.
Always download chosen assets into media/cache/pixabay/ (never hotlink); cache
search responses for 24 h; obey a configurable requests-per-minute cap with backoff
on 429.
Prefer portrait or crop-to-9:16 centre. For videos choose the smallest size variant at or
above 720 px width. Use safesearch=true.
Use keyword banks in data/visual_keywords.json per visual style (calm, devotional, no
people/faces, no text, no logos): for example Himalaya mist, snow peaks, temple bell,
diya flame, incense smoke, river at dawn, night sky stars, lotus, banyan forest,
ash/embers, flowing water. Never search for faces, deity photos of other faiths, brands
or political content.
Store per asset: provider, asset id, source page URL, uploader, license note ("Pixabay
Content License"), download time. Attribution is not required, but store it anyway.
The API key travels in the query string: ensure every logger, exception message and
requests debug path redacts key=. Add a unit test for this.
2.3 Wikimedia Commons provider (no key)
Only files whose license metadata is CC0 or Public Domain (check per file via the API's
extmetadata). Skip anything requiring attribution. Record the file page URL. Use for still
backgrounds only.
2.4 Pollinations and procedural
Keep the existing Pollinations still generator and the ffmpeg procedural generator
(gradient, particles, diya flame, smoke) as final fallbacks.
2.5 Tests (must pass)
Mocked Pixabay responses: parsing, caching (second call hits cache), 429 backoff, key
===== PAGE 4 =====
redaction in logs.
Chain behaviour: with all keyed providers disabled, render one reel and pass
validate().
Visual style rotation and similarity guard still work with the new providers.
3. CHANGE B (PART 1): PUBLISH BACKEND ABSTRACTION
Add config and code so publishing is pluggable:
Under make_com: the Worker cron must not call Instagram. Keep its
queue/buffer/alerts/YouTube/site logic.
scheduled_at for each reel equals a Make slot time exactly (IST), because jitter is 0.
The reel row gets new states: scheduled -> handed_off -> published |
failed_in_make | unknown.
4. CHANGE B (PART 2): MAKE.COM ROUTE
4.1 Verified facts to re-check in current docs before building
Make's Instagram app is "Instagram for Business (Facebook login)" with actions
including Create a reel post ("uploads and posts a new reel"), Create a comment,
Create a reply, and a Get post insights module. Confirm exact module names and
fields (video URL vs file, caption, cover, share-to-feed, returned media ID/permalink).
publish:
  backend: make_com            # make_com | business_suite_manual | graph_api (dormant; needs Meta app + token)
  make:
    max_reels_per_day: 2       # set by feasibility test U6
    slots_ist: ["06:30", "19:00"]
    credits_budget_monthly: 800          # of the 1,000 free credits; 20% margin
    credits_per_run_estimate: 6          # refine from measurements
    claim_window_minutes: 10
    unacked_alert_minutes: 30
    deadman_minutes: 75
    insight_piggyback: true
render:
  profile: standard            # standard | lite5mb, chosen by feasibility test
  lite5mb: {width: 720, height: 1280, fps: 30, video_kbps: 800, audio_kbps: 64, max_seconds: 40, max_mb: 4.8}
engagement: {enabled: false}
cta: {mode: bio_link}          # captions say "PDF + audio: link in bio", not "comment CHALISA"
posting: {jitter_minutes: 0}   # under make_com the slot time IS the schedule
optimizer: {slot_arm_enabled: false}   # slots are fixed by the Make schedule
===== PAGE 5 =====
Free plan limits to confirm on make.com/pricing: 1,000 credits/month, 2 active scenarios,
15-minute minimum interval for interval scheduling, 5-minute execution limit, and a
possible 5 MB file limit (one source reported it; confirm whether it applies to a reel
fetched by URL). Confirm that scheduling at fixed clock times (and several times per
scenario) works on free, and that the HTTP module is available on free.
Requirement: the Instagram account must be Professional and linked to a Facebook
Page for the Facebook-login connection.
Record everything in docs/API_NOTES.md with URLs and dates.
4.2 Worker endpoints for Make (relay/src/make_api.ts)
All under /api/make/*, auth Authorization: Bearer <MAKE_KEY> (a new random Worker
secret, stored in Make's HTTP module header; scoped to these routes only), rate-limited,
generic errors, constant-time compare, 404 elsewhere.
GET /api/make/next?slot=A|B: atomically claim the oldest due reel (scheduled_at <=
now + claim_window_minutes, status scheduled) using the existing claim_due_reel
function, set handed_off, and return JSON {empty:false, reel_id, video_url,
caption, first_comment, insight_media_id|null}. If nothing is due: the queue is
empty -> use a reserve reel if available; else return {empty:true}. A repeat call for an
already handed-off reel never returns it again. posting_enabled=false returns
{empty:true}.
POST /api/make/ack: {reel_id, status:"ok"|"error", ig_media_id, permalink,
message}. Idempotent. On ok: mark published, record ig_media_id, published_at,
trigger the YouTube step (as in v3). On error: mark failed_in_make, Telegram alert
with the message, and the planner re-queues a substitute.
POST /api/make/insights: {media_id, metrics:{...}} stores a snapshot in
relay_insights (store whatever metrics Make returns; null the rest).
GET /api/make/ping?test=1: returns a sample payload without claiming anything;
records make_last_call.
insight_media_id selection: the published reel with the oldest missing snapshot due
now (about 72 h, then about 7 d), or null.
Never auto-retry a handed-off reel. If no ack arrives within unacked_alert_minutes,
mark unknown and alert Telegram ("check Instagram and Make: reel X may or may not
be live"). This favours no duplicates over speed.
Dead-man switch: if no /next call arrives within deadman_minutes after a slot, alert
Telegram ("Make scenario not running: check connection/scenario status"). Make can
disable a scenario after repeated errors, or the Facebook connection can expire; this
alert is how I find out.
===== PAGE 6 =====
Credit meter: count /next hits to estimate monthly credits (runs x
credits_per_run_estimate), include it in the weekly report, alert at 80% of
credits_budget_monthly, and automatically disable the insights piggyback when above
90%.
Late/missed slots: the oldest due reel is served at the next run; anything older than
max_late_hours is rescheduled to the next free slot.
Keep buffer alerts, reserve reels and the 3-day/1-day/empty Telegram messages exactly
as in v3.
4.3 Make scenarios (what I will build; design to give me)
Two scenarios on the free plan (one per slot), or one scenario with two scheduled times if
Make supports that on free (check; record). Each scenario, in order:
1. Schedule: every day at the slot time, timezone Asia/Kolkata (verify the account/scenario
timezone setting).
2. HTTP, make a request: GET https://<worker>/api/make/next?slot=A with the bearer
header; parse response = yes.
3. Filter: empty is not true.
4. Instagram for Business, Create a reel post: video URL = video_url, caption =
caption (plus cover/share-to-feed options if the module has them).
5. Instagram for Business, Create a comment on the new media ID with first_comment
(optional; keep only if credits allow).
6. HTTP POST /api/make/ack with reel_id, ig_media_id, permalink (if returned),
status ok.
7. Router branch 2 (filter: insight_media_id exists): Get post insights for that ID, then
HTTP POST /api/make/insights.
8. Error handler on step 4: HTTP POST /api/make/ack with status error and the error
text.
Estimated credits per run: 4 core + 2 insights = about 6; at 2 runs/day that is about
360/month. Measure and update the estimate.
4.4 Your deliverables for the Make setup
Print a click-by-click guide (no screenshots needed) with exact module names, every
field mapping, the exact header and URL, and the schedule settings. Include the two
scenarios' names ("Chalisa Slot A/B") and the final "turn scenario ON" step.
If and only if you can verify exact module identifiers from official documentation or a real
exported blueprint, also offer an importable blueprint JSON. Never fabricate module IDs.
The guide is the primary path.
===== PAGE 7 =====
Provide a connectivity test for me: after I build the scenarios, I run each once; the
agent watches make_last_call and /ping hits for up to 30 minutes and confirms or
tells me what is wrong.
4.5 Feasibility tests (gate U6, run before declaring the route usable)
1. File size: standard profile reel via the Create a reel post module. If it errors on file size,
switch render.profile to lite5mb automatically: re-render the queue in 720x1280,
about 800 kbps video + 64 kbps audio, maximum 40 s and 4.8 MB, re-validate with
ffprobe and blackdetect/silencedetect, update captions/timings, and retest.
2. Scheduling: confirm fixed-time runs fire in IST on free. If only interval scheduling works,
set max_reels_per_day: 1, report why, and propose the best alternative.
3. HTTP module available on free: if not, switch the feed to a method that is (for example
Google Sheets/Drive modules reading an exported CSV), and update the design
accordingly, logging in DECISIONS.md.
4. Credits per run measured from Make's usage page (I will paste the number if you ask
once) or estimated from call counts.
5. Set max_reels_per_day from the result. Under free limits it is 2 unless a scenario can
hold several scheduled times.
4.6 Business Suite fallback (publish.backend: business_suite_manual)
If gate U6 fails, or Make later stops being viable, switch to this mode:
scripts/export_batch.py creates batches/YYYY-MM-DD/ with the MP4s, covers and a
schedule.csv (file, caption, first comment, IST date/time) plus a short checklist. A
Sunday Telegram message says "Upload this batch in Meta Business Suite and schedule
it" with the folder path. Reels count as published at their scheduled time. Analytics
piggyback is unavailable in this mode.
Verify what Business Suite currently allows for scheduling Reels (how far ahead) and
size the batch to it.
5. CHANGE C: CONTENT AND RENDER UPDATES
CTA/captions: replace "Comment CHALISA..." with "Free Chalisa PDF + audio: link in
bio" in captions, first comments and on-screen CTA. Regenerate caption/CTA fields for
scripts already queued but not yet handed off, using templates (no LLM call needed); do
not touch reels inside the 6-hour freeze window.
Render profile: add lite5mb as a first-class profile in render.py with its own
validation limits; standard stays default unless U6 forces lite5mb.
Planner: read publish.make.max_reels_per_day, set jitter_minutes to 0 for
===== PAGE 8 =====
make_com, snap reels to the configured Make slots, and cap auto-scaling at
max_reels_per_day. Disable the slot arm.
Queue migration for existing reels: reels already in relay_queue with old jitter times
are snapped to the nearest Make slot (keep order, keep day numbers, keep min gap).
Frozen ones (within 6 h) are left for the Graph API path only if that backend is still active;
otherwise snap them too.
6. CHANGE D: ENGAGEMENT AND ANALYTICS UNDER MAKE
Set engagement.enabled=false. Disable reply/DM/poll steps in the Worker when
backend != graph_api. Keep code and tests.
Remove "comment keyword" mentions from site pages and the PDF page copy; the link-
in-bio /chalisa page remains the lead magnet.
Insights: use the piggyback in 4.2. The optimizer's reward function must adapt to the
metrics actually received: if watch-time metrics are missing, reweight over reach/views,
likes, shares, saves. Log what the Make module returns in docs/API_NOTES.md.
Optimizer arms except slot still work; resolution is lower (one snapshot per reel), so
raise min_samples_per_arm to 12.
Weekly Telegram report: replace comment stats with credits used, handed-
off/acked/unknown counts and the last Make contact.
Optional: scripts/import_insights.py reads a CSV exported from Instagram/Business
Suite from data/insights_import/ to fill gaps.
7. SECRETS AND SECURITY UPDATES
Secret Location Change
Pixabay API key
(optional)
laptop OS keychain
only new
MAKE_KEY
Worker secret +
inside my Make
scenarios
new; rotate-able; scoped to /api/make/*
Instagram token
(KV), Meta App
ID/secret
Worker KV / secrets
retire after gate U9 (delete from KV and
wrangler secret delete); no longer
needed
Pexels key laptop keychain optional; remove if unused
===== PAGE 9 =====
everything else unchanged unchanged
Update secret_scan.py regexes: add the Pixabay key format (digits, hyphen, hex;
verify against my real key without printing it), the MAKE_KEY format you generate, and
keep the others.
Add log-masking tests for key= query strings and the Authorization header on
/api/make/*.
The Make bearer key sits inside Make (a third party). Treat it as low-privilege: it can only
claim the next due reel (one per 20 minutes at most), ack, and post insights. Rate limit
enforces this. RUNBOOK explains rotating it in both places.
After U9, tell me (in the final report) to optionally revoke the Meta developer app and the
Instagram token from my account settings.
8. HUMAN INPUTS FOR THIS UPGRADE (collect once, in one
message)
1. Pixabay API key (optional): create a free account at pixabay.com, open
pixabay.com/api/docs while logged in, copy the key shown. Leave blank to use the
keyless providers.
2. Make.com account (free, no card).
3. Facebook Page linked to my Instagram Professional account (Instagram app: Settings,
Account, Sharing to other apps / Linked accounts; verify current path and tell me).
4. After the agent prints the guide: build the Make scenarios, connect Instagram through
"Facebook login", set the schedule, turn them ON, run once.
5. Confirm the first run when the agent asks.
Store the Pixabay key straight into the OS keychain. Do not echo it back.
9. MIGRATIONS (additive, reversible)
relay_queue: add handed_off_at, acked_at, ack_status, make_run_note; extend
status enum with handed_off, failed_in_make, unknown.
relay_state: keys make_last_call, make_calls_month, make_credit_estimate.
Local reels: add backend, render_profile.
Provider tables or columns for asset provenance (provider, asset id, source URL,
license).
Backfill existing rows safely; down scripts restore the prior shape. Test up then down
then up on a copy of the real DB.
===== PAGE 10 =====
10. PHASES AND GATES
Phase Work Gate
U0 Audit, snapshot, rollbackdoc V4_AUDIT.md written; pre-v4 tag; backups exist;existing tests pass or failures documented
U1 Inputs Pixabay key (if given) validated with one live search;nothing printed
U2 Provider chain + Pixabay+ Wikimedia + fallbacks Tests in 2.5 pass; one reel renders with zero keys;one with Pixabay clips; logs contain no key
U3 Backend abstraction +config + migrations up/down/up migration test passes; flag switchingtested; Graph API path still passes its unit tests when
selected
U4 Make endpoints in theWorker Auth, claim atomicity (parallel callers), idempotentack, unacked -> unknown, dead-man alert, credit
meter, ping test all pass (Miniflare + staging)
U5
Content/render updates
(CTA, lite5mb, planner
snapping, queue
migration)
Queue re-snapped; lite5mb reel passes validation
under 4.8 MB; day numbers and ordering intact
U6 Make feasibility
Agent prints the guide; I build and run once; tests in
4.5 done; max_reels_per_day and render profile
set; or fallback to Business Suite documented
U7 Analytics piggyback +optimizer adaptation Insights reach the Worker from a real Make run (ordocumented as unavailable); optimizer tests passwith reduced metrics
U8 Site/PDF/copy updates No "comment CHALISA" text remains (grep proof);
pages deploy; secret scan clean
U9 Live proof
Three real posts published by Make with the laptop
daemon stopped; acks received; no duplicates;
YouTube step fired (if enabled)
U10 Retire Meta pieces
Meta secrets and KV token deleted; Worker no
longer references them under make_com; tests still
green; rollback doc updated
===== PAGE 11 =====
U11 Secret audit gitleaks over full history clean; log-masking fuzz
passes; wrangler secret list matches the table
in 7
U12 Handover Final report
11. TEST ADDITIONS (pytest + vitest)
Provider chain and key redaction; Pixabay caching/backoff; zero-key render; lite5mb
validator; planner slot snapping and cap; /api/make/* auth, rate limit, claim concurrency,
idempotent ack, unknown state, dead-man, credit meter thresholds, piggyback selection;
Business Suite exporter output; migration up/down; backend flag matrix (make_com,
business_suite_manual, graph_api dormant). Simulate offline: with the factory stopped
and a fake clock, Make-style calls at slot times drain the buffer correctly, alerts fire once,
reserves are used last.
12. ROLLBACK
docs/ROLLBACK_V4.md must allow me to return to v3 in minutes: git checkout pre-v4,
restore DB backups, redeploy the previous Worker version, re-enable the Graph API
backend (only possible if the Meta secrets were not yet retired; state clearly that after U10 a
rollback needs new Meta credentials).
13. DEFINITION OF DONE
All tests pass; secret audit clean; U0 to U12 evidence in docs/VERIFICATION.md.
Three real posts published by Make with the laptop daemon off; buffer at target; alerts
tested (low buffer, dead-man, unacked, credits).
Zero-key render proven; Pixabay clips used when a key exists.
Updated RUNBOOK.md: Make troubleshooting (scenario disabled, connection expired,
credits exhausted), rotating MAKE_KEY, switching backends, Business Suite weekly
routine.
Final report: what changed; evidence; remaining manual items (honestly: re-authorising
the Facebook connection in Make if it expires, and checking Telegram when alerts
arrive); lost features (auto-replies, keyword DMs, minute-exact timing, per-reel analytics
resolution); credit usage numbers; the next best upgrade if Make's free plan becomes
limiting.
14. PITFALLS (check proactively)
===== PAGE 12 =====
1. Free Make plan: 2 scenarios, credits, possible 5 MB file cap, 15-minute interval floor.
Measure, do not assume.
2. A Make scenario can be switched off after repeated errors; a Facebook connection can
expire. The dead-man alert is mandatory.
3. No auto-retry of handed-off reels (duplicate-post risk). Prefer unknown + alert.
4. Pixabay key appears in URLs; redact everywhere. Cache and download; never hotlink.
5. Make cannot be automated by you: do not attempt browser automation of Make or
Instagram. Give me the guide.
6. Slot times are now fixed; jitter is off; do not reintroduce randomness unless the Make
schedule is changed.
7. The caption CTA must not promise comment-triggered DMs anymore.
8. Cloudflare free limits still apply to every Worker change; keep ticks small.
15. WORK ORDER
Run U0 to U12 in order. After each phase append evidence to docs/VERIFICATION.md and
commit (secret scan must pass). Pause only at U6 for my Make setup and print exactly what
I must do. When finished, print the final report and stop.