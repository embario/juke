# Juke Web Messaging UX Designs

## Context

These concepts are for the web app only. They assume the current Juke shell:

- persistent left sidebar navigation
- full-height content area inside `AppLayout`
- music-first visual language with deep blue panels and orange accents
- launch points from the sidebar, music profiles, and Juke World user modal

The goal is not just to place chat on the page, but to decide how messaging should behave inside Juke's existing product posture.

## Shared Product Rules

All three options assume the same underlying product behavior:

- `Messages` lives in the sidebar
- unread count appears in the sidebar and in the page-level inbox
- users can start a DM from profile and world surfaces
- users can create private group chats
- messages support text plus one track attachment in v1
- thread state updates in realtime
- mobile web collapses the experience into list and detail screens

## Option 1: Split Inbox Workspace

### Summary

This is the most direct and most productive design. Messaging gets a dedicated `/messages` route with a three-region workspace:

- left rail for inbox and filters
- center thread view
- right context panel for members, shared tracks, and conversation actions

This feels like "Juke as a music-social workstation" rather than a generic consumer messenger.

### Behavior

- Clicking `Messages` in the sidebar opens the inbox workspace.
- Clicking a conversation swaps the thread in-place instead of navigating away.
- The composer stays pinned at the bottom of the thread.
- Group info and track context live in the right panel, so users can inspect who is in the room and replay shared music without leaving the thread.
- New message events append inline with a subtle pulse, not a full-page toast.
- Opening a profile or world modal and clicking `Message` lands the user directly in the workspace with that thread selected.

### Desktop Wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ Sidebar         │ Inbox rail                     │ Thread                     │ Context panel │
│                 │                                │                            │               │
│ Library         │ [Search messages.....]         │ Neon Crate Society         │ 6 members     │
│ Music Profile   │ [All] [Unread] [Groups]        │ last active 2m ago         │ 14 shared     │
│ Juke World      │                                │                            │ tracks        │
│ Messages  12    │ > Ava                          │ Ava: drop the opener       │               │
│                 │   sent a track 2m              │                            │ Shared tracks │
│                 │ > Neon Crate Society           │ You: perfect, queueing it  │ [card]        │
│                 │   4 unread                     │                            │ [card]        │
│                 │ > Marco                        │ Marco shared "So What"     │ [card]        │
│                 │                                │ [track card]               │               │
│                 │                                │                            │ Members       │
│                 │                                │                            │ Ava           │
│                 │                                │                            │ Marco         │
│                 │                                │                            │ ...           │
│                 │                                │────────────────────────────│               │
│                 │                                │ [Type message...........]  │ [Mute] [Info] │
│                 │                                │ [Attach track] [Send]      │               │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Mobile Behavior

- `/messages` opens the inbox list first.
- Tapping a thread navigates to `/messages/:conversationId`.
- Thread header gets a back button and a compact info sheet for members/shared tracks.
- Composer stays sticky above the mobile browser chrome.

### Strengths

- Best for high-volume messaging and group chat.
- Best information density.
- Gives Juke room to make track-sharing feel first-class.
- Scales well from DM to groups.

### Risks

- More complex first implementation than a simpler two-pane chat.
- Right context panel can feel heavy if not tuned carefully.

### Best For

- Power users
- Music curation groups
- Desktop-first usage

## Option 2: Thread-First Social Canvas

### Summary

This design treats each conversation like a mini social scene. The thread is the hero, and everything else is secondary. The inbox becomes a slim collapsible column while the center area feels more editorial and immersive.

This is less "messenger app" and more "shared listening lounge."

### Behavior

- Entering `Messages` opens the last active thread by default.
- The inbox rail stays narrow and preview-light.
- Messages with track shares expand into larger album-style cards with play actions and richer metadata.
- System moments such as "Ava added Marco" or "3 people reacted to this track share" read like feed events instead of plain admin lines.
- The thread background can subtly shift hue based on the most recently shared track art or dominant conversation accent.

### Desktop Wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ Sidebar         │ Mini inbox        │ Conversation stage                                    │
│                 │                   │                                                       │
│ Messages   12   │ Ava         2m    │ Neon Crate Society                                   │
│                 │ Crate Soc   now   │ Tonight's warm-up mix                                │
│                 │ Marco       1h    │                                                       │
│                 │ Jules       3h    │ Ava                                                   │
│                 │                   │ this transition is filthy                             │
│                 │                   │                                                       │
│                 │                   │ ┌───────────────────────────────────────────────┐      │
│                 │                   │ │ Track share                                   │      │
│                 │                   │ │ "So What" • Miles Davis                       │      │
│                 │                   │ │ [Play preview] [Open track] [Queue]           │      │
│                 │                   │ └───────────────────────────────────────────────┘      │
│                 │                   │                                                       │
│                 │                   │ Marco                                                │
│                 │                   │ put this after the opener                            │
│                 │                   │                                                       │
│                 │                   │ [Composer......................................]      │
│                 │                   │ [Attach track]                             [Send]     │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Mobile Behavior

- Mobile opens directly into the last active thread.
- Inbox is a slide-over sheet from the left.
- Conversation info and member list are a top-right action sheet.

### Strengths

- Most distinctive visual identity.
- Makes music-sharing feel central instead of bolted on.
- Strong emotional feel for groups and recurring scenes.

### Risks

- Harder to scan many conversations quickly.
- Less operationally efficient for users managing multiple threads.
- More visual complexity to implement well.

### Best For

- Brand-forward product direction
- Social/music identity
- Lower-volume, higher-emotion conversations

## Option 3: Quick Message Drawer

### Summary

This is the lightest-weight design. Messaging behaves like a persistent drawer that can open over any page, with a full inbox route only when needed. It prioritizes low interruption and immediate access from anywhere in the product.

It feels closest to "Juke added messaging without changing the rest of the app."

### Behavior

- The sidebar `Messages` item opens a right-side drawer on desktop.
- Users can keep browsing Library, Profiles, or Juke World while messaging.
- Starting a DM from a profile or world card opens the drawer directly to that thread.
- A full-page `/messages` route exists for dedicated inbox management, but the drawer is the primary interaction.
- New message notifications appear as compact stackable chips above the playback bar.

### Desktop Wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ Main Juke page content                                               │ Messaging drawer     │
│                                                                      │                     │
│ Library / Profile / World stays visible                              │ [Search........]    │
│                                                                      │ Ava                 │
│                                                                      │ Crate Society       │
│                                                                      │ Marco               │
│                                                                      │──────────────────── │
│                                                                      │ Ava: got a closer?  │
│                                                                      │ You: maybe this     │
│                                                                      │ [track card]        │
│                                                                      │                     │
│                                                                      │ [Type.............] │
│                                                                      │ [Attach]     [Send] │
└────────────────────────────────────────────────────────────────────────┴─────────────────────┘
```

### Mobile Behavior

- Drawer becomes a full-screen sheet.
- Thread and inbox stack inside the sheet without changing the underlying page.

### Strengths

- Lowest interruption cost.
- Fastest path from "viewing a person" to "sending a message."
- Lets messaging coexist with browsing and playback naturally.

### Risks

- Group chat management is cramped in a drawer.
- Harder to support rich conversation context.
- Can feel like messaging is secondary, even if the feature matters strategically.

### Best For

- Lightweight DM behavior
- Frequent browse-and-message multitasking
- Fast initial rollout

## Comparison

| Dimension | Option 1: Split Inbox Workspace | Option 2: Thread-First Social Canvas | Option 3: Quick Message Drawer |
| --- | --- | --- | --- |
| Inbox scanning | Strong | Medium | Medium |
| Group chat support | Strong | Strong | Weak |
| Track-sharing expression | Strong | Strongest | Medium |
| Implementation complexity | Medium | High | Medium |
| Consistency with current shell | Strong | Medium | Strong |
| Feels most like Juke | Strong | Strongest | Medium |
| Best v1 path | Yes | No | Possible |

## Recommendation

Recommend **Option 1: Split Inbox Workspace** for v1.

It gives Juke the right balance of:

- operational clarity
- scalability from DMs to groups
- room for track-sharing to matter
- good fit with the existing sidebar-driven shell

It is also the safest path for shipping web first, then carrying the same mental model to Android and iOS.

## Suggested Detail Pass After Selection

Once one direction is chosen, the next design pass should lock:

- conversation list density and preview rules
- track card visual treatment
- unread badge behavior
- empty states for no threads and no search results
- mobile responsive behavior for thread navigation
- entry-point copy for profile and Juke World CTAs
