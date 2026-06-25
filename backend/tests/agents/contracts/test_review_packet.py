from src.agents.contracts.task_report import ReviewPacket, ReviewPacketItem, TaskReport


def test_review_packet_item_carries_provenance_and_default_checked() -> None:
    item = ReviewPacketItem(
        item_id="item-1",
        kind="document",
        title="文献定位与创新点.md",
        summary="主题矩阵、gap 和可引用论断。",
        preview={"format": "markdown", "excerpt": "# 文献定位"},
        source={"expert_id": "literature_synthesizer.v1", "node_id": "node-1"},
        claim_refs=["claim-1"],
        evidence_refs=["library:paper-1"],
        quality_surfaces=["citation_strength"],
        risk={"level": "medium", "reasons": ["1 条引用需要人工确认"]},
        default_checked=True,
        can_commit=True,
        provenance={"execution_id": "exec-1"},
    )

    payload = item.model_dump()

    assert payload["schema_version"] == "wenjin.review_packet.item.v1"
    assert payload["kind"] == "document"
    assert payload["default_checked"] is True
    assert payload["can_commit"] is True
    assert payload["risk"]["level"] == "medium"


def test_task_report_can_embed_review_packet() -> None:
    packet = ReviewPacket(
        packet_id="packet-1",
        execution_id="exec-1",
        capability_id="sci_literature_positioning",
        title="文献定位与创新点",
        summary="生成 1 个文档候选。",
        completion_status="complete",
        items=[],
    )
    report = TaskReport(
        execution_id="exec-1",
        capability_id="sci_literature_positioning",
        status="completed",
        duration_seconds=2,
        narrative="完成。",
        review_packet=packet,
    )

    assert report.review_packet is not None
    assert report.review_packet.packet_id == "packet-1"
