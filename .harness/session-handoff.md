# Session Handoff

## Current Status
- Manual Broadcasts backend has been implemented (Broadcast and BroadcastTarget models, API, and runner).
- The frontend (Inbox app) was updated.
- Found and fixed several issues with tests related to the channel field in FunnelState. All 125 tests passed successfully.
- Code has been pushed to GitHub (main branch) and is currently being deployed to production via deploy_files.py.

## Next Steps
- Validate manual broadcasts functionality on the production server once deploy is complete.
- Verify Inbox UI visually shows "Рассылки" (Broadcasts).
- Wait for user feedback on whether everything works perfectly on production.

## Notes
- To create a manual broadcast, the unnel-worker will pick up pending broadcasts and run roadcast_runner.py to send messages via the correct channel.
