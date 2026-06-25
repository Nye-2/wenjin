from src.agents.harness.contracts import AcademicACIObservation, AcademicACIPermissionCheck


def test_academic_aci_observation_is_bounded_and_structured() -> None:
    observation = AcademicACIObservation(
        tool="sandbox.run_python",
        status="ok",
        summary="Generated metrics from panel.csv.",
        evidence_refs=("dataset:/workspace/datasets/panel.csv",),
        artifact_refs=("artifact:/workspace/outputs/metrics/result.json",),
        output_refs=("harness-output-ref:exec/node/stdout",),
        warnings=("stdout externalized",),
        provenance={
            "execution_id": "exec-1",
            "node_id": "node-1",
            "workspace_id": "ws-1",
        },
    )

    payload = observation.to_payload()

    assert payload["schema"] == "wenjin.academic_aci.observation.v1"
    assert payload["tool"] == "sandbox.run_python"
    assert payload["status"] == "ok"
    assert payload["artifact_refs"] == ["artifact:/workspace/outputs/metrics/result.json"]
    assert payload["output_refs"] == ["harness-output-ref:exec/node/stdout"]


def test_academic_aci_permission_check_uses_allow_ask_deny() -> None:
    check = AcademicACIPermissionCheck(
        tool="sandbox.generate_figure",
        decision="ask",
        reason="image provider call requires explicit policy permission",
        required_permissions=("sandbox.generate_figure",),
    )

    assert check.to_payload() == {
        "schema": "wenjin.academic_aci.permission_check.v1",
        "tool": "sandbox.generate_figure",
        "decision": "ask",
        "reason": "image provider call requires explicit policy permission",
        "required_permissions": ["sandbox.generate_figure"],
    }
