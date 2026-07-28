from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.app.routers import pdf


class MetadataServerHelperTests(unittest.TestCase):
    def test_usa_endpoint_fijo_header_y_timeout(self) -> None:
        response = MagicMock()
        response.read.return_value = b"service@example.iam.gserviceaccount.com\n"
        opener = MagicMock()
        opener.__enter__.return_value = response

        with patch.object(pdf.urllib.request, "urlopen", return_value=opener) as urlopen:
            result = pdf._get_metadata_service_account_email()

        self.assertEqual(result, "service@example.iam.gserviceaccount.com")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, pdf._METADATA_SERVICE_ACCOUNT_EMAIL_URL)
        self.assertEqual(dict(request.header_items()), {"Metadata-flavor": "Google"})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], pdf._METADATA_TIMEOUT_SECONDS)

    def test_fallo_del_metadata_server_no_impide_retorno_de_credenciales(self) -> None:
        with patch.object(pdf.urllib.request, "urlopen", side_effect=OSError("unavailable")):
            self.assertIsNone(pdf._get_metadata_service_account_email())


if __name__ == "__main__":
    unittest.main()
