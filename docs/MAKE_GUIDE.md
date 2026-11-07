# Make.com Setup Guide (Chalisa Relay)

1. Create free Make.com account (no card).
2. Create Scenario "Chalisa Slot A":
   - Schedule: every day 06:30 Asia/Kolkata.
   - Module HTTP "Make a request": GET https://<worker>/api/make/next?slot=A
     Headers: Authorization: Bearer <MAKE_KEY>
     Parse response: yes.
   - Filter: empty is not true.
   - Instagram for Business "Create a reel post": Video URL = video_url, Caption = caption, Share to feed = yes.
   - Instagram for Business "Create a comment": Media ID = returned ig_media_id, Message = first_comment (optional).
   - HTTP POST https://<worker>/api/make/ack body JSON {reel_id, status:"ok", ig_media_id, permalink}.
   - Router branch 2 (if insight_media_id exists): Get post insights -> HTTP POST /api/make/insights.
   - Error handler on reel post: HTTP POST /api/make/ack with status:"error" and message.
3. Duplicate as "Chalisa Slot B" with schedule 19:00 IST.
4. Turn both scenarios ON.
5. Run each once manually.

Worker URL and MAKE_KEY will be provided after deploy.