# Architecture Notes

## Source of Truth

GetCourse: courses, payments, installments, course access, login/password issuance, student cabinet, temporary manual work with leads.

FunnelHub server: persistent lead database, Telegram/VK subscribers, future Max subscribers, email subscribers, communication history, funnel state, inbox, imports, broadcasts, analytics.

## Target Flow

```text
GetCourse form
-> GetCourse creates/updates user and issues login/password
-> GetCourse calls FunnelHub webhook
-> FunnelHub stores/updates lead and generates bot-start token
-> User redirects to thank-you / bot choice page
-> Telegram/VK bot links messenger account to lead
-> FunnelHub controls bot/email communication
```

## Non-Negotiable Constraint

Deleting a non-buyer from GetCourse must not remove the ability to communicate with that person from FunnelHub, provided the person is still subscribed and legally allowed to receive messages.
