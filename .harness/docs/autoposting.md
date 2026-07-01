# Autoposting And Follow-Up Posts

## Goal

Autoposting must support two separate product flows:

1. Public publishing to external content platforms.
2. Internal follow-up posts sent through FunnelHub bots after a lead completes the 18-day funnel.

These flows should not be mixed in one runtime model because they have different recipients,
delivery guarantees, history, duplicate rules, and API constraints.

Marked public content can still feed the follow-up flow. If a public autopost contains the
configured follow-up hashtag/marker, FunnelHub should create a separate `FunnelFollowupPost`
copy for internal bot delivery. The public publication and the private follow-up delivery must
keep separate statuses, histories, retries, and duplicate keys.

## Current State

The MVP already has public autoposting infrastructure:

- `autoposts` stores a queued/scheduled post.
- `autopost_publications` stores one publication row per selected public channel.
- The worker publishes due posts.
- Telegram channel posting and VK wall posting are implemented.
- Duplicate protection exists through `autoposts.dedupe_key` and unique
  `(autopost_id, channel)` publication rows.

The current production scope implements:

- Telegram channel publishing.
- VK wall publishing.
- VK image attachments for public VK posts, using temporary local storage until publish/cancel.
- Internal follow-up delivery to leads after day 18.
- Durable per-lead follow-up queues for leads who finish the main funnel after a follow-up post is
  created.
- Immediate follow-up mode for urgent posts to completed-funnel leads without changing the
  recipient's personal queued-post cadence.
- Editing and deletion of follow-up posts that have not started sending.
- Automatic routing from a marked public autopost into an internal follow-up post.

The current production scope does not implement:

- External source pulling from VK/Telegram/YouTube into FunnelHub.

## Decision: Two Separate Entities

Use separate entities for the two flows:

### 1. PublicAutopost

Purpose: publish one prepared post to public external platforms.

Public channels:

- Telegram channel.
- VK group wall.

Media behavior:

- Public Autoposting may attach one JPEG/PNG/WebP image.
- Images are used only for VK publications.
- Telegram remains text-only because the product decision is to avoid separate Telegram
  photo/text messages when long post text cannot fit as a photo caption.
- Uploaded image files are temporary: keep them in the shared app/worker upload volume while the
  post is pending or retryable, then delete after all selected publication rows publish or after
  cancellation.

Excluded for now:

- Odnoklassniki, because the API/app approval flow adds too much operational overhead for the
  current scope.
- Zen, because the manual Telegram-Zen bot transfer is handled outside FunnelHub.
- YouTube, because community-post publishing is not available through the standard public API for
  this use case.
- VK Video, because it is video publishing, not text/content post publishing.
- YouTube video upload, because it is a separate video-publishing feature.

Public publishing history should be tracked per platform:

- platform/channel;
- status;
- attempted_at;
- published_at;
- external_post_id;
- external_post_url;
- error;
- raw provider response.

Duplicate protection:

- one public post must not publish twice to the same platform;
- source/imported posts must have a stable provider-based dedupe key when applicable.

Provider notes:

- Telegram and VK are implemented.
- Odnoklassniki, Zen, and YouTube are intentionally out of scope.

### 2. FunnelFollowupPost

Purpose: send content to leads in private messages through FunnelHub bots after the main
18-day scenario is completed.

This is not public platform publishing. It is a segmented bot broadcast.

Delivery channels:

- Telegram bot.
- VK bot.

Recipient rule:

- lead has completed the main messenger funnel, currently `aisu_consultation`;
- matching `funnel_states.status = completed`;
- `funnel_states.completed_at is not null`;
- lead has an active subscribed `messenger_identities` row for Telegram and/or VK;
- unsubscribed identities are skipped.

If a lead is subscribed to both Telegram and VK:

- default behavior should be to send to both channels;
- this can later become configurable, for example "both", "last active", or "preferred channel".

Queue behavior:

- queued follow-up posts are durable database rows, not Redis-only/in-memory jobs;
- recipients who already completed the main funnel get delivery rows when the post is created;
- recipients who have not completed the main funnel yet get rows created when their funnel state
  transitions to completed;
- for queued mode, the first accumulated post is scheduled for the day after funnel completion;
- additional accumulated posts are scheduled one per day per lead/channel while the queue has
  pending items;
- the UI-selected `scheduled_at` time controls the send time of day;
- a lead subscribed to both Telegram and VK receives separate delivery rows for both selected
  channels.

Immediate mode:

- immediate follow-up posts are for urgent/private announcements to leads who already completed
  the main funnel;
- immediate posts use the UI-selected scheduled time, including "now" when no future time is set;
- immediate posts do not reserve or shift the recipient's queued follow-up cadence.

Editing and deletion:

- a follow-up post can be edited or deleted only while none of its delivery rows has started
  sending;
- "started" means any delivery with status other than `pending`, or with `attempted_at`/`sent_at`
  set;
- editing rebuilds pending delivery rows from the updated title/body/channels/time/mode;
- after sending starts, API mutations are rejected with conflict status and the UI hides
  edit/delete actions.

Follow-up delivery history should be tracked per lead and channel:

- followup_post_id;
- lead_id;
- channel;
- messenger_identity_id if available;
- status;
- attempted_at;
- sent_at;
- message_id;
- external_message_id;
- error.

Duplicate protection:

- one follow-up post must not be sent twice to the same `lead_id + channel`;
- retries should only retry failed/pending delivery rows, not already sent rows.
- a follow-up created from a public autopost must store a source link/reference to the public
  autopost and use a stable dedupe key so the same marked public post cannot create duplicate
  follow-up posts.

Hashtag/marker behavior:

- public autopost creation/publishing detects the configured follow-up marker in the post body;
- the default marker is `#aisukam` through `AUTOPOST_FOLLOWUP_MARKER`;
- when the marker is present, create or reuse the matching `FunnelFollowupPost`;
- the default behavior is to strip the marker from the private follow-up message through
  `AUTOPOST_FOLLOWUP_STRIP_MARKER=true`;
- the marker must not make the public autopost and private follow-up share delivery rows.

## Admin UI

The Inbox/admin interface should show two separate workspaces:

1. Public autoposting.
   - Create post.
   - Select public platforms.
   - Schedule publication.
   - View per-platform history.

2. Follow-up posts after day 18.
   - Create private bot post.
   - Select delivery channels: Telegram, VK, or both.
   - Schedule send.
   - Select queued or immediate mode.
   - Preview recipient count.
   - View per-lead delivery history.
   - Edit/delete posts that are still fully pending.

The UI should make it visually clear whether the post is public or private bot delivery.

## Worker Flow

The worker should process these independently:

1. Public autopost runner:
   - find due public posts;
   - publish to selected external platforms;
   - update per-platform publication history.

2. Funnel follow-up runner:
   - find due follow-up deliveries;
   - send through Telegram/VK bot adapters;
   - update per-lead delivery history.
   - never resend already sent delivery rows.

## Implemented Slices

- Public Autoposting MVP: Telegram channel and VK group wall.
- Follow-up post model, API, worker, and Inbox tab.
- Hashtag/marker routing from marked public autoposts into follow-up posts.
- Durable follow-up queue backfill when a lead completes the main funnel.
- Immediate follow-up mode.
- Pending follow-up edit/delete.

## Open Questions

- Should follow-up posts include buttons/links, and should those buttons support per-lead
  tracking links?
