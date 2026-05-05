from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from skoleintra.db.models import Child


@dataclass(frozen=True, slots=True)
class ArchivedChild:
    source_id: str
    display_name: str
    school_hostname: str
    is_present: bool


@dataclass(frozen=True, slots=True)
class ChildSnapshot:
    source_id: str
    display_name: str
    url_prefix: str | None = None


@dataclass(frozen=True, slots=True)
class ChildReconciliationResult:
    children: list[ArchivedChild]
    created: int
    renamed: int


@dataclass(frozen=True, slots=True)
class ArchivedGroup:
    source_id: str
    display_name: str
    school_hostname: str
    is_present: bool


@dataclass(frozen=True, slots=True)
class GroupSnapshot:
    source_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class GroupReconciliationResult:
    groups: list[ArchivedGroup]
    created: int
    renamed: int


def reconcile_children(
    *,
    school_hostname: str,
    archived: list[ArchivedChild],
    discovered: list[ChildSnapshot],
    scope_succeeded: bool,
) -> ChildReconciliationResult:
    by_source_id = {child.source_id: child for child in archived}
    discovered_source_ids = {child.source_id for child in discovered}
    renamed = 0
    created = 0
    reconciled: list[ArchivedChild] = []

    for child in discovered:
        existing = by_source_id.get(child.source_id)
        if existing is None:
            created += 1
            reconciled.append(
                ArchivedChild(
                    source_id=child.source_id,
                    display_name=child.display_name,
                    school_hostname=school_hostname,
                    is_present=True,
                )
            )
            continue

        if existing.display_name != child.display_name:
            renamed += 1

        reconciled.append(
            ArchivedChild(
                source_id=existing.source_id,
                display_name=child.display_name,
                school_hostname=existing.school_hostname,
                is_present=True,
            )
        )

    for child in archived:
        if child.source_id in discovered_source_ids:
            continue
        if scope_succeeded:
            reconciled.append(
                ArchivedChild(
                    source_id=child.source_id,
                    display_name=child.display_name,
                    school_hostname=child.school_hostname,
                    is_present=False,
                )
            )
        else:
            reconciled.append(child)

    return ChildReconciliationResult(
        children=reconciled,
        created=created,
        renamed=renamed,
    )


def reconcile_groups(
    *,
    school_hostname: str,
    archived: list[ArchivedGroup],
    discovered: list[GroupSnapshot],
    scope_succeeded: bool,
) -> GroupReconciliationResult:
    by_source_id = {group.source_id: group for group in archived}
    discovered_source_ids = {group.source_id for group in discovered}
    renamed = 0
    created = 0
    reconciled: list[ArchivedGroup] = []

    for group in discovered:
        existing = by_source_id.get(group.source_id)
        if existing is None:
            created += 1
            reconciled.append(
                ArchivedGroup(
                    source_id=group.source_id,
                    display_name=group.display_name,
                    school_hostname=school_hostname,
                    is_present=True,
                )
            )
            continue

        if existing.display_name != group.display_name:
            renamed += 1

        reconciled.append(
            ArchivedGroup(
                source_id=existing.source_id,
                display_name=group.display_name,
                school_hostname=existing.school_hostname,
                is_present=True,
            )
        )

    for group in archived:
        if group.source_id in discovered_source_ids:
            continue
        if scope_succeeded:
            reconciled.append(
                ArchivedGroup(
                    source_id=group.source_id,
                    display_name=group.display_name,
                    school_hostname=group.school_hostname,
                    is_present=False,
                )
            )
        else:
            reconciled.append(group)

    return GroupReconciliationResult(
        groups=reconciled,
        created=created,
        renamed=renamed,
    )


def sync_child_scope(
    session: Session,
    *,
    school_hostname: str,
    discovered: list[ChildSnapshot],
    scope_succeeded: bool,
) -> list[Child]:
    existing = list(
        session.execute(
            select(Child).where(Child.school_hostname == school_hostname)
        ).scalars()
    )
    by_source_id = {
        child.source_id: child for child in existing if child.source_id is not None
    }
    legacy_by_name = {
        child.name: child for child in existing if child.source_id is None
    }

    synced: list[Child] = []
    seen_child_ids: set[int] = set()

    for snapshot in discovered:
        child = by_source_id.get(snapshot.source_id)
        if child is None:
            child = legacy_by_name.get(snapshot.display_name)

        if child is None:
            child = Child(
                source_id=snapshot.source_id,
                name=snapshot.display_name,
                school_hostname=school_hostname,
                is_present=True,
            )
            session.add(child)
        else:
            child.source_id = snapshot.source_id
            child.name = snapshot.display_name
            child.is_present = True

        synced.append(child)
        if child.id is not None:
            seen_child_ids.add(child.id)

    session.flush()
    seen_child_ids.update(child.id for child in synced if child.id is not None)

    if scope_succeeded:
        for child in existing:
            if child.id not in seen_child_ids:
                child.is_present = False

    return synced
