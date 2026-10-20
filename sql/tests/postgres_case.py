import subprocess
import time
import unittest
import uuid


class PostgresCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = "openlangford-sql-test-" + uuid.uuid4().hex[:10]
        subprocess.run([
            "docker", "run", "-d", "--rm", "--name", cls.container,
            "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:17-alpine",
        ], check=True, capture_output=True)
        cls.addClassCleanup(lambda: subprocess.run(
            ["docker", "rm", "-f", cls.container], check=True, capture_output=True))
        for _ in range(50):
            if subprocess.run(["docker", "exec", cls.container, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                              capture_output=True).returncode == 0:
                return
            time.sleep(0.2)
        raise RuntimeError("Disposable PostgreSQL did not become ready")

    def sql(self, query, success=True):
        result = subprocess.run([
            "docker", "exec", "-i", self.container, "psql", "-h", "127.0.0.1", "-U", "postgres",
            "-v", "ON_ERROR_STOP=1", "-At",
        ], input=query, text=True, capture_output=True, timeout=20)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result.stdout.strip(), result.stderr

