import os
import subprocess
import sys

VALID_SECRET = "production-test-7Gv!F1q@9xZ#2pL$8mN%5rT&3yU*6kW-4cE_1sQ+0aB=9dH"


def run_production_settings(
    overrides: dict[str, str | None],
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "POSTGRES_DB": "visio_test",
            "POSTGRES_USER": "visio_test",
            "POSTGRES_PASSWORD": "visio_test_password",
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": "5432",
            "POSTGRES_SSLMODE": "require",
        }
    )
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value

    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from django.conf import settings; print(settings.DEBUG)",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_production_settings_fail_without_secret_key() -> None:
    result = run_production_settings(
        {
            "DJANGO_SECRET_KEY": None,
            "DJANGO_ALLOWED_HOSTS": "api.example.invalid",
        }
    )

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_production_settings_fail_without_allowed_hosts() -> None:
    result = run_production_settings(
        {
            "DJANGO_SECRET_KEY": VALID_SECRET,
            "DJANGO_ALLOWED_HOSTS": None,
        }
    )

    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr


def test_production_settings_reject_wildcard_allowed_hosts() -> None:
    result = run_production_settings(
        {
            "DJANGO_SECRET_KEY": VALID_SECRET,
            "DJANGO_ALLOWED_HOSTS": "*",
        }
    )

    assert result.returncode != 0
    assert "Wildcard DJANGO_ALLOWED_HOSTS" in result.stderr


def test_production_settings_reject_plaintext_database_transport() -> None:
    result = run_production_settings(
        {
            "DJANGO_SECRET_KEY": VALID_SECRET,
            "DJANGO_ALLOWED_HOSTS": "api.example.invalid",
            "POSTGRES_SSLMODE": "disable",
        }
    )

    assert result.returncode != 0
    assert "POSTGRES_SSLMODE" in result.stderr


def test_production_settings_reject_insecure_csrf_origin() -> None:
    result = run_production_settings(
        {
            "DJANGO_SECRET_KEY": VALID_SECRET,
            "DJANGO_ALLOWED_HOSTS": "api.example.invalid",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "http://api.example.invalid",
        }
    )

    assert result.returncode != 0
    assert "DJANGO_CSRF_TRUSTED_ORIGINS" in result.stderr


def test_production_settings_reject_disabled_ssl_redirect() -> None:
    result = run_production_settings(
        {
            "DJANGO_SECRET_KEY": VALID_SECRET,
            "DJANGO_ALLOWED_HOSTS": "api.example.invalid",
            "DJANGO_SECURE_SSL_REDIRECT": "0",
        }
    )

    assert result.returncode != 0
    assert "DJANGO_SECURE_SSL_REDIRECT" in result.stderr


def test_production_settings_boot_with_complete_nonsecret_test_environment() -> None:
    result = run_production_settings(
        {
            "DJANGO_SECRET_KEY": VALID_SECRET,
            "DJANGO_ALLOWED_HOSTS": "api.example.invalid",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://api.example.invalid",
        }
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
