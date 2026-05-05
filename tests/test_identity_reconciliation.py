from skoleintra.db.identity import (
    ArchivedChild,
    ArchivedGroup,
    ChildSnapshot,
    GroupSnapshot,
    reconcile_children,
    reconcile_groups,
)


def test_reconcile_children_updates_name_for_existing_source_id():
    archived = [
        ArchivedChild(
            source_id="5798",
            display_name="Iben",
            school_hostname="school.example",
            is_present=True,
        )
    ]

    discovered = [
        ChildSnapshot(
            source_id="5798",
            display_name="Iben 0A",
        )
    ]

    result = reconcile_children(
        school_hostname="school.example",
        archived=archived,
        discovered=discovered,
        scope_succeeded=True,
    )

    assert len(result.children) == 1
    assert result.children[0].source_id == "5798"
    assert result.children[0].display_name == "Iben 0A"
    assert result.created == 0
    assert result.renamed == 1


def test_reconcile_children_marks_missing_child_gone_after_successful_scope():
    archived = [
        ArchivedChild(
            source_id="5798",
            display_name="Iben",
            school_hostname="school.example",
            is_present=True,
        )
    ]

    result = reconcile_children(
        school_hostname="school.example",
        archived=archived,
        discovered=[],
        scope_succeeded=True,
    )

    assert len(result.children) == 1
    assert result.children[0].source_id == "5798"
    assert result.children[0].is_present is False


def test_reconcile_children_restores_present_child_on_reappearance():
    archived = [
        ArchivedChild(
            source_id="5798",
            display_name="Iben",
            school_hostname="school.example",
            is_present=False,
        )
    ]

    discovered = [
        ChildSnapshot(
            source_id="5798",
            display_name="Iben",
        )
    ]

    result = reconcile_children(
        school_hostname="school.example",
        archived=archived,
        discovered=discovered,
        scope_succeeded=True,
    )

    assert len(result.children) == 1
    assert result.children[0].source_id == "5798"
    assert result.children[0].is_present is True
    assert result.created == 0


def test_reconcile_groups_updates_name_for_existing_source_id():
    archived = [
        ArchivedGroup(
            source_id="valmue",
            display_name="VALMUESTUE",
            school_hostname="school.example",
            is_present=True,
        )
    ]

    discovered = [
        GroupSnapshot(
            source_id="valmue",
            display_name="Valmuestuen",
        )
    ]

    result = reconcile_groups(
        school_hostname="school.example",
        archived=archived,
        discovered=discovered,
        scope_succeeded=True,
    )

    assert len(result.groups) == 1
    assert result.groups[0].source_id == "valmue"
    assert result.groups[0].display_name == "Valmuestuen"
    assert result.created == 0
    assert result.renamed == 1


def test_reconcile_groups_marks_missing_group_gone_after_successful_scope():
    archived = [
        ArchivedGroup(
            source_id="valmue",
            display_name="VALMUESTUE",
            school_hostname="school.example",
            is_present=True,
        )
    ]

    result = reconcile_groups(
        school_hostname="school.example",
        archived=archived,
        discovered=[],
        scope_succeeded=True,
    )

    assert len(result.groups) == 1
    assert result.groups[0].source_id == "valmue"
    assert result.groups[0].is_present is False
