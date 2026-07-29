from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from backend.app.routers import pdf


def run(coro):
    return asyncio.run(coro)


def test_create_loose_batch_writes_manifest_before_any_upload():
    bucket = MagicMock()
    client = MagicMock()
    client.bucket.return_value = bucket
    payload = pdf.LooseBatchCreatePayload(files=[
        pdf.LooseBatchFile(filename="uno.xml", size=10),
        pdf.LooseBatchFile(filename="dos.xml", size=20),
    ])

    with patch.object(pdf.storage, "Client", return_value=client):
        result = run(pdf.create_loose_pdf_batch(payload))

    assert result["batchId"]
    assert [job["filename"] for job in result["jobs"]] == ["uno.xml", "dos.xml"]
    assert bucket.blob.return_value.upload_from_string.call_count == 2


def test_create_loose_batch_rejects_500_files():
    payload = pdf.LooseBatchCreatePayload(files=[
        pdf.LooseBatchFile(filename=f"{i}.xml", size=1) for i in range(500)
    ])
    try:
        run(pdf.create_loose_pdf_batch(payload))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "ZIP" in str(exc.detail)
    else:
        raise AssertionError("500 XML sueltos deben requerir ZIP")


def test_loose_batch_upload_requires_manifest_membership():
    bucket = MagicMock()
    with patch.object(pdf.batch_state_store, "load_manifest", new=AsyncMock(return_value={"other": "uno.xml"})):
        try:
            run(pdf._validate_loose_batch_member(bucket, "123e4567-e89b-12d3-a456-426614174000", "job", "uno.xml"))
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("un job ajeno no debe poder subir a la cola")


def test_reconcile_marks_missing_xml_as_awaiting_upload():
    bucket = MagicMock()
    pdf_blob = MagicMock()
    xml_blob = MagicMock()
    pdf_blob.exists.return_value = False
    xml_blob.exists.return_value = False
    bucket.blob.side_effect = lambda path: pdf_blob if path.startswith("pdfs/") else xml_blob
    statuses = {"job-1": None}

    run(pdf.batch_state_store.reconcile_none_statuses_with_gcs(bucket, ["job-1"], statuses))

    assert statuses["job-1"] == "awaiting_upload"
