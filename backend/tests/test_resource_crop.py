from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services.resource_service import build_cropped_image, centered_crop_box


client = TestClient(app)


@pytest.mark.parametrize(
    ("width", "height", "ratio", "expected"),
    [
        (1600, 1200, "16:9", (0, 150, 1600, 1050)),
        (1200, 1600, "1:1", (0, 200, 1200, 1400)),
        (1200, 1600, "9:16", (150, 0, 1050, 1600)),
        (2100, 900, "21:9", (0, 0, 2100, 900)),
    ],
)
def test_centered_crop_box(width: int, height: int, ratio: str, expected: tuple[int, int, int, int]) -> None:
    assert centered_crop_box(width, height, ratio) == expected


def test_centered_crop_box_rejects_unknown_ratio() -> None:
    with pytest.raises(ValueError, match="不支持的图片比例"):
        centered_crop_box(100, 100, "5:4")


def test_build_cropped_image_keeps_png_and_expected_dimensions() -> None:
    source = BytesIO()
    Image.new("RGBA", (800, 600), (255, 0, 0, 128)).save(source, format="PNG")
    source.seek(0)

    data, width, height, extension, mime, box = build_cropped_image(source, "9:16")

    assert (width, height) == (338, 600)
    assert box == (231, 0, 569, 600)
    assert extension == ".png"
    assert mime == "image/png"
    with Image.open(BytesIO(data)) as cropped:
        assert cropped.size == (338, 600)
        assert cropped.mode == "RGBA"


def test_batch_crop_api_creates_new_resource_and_keeps_source() -> None:
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    source = BytesIO()
    Image.new("RGB", (640, 480), (10, 20, 30)).save(source, format="JPEG")
    uploaded = client.post(
        "/api/v1/resources",
        params={"media_type": "image", "direction": "input"},
        files={"file": ("crop-source.jpg", source.getvalue(), "image/jpeg")},
        headers=headers,
    )
    assert uploaded.status_code == 201
    source_resource = uploaded.json()

    response = client.post(
        "/api/v1/resources/batch-crop",
        json={"resource_ids": [source_resource["id"]], "aspect_ratio": "16:9"},
        headers=headers,
    )

    assert response.status_code == 200
    result = response.json()
    assert result["failed"] == []
    assert len(result["created"]) == 1
    cropped = result["created"][0]
    assert cropped["id"] != source_resource["id"]
    assert (cropped["width"], cropped["height"]) == (640, 360)
    assert cropped["folder_id"] == source_resource["folder_id"]
    assert client.get(f"/api/v1/resources/{source_resource['id']}", headers=headers).status_code == 200
