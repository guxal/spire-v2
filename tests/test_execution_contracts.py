from spire.execution import ChangeKind, ChangeSpec, ExecutionMode, ExecutionRun, ExecutionRunState


def test_change_spec_and_run_are_hashed_immutable():
    spec = ChangeSpec(
        spec_id="spec_1",
        customer_id="1234567890",
        account_id="1234567890",
        kind=ChangeKind.UPDATE_BUDGET,
        target={"campaign_id": "101"},
        requested_change={"daily_budget": "55601"},
        snapshot_ref={"snapshot_id": "snapshot_extract_1", "content_hash": "sha256:snapshot"},
        provenance={"producer": "test"},
    )
    assert spec.content_hash.startswith("sha256:")
    assert spec.target["campaign_id"] == "101"
    run = ExecutionRun(
        run_id="run_1",
        spec_id=spec.spec_id,
        customer_id=spec.customer_id,
        account_id=spec.account_id,
        mode=ExecutionMode.PRODUCTION,
        state=ExecutionRunState.DRAFT,
        spec_hash=spec.content_hash,
        snapshot_ref=spec.snapshot_ref,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    assert run.content_hash.startswith("sha256:")
    assert run.state is ExecutionRunState.DRAFT


def test_change_spec_rejects_authority_and_technical_fields():
    try:
        ChangeSpec(
            spec_id="spec_1",
            customer_id="1234567890",
            account_id="1234567890",
            kind=ChangeKind.UPDATE_BUDGET,
            target={"campaign_id": "101"},
            requested_change={"daily_budget": "1", "approval": "yes"},
            snapshot_ref={},
        )
    except ValueError as exc:
        assert str(exc) == "CHANGE_SPEC_AUTHORITY_OR_TECHNICAL_FIELD_FORBIDDEN"
    else:
        raise AssertionError("authority fields must not enter ChangeSpec")
