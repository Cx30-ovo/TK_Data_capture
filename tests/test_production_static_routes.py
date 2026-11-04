"""Check the production static mounts without starting application tasks."""
import importlib.util
from pathlib import Path

import httpx
import pytest


@pytest.mark.asyncio
async def test_production_frontend_assets_are_served_without_lifespan(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'api/main.py'
    api = tmp_path / 'api'
    api.mkdir()
    main = api / 'main.py'
    main.write_bytes(source.read_bytes())
    static = api / 'webui'
    expected = {
        '/': ('index.html', b'<html>frontend</html>'),
        '/assets/app.js': ('assets/app.js', b'export const app = 1'),
        '/logos/platform.svg': ('logos/platform.svg', b'<svg/>'),
        '/spatial/favicon.svg': ('spatial/favicon.svg', b'<svg>icon</svg>'),
        '/spatial/starfield.png': ('spatial/starfield.png', b'background'),
        '/daily.html': ('daily.html', b'<html>daily</html>'),
        '/static/daily.css': ('daily.css', b'body { margin: 0 }'),
    }
    for relative, body in expected.values():
        path = static / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    spec = importlib.util.spec_from_file_location('api._static_release_test', main)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://test') as client:
        for url, (_, body) in expected.items():
            response = await client.get(url)
            assert response.status_code == 200, url
            assert response.content == body, url
        assert (await client.get('/spatial/nonexistent.png')).status_code == 404
