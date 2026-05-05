# Skoleintra

Skoleintra syncs parent-facing school and daycare information out of ForaeldreIntra so the parent can read it without logging into the portal.

## Language

**Child**:
A child whose school or daycare information is visible in the parent's portal.
_Avoid_: User, account

**Group**:
A class, room, or daycare group that shared content may belong to.
_Avoid_: Child, membership label

**Message**:
A sent communication in the portal that does not change after delivery.
_Avoid_: Item, thread

**Photo album**:
A collection of photos published for a child that may gain new photos over time.
_Avoid_: Item, attachment list

**Week plan**:
A plan for one **Child** for one calendar week that may be revised after first publication.
_Avoid_: Item, schedule blob

**Week-plan revision**:
A meaningful published update to an existing **Week plan**.
_Avoid_: Diff blob, scrape event

## Relationships

- A **Child** can have many **Messages**
- A **Child** can have many **Photo albums**
- A **Child** can have many **Week plans**
- A **Child** can belong to one or more **Groups**
- A **Group** can have many **Children**
- A **Photo album** contains one or more photos
- A **Child** has at most one **Week plan** per calendar week
- A **Week plan** can belong to a **Group** and be visible through multiple **Children**
- A **Week plan** can have many **Week-plan revisions**

## Example dialogue

> **Dev:** "If a **Week plan** changes after we first sync it, should we treat that as a new **Week plan**?"
> **Domain expert:** "No — it is still the same **Week plan**, but an updated version of it."

## Flagged ambiguities

- "item" is a storage abstraction, not a domain term — when discussing product behavior, say **Message**, **Photo album**, or **Week plan** instead.
- A renamed **Group** is still the same **Group** — name changes do not create a new group.
