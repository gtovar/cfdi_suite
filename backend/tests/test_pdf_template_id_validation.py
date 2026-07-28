"""Los IDs de plantilla que viajan al pipeline PDF nunca pueden formar paths."""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from google.api_core.exceptions import AlreadyExists, ServiceUnavailable

from backend.app.routers import pdf as pdf_router
from backend.app.services import task_dispatcher
from backend.app.services.template_ids import is_valid_template_id


def _run(coro):
    return asyncio.run(coro)


class TemplateIdRuleTests(unittest.TestCase):
    def test_rechaza_rutas_y_url_encoding(self) -> None:
        for template_id in ("../default", "default/extra", "/tmp/default", "%2e%2e%2fdefault"):
            with self.subTest(template_id=template_id):
                self.assertFalse(is_valid_template_id(template_id))

    def test_acepta_id_custom_aun_sin_archivo(self) -> None:
        template_id = "cliente_acme-2026"
        self.assertTrue(is_valid_template_id(template_id))


class PdfTemplateIdBoundaryTests(unittest.TestCase):
    def test_form_data_rechaza_id_inseguro_antes_de_encolar(self) -> None:
        with self.assertRaises(HTTPException) as error:
            pdf_router._template_id_from_form(json.dumps({"_id": "../default"}))
        self.assertEqual(error.exception.status_code, 400)

    def test_json_payload_rechaza_barras_y_ruta_absoluta(self) -> None:
        for template_id in ("default/extra", "/tmp/default"):
            with self.subTest(template_id=template_id):
                with self.assertRaises(HTTPException) as error:
                    _run(pdf_router.start_pdf_zip_gcs_generation(
                        pdf_router.ProcessGcsZipPayload(
                            gcsPath="uploads/123e4567-e89b-12d3-a456-426614174000.zip",
                            template=json.dumps({"_id": template_id}),
                        )
                    ))
                self.assertEqual(error.exception.status_code, 400)

    def test_form_data_preserva_id_custom_valido_inexistente(self) -> None:
        self.assertEqual(
            pdf_router._template_id_from_form(json.dumps({"_id": "cliente_acme-2026"})),
            "cliente_acme-2026",
        )

    def test_cloud_task_pdf_rechaza_antes_de_cargar_xml(self) -> None:
        payload = pdf_router.GeneratePdfPayload(
            job_id="job-test", xml_b64="", template_id="%2e%2e%2fdefault"
        )
        with (
            patch.object(pdf_router, "verify_cloud_tasks", return_value=True),
            patch.object(pdf_router.batch_state_store, "mark_job_converting", new=AsyncMock()) as mark_converting,
            patch.object(pdf_router.storage, "Client") as storage_client,
        ):
            with self.assertRaises(HTTPException) as error:
                _run(pdf_router.internal_generate_pdf(payload, MagicMock()))

        self.assertEqual(error.exception.status_code, 400)
        mark_converting.assert_not_awaited()
        storage_client.assert_not_called()

    def test_cloud_task_extract_rechaza_antes_de_cargar_zip(self) -> None:
        payload = pdf_router.ExtractZipPayload(
            gcs_path="uploads/123e4567-e89b-12d3-a456-426614174000.zip",
            batch_id="batch-test",
            template_id="../default",
        )
        with (
            patch.object(pdf_router, "verify_cloud_tasks", return_value=True),
            patch.object(pdf_router, "process_zip_in_background", new=AsyncMock()) as process_zip,
        ):
            with self.assertRaises(HTTPException) as error:
                _run(pdf_router.internal_extract_zip(payload, MagicMock()))

        self.assertEqual(error.exception.status_code, 400)
        process_zip.assert_not_awaited()

    def test_dispatcher_rechaza_antes_de_crear_cloud_task(self) -> None:
        with patch.object(task_dispatcher, "get_tasks_client") as get_client:
            with self.assertRaises(ValueError):
                task_dispatcher.enqueue_pdf_generation("job-test", "", "../default")
        get_client.assert_not_called()

    def test_dispatcher_encola_id_custom_valido_sin_exigir_archivo(self) -> None:
        client = MagicMock()
        client.queue_path.return_value = "queues/pdf-generator"
        client.create_task.return_value.name = "tasks/custom-template"
        with patch.object(task_dispatcher, "get_tasks_client", return_value=client):
            result = task_dispatcher.enqueue_pdf_generation("job-test", "", "cliente_acme-2026")

        self.assertEqual(result, "tasks/custom-template")
        payload = json.loads(client.create_task.call_args.kwargs["request"]["task"]["http_request"]["body"])
        self.assertEqual(payload["template_id"], "cliente_acme-2026")

    def test_dispatcher_reintenta_timeout_con_tarea_idempotente(self) -> None:
        client = MagicMock()
        client.queue_path.return_value = "queues/pdf-generator"
        client.task_path.return_value = "queues/pdf-generator/tasks/pdf-job-test"
        response = MagicMock()
        response.name = "queues/pdf-generator/tasks/pdf-job-test"
        client.create_task.side_effect = [ServiceUnavailable("temporal"), response]
        with (
            patch.object(task_dispatcher, "get_tasks_client", return_value=client),
            patch("backend.app.services.task_dispatcher.time.sleep") as sleep,
        ):
            result = task_dispatcher.enqueue_pdf_generation("job-test", "", "default")

        self.assertEqual(result, "queues/pdf-generator/tasks/pdf-job-test")
        self.assertEqual(client.create_task.call_count, 2)
        self.assertEqual(sleep.call_count, 1)
        task = client.create_task.call_args.kwargs["request"]["task"]
        self.assertEqual(task["name"], "queues/pdf-generator/tasks/pdf-job-test")

    def test_dispatcher_acepta_tarea_ya_creada_como_exito(self) -> None:
        client = MagicMock()
        client.queue_path.return_value = "queues/pdf-generator"
        client.task_path.return_value = "queues/pdf-generator/tasks/pdf-job-test"
        client.create_task.side_effect = AlreadyExists("ya existe")
        with patch.object(task_dispatcher, "get_tasks_client", return_value=client):
            result = task_dispatcher.enqueue_pdf_generation("job-test", "", "default")
        self.assertEqual(result, "queues/pdf-generator/tasks/pdf-job-test")

    def test_dispatcher_distingue_resultado_incierto_tras_reintentos(self) -> None:
        client = MagicMock()
        client.queue_path.return_value = "queues/pdf-generator"
        client.task_path.return_value = "queues/pdf-generator/tasks/pdf-job-test"
        client.create_task.side_effect = ServiceUnavailable("temporal")
        with (
            patch.object(task_dispatcher, "get_tasks_client", return_value=client),
            patch("backend.app.services.task_dispatcher.time.sleep"),
            self.assertRaises(task_dispatcher.TaskEnqueueUncertainError),
        ):
            task_dispatcher.enqueue_pdf_generation("job-test", "", "default")
        self.assertEqual(client.create_task.call_count, 3)
