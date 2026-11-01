from __future__ import annotations

import json
from pathlib import Path

import pytest

from revoai_engine.knowledge import KnowledgeError, KnowledgeStore
from revoai_engine.knowledge.store import SCHEMA_VERSION
from revoai_engine.protocol import (
    InitializeParams,
    RpcRequest,
    METHOD_KNOWLEDGE_SEARCH,
    METHOD_KNOWLEDGE_STATS,
    METHOD_KNOWLEDGE_TRANSCRIPT_IMPORT,
)
from revoai_engine.service import EngineState, dispatch


def _store(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path / "knowledge")


def _add_source(store: KnowledgeStore, title: str = "Scan to BIM walls") -> dict:
    return store.add_transcript(
        title=title,
        transcript=(
            "Create walls from a point cloud. Set levels first, then place wall "
            "centrelines on the detected wall planes and check wall joins."
        ),
        url="https://example.test/scan-to-bim",
        creator="Test creator",
        license_text="Test licence",
    )


def test_knowledge_survives_restart_and_search_finds_snippets(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    first = KnowledgeStore(root)
    imported = first.add_transcript(
        title="Residential walls",
        transcript="Model walls from a point cloud and align them to levels.",
        url="https://example.test/residential",
    )
    assert imported["created"] is True
    assert imported["chunkCount"] >= 1

    reopened = KnowledgeStore(root)
    result = reopened.search(query="walls point cloud")

    assert result["snippets"], "Expected a transcript snippet in search results."
    assert result["snippets"][0]["sourceId"] == imported["sourceId"]
    assert result["snippets"][0]["url"] == "https://example.test/residential"
    assert "walls" in result["snippets"][0]["snippet"].lower()


def test_duplicate_import_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _add_source(store)
    second = _add_source(store)

    assert first["created"] is True
    assert second["created"] is False
    assert second["sourceId"] == first["sourceId"]
    assert store.stats()["sources"] == 1
    assert store.stats()["documents"] == 1


def test_approved_knowledge_is_retrieved_with_provenance(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = _add_source(store)
    record = store.add_technique(
        subject="Wall centrelines from scan planes",
        category="walls",
        description="Place native wall centrelines on detected wall planes.",
        source_type="youtube",
        source_ids=[source["sourceId"]],
        confidence=0.8,
        procedure=["Identify wall planes", "Create wall centreline", "Check joins"],
        api_operations=["Wall.Create"],
    )

    assert record["status"] == "pending_review"
    assert store.context(element_kinds=["wall"])["records"] == []

    approved = store.review(record_id=record["id"], action="approve", reviewer="reviewer")
    assert approved["status"] == "approved"
    assert approved["approvedBy"] == "reviewer"
    assert approved["provenance"][0]["sourceId"] == source["sourceId"]

    context = store.context(element_kinds=["wall"])
    assert len(context["records"]) == 1
    assert context["citations"][0]["recordId"] == record["id"]
    assert "Scan to BIM walls" in context["text"]

    rejected = store.review(record_id=record["id"], action="reject", note="Not verified")
    assert rejected["status"] == "rejected"
    assert store.context(element_kinds=["wall"])["records"] == []


def test_new_imports_do_not_overwrite_approved_knowledge(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = _add_source(store)
    record = store.add_technique(
        subject="Floor boundary from plane",
        category="floors",
        description="Use the ordered floor boundary as the floor sketch.",
        source_ids=[source["sourceId"]],
    )
    store.review(record_id=record["id"], action="approve", reviewer="reviewer")

    _add_source(store, title="Another video")
    store.add_technique(
        subject="Alternative floor boundary",
        category="floors",
        description="A second technique that has not been approved.",
        source_type="youtube",
    )

    preserved = store.get_record(record["id"])
    assert preserved["status"] == "approved"
    assert preserved["version"] == 1
    assert preserved["subject"] == "Floor boundary from plane"


def test_project_extraction_is_stored_with_elements(tmp_path: Path) -> None:
    store = _store(tmp_path)
    extraction = {
        "project": {
            "title": "Verified house",
            "path": "C:/models/house.rvt",
            "revitVersion": "2027",
            "revitBuild": "27.0.4.412",
            "units": {"length": "millimeters"},
            "extractedAt": "2026-11-01T00:00:00.000Z",
            "warnings": ["One room had no phase association."],
        },
        "counts": {"walls": 2, "floors": 1},
        "elements": [
            {
                "elementId": "101",
                "uniqueId": "uid-101",
                "category": "Walls",
                "family": "Basic Wall",
                "typeName": "Generic 200mm",
                "levelId": "Level 1",
                "hostId": None,
                "boundingBox": {"min": [0, 0, 0], "max": [5, 0.2, 2.7]},
                "parameters": [{"name": "Width", "value": "200"}],
                "geometry": {"solidCount": 1},
            },
            {
                "elementId": "102",
                "uniqueId": "uid-102",
                "category": "Floors",
                "typeName": "Generic 200mm",
                "levelId": "Level 1",
            },
            {
                "elementId": "103",
                "uniqueId": "uid-103",
                "category": "Doors",
                "family": "Single-Flush",
                "typeName": "0915 x 2134mm",
                "hostId": "101",
            },
        ],
    }

    imported = store.add_project_extraction(extraction)

    assert imported["created"] is True
    assert imported["elementCount"] == 3
    assert imported["warnings"] == ["One room had no phase association."]
    stats = store.stats()
    assert stats["projects"] == 1
    assert stats["projectElements"] == 3

    duplicate = store.add_project_extraction(extraction)
    assert duplicate["created"] is False
    assert duplicate["elementCount"] == 3

    reopened = KnowledgeStore(tmp_path / "knowledge")
    assert reopened.stats()["projectElements"] == 3


def test_update_and_delete_preserve_review_history(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = _add_source(store)
    record = store.add_technique(
        subject="Draft wall technique",
        category="walls",
        description="Draft description.",
        source_ids=[source["sourceId"]],
    )

    updated = store.update_record(
        record_id=record["id"],
        subject="Reviewed wall technique",
        description="Corrected description.",
        procedure=["Check the wall plane", "Create the centreline"],
        reviewer="editor",
    )
    assert updated["subject"] == "Reviewed wall technique"
    assert updated["procedure"] == ["Check the wall plane", "Create the centreline"]
    assert any(review["action"] == "update" for review in updated["reviews"])

    store.review(record_id=record["id"], action="approve", reviewer="reviewer")
    with pytest.raises(KnowledgeError):
        store.update_record(record_id=record["id"], description="Not allowed")

    deleted = store.delete_record(record_id=record["id"], reviewer="reviewer", note="Superseded")
    assert deleted["deleted"] is True
    assert store.stats()["records"] == 1  # the source-material record remains

    with pytest.raises(KnowledgeError):
        store.get_record(record["id"])
    assert all(item["id"] != record["id"] for item in store.search(query="wall")["records"])


def test_backup_verify_and_restore(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _add_source(store)

    backup = store.backup()
    verified = store.verify_backup(backup["path"])
    assert verified["valid"] is True
    assert verified["manifest"]["schemaVersion"] == SCHEMA_VERSION

    restored_root = tmp_path / "restored"
    restored = store.restore_backup(backup["path"], restored_root)
    assert Path(restored["path"]).is_file()

    reopened = KnowledgeStore(restored_root)
    assert reopened.stats()["sources"] == 1
    assert reopened.search(query="walls")["snippets"]


def test_export_contains_provenance(tmp_path: Path) -> None:
    store = _store(tmp_path)
    imported = _add_source(store)
    export = store.export()
    lines = Path(export["path"]).read_text(encoding="utf-8").splitlines()
    payloads = [json.loads(line) for line in lines]

    assert any(item["type"] == "sources" for item in payloads)
    assert any(item["type"] == "document_chunks" for item in payloads)
    assert any(item["type"] == "manifest" for item in payloads)
    assert imported["sourceId"] in Path(export["path"]).read_text(encoding="utf-8")


def test_knowledge_rpc_dispatch_uses_local_root(tmp_path: Path) -> None:
    state = EngineState()
    state.initialize(
        InitializeParams(
            client_name="pytest",
            client_version="0.7.0",
            protocol_version="1.0",
            knowledge_root=str(tmp_path / "knowledge"),
        )
    )

    response = dispatch(
        state,
        RpcRequest(
            id="1",
            method=METHOD_KNOWLEDGE_TRANSCRIPT_IMPORT,
            params={
                "title": "API walls",
                "transcript": "Wall.Create needs a curve, level and height.",
            },
        ),
    )
    assert response is not None and response.error is None

    search = dispatch(
        state,
        RpcRequest(
            id="2",
            method=METHOD_KNOWLEDGE_SEARCH,
            params={"query": "Wall.Create"},
        ),
    )
    assert search is not None and search.error is None
    assert search.result is not None

    stats = dispatch(
        state,
        RpcRequest(id="3", method=METHOD_KNOWLEDGE_STATS),
    )
    assert stats is not None and stats.result is not None
    assert stats.result["sources"] == 1
