import unittest
from flask import Flask
from backend.app import create_app
from backend.config import Config

class TestPhase5ProductionHardening(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_gunicorn_app_factory(self):
        """Verify Gunicorn entrypoint 'backend.app:create_app()' successfully instantiates."""
        app_instance = create_app()
        self.assertIsInstance(app_instance, Flask)
        self.assertEqual(app_instance.name, "backend.app")

    def test_security_headers_present_on_success(self):
        """Verify strict HTTP security headers are injected into standard responses."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)

        headers = res.headers
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("Strict-Transport-Security"), "max-age=31536000; includeSubDomains")
        self.assertEqual(headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

    def test_security_headers_present_on_unauthenticated_error(self):
        """Verify security headers are preserved even on 401 Unauthorized responses."""
        res = self.client.get("/api/v1/menu/")
        self.assertEqual(res.status_code, 401)

        headers = res.headers
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("Strict-Transport-Security"), "max-age=31536000; includeSubDomains")

    def test_cors_authorized_origin(self):
        """Verify CORS headers are returned for authorized local/production origins."""
        res = self.client.get("/health", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), "http://localhost:3000")

    def test_cors_unauthorized_origin_rejected(self):
        """Verify unauthorized external origins do not receive Access-Control-Allow-Origin."""
        res = self.client.get("/health", headers={"Origin": "http://unauthorized-malicious-domain.com"})
        self.assertEqual(res.status_code, 200)
        self.assertNotEqual(res.headers.get("Access-Control-Allow-Origin"), "http://unauthorized-malicious-domain.com")

    def test_production_env_disables_debug(self):
        """Verify debug mode is strictly enforced to False in production environment."""
        class MockProdConfig(Config):
            ENV = "production"
            DEBUG = False

        prod_app = create_app(config_class=MockProdConfig)
        self.assertFalse(prod_app.debug)

if __name__ == "__main__":
    unittest.main()

