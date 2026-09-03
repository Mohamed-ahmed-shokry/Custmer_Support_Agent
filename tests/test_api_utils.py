from app.api_utils import extract_error_detail


class FakeResponse:
    def __init__(self, payload=None, text="", json_error=None):
        self._payload = payload
        self.text = text
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


def test_extract_error_detail_uses_fastapi_detail():
    response = FakeResponse(
        payload={"detail": "Document was not found."}, text='{"detail":"Document was not found."}'
    )

    assert extract_error_detail(response) == "Document was not found."


def test_extract_error_detail_formats_validation_messages():
    response = FakeResponse(
        payload={"detail": [{"msg": "Input should be greater than 0"}, {"msg": "Field required"}]},
        text="validation failed",
    )

    assert extract_error_detail(response) == "Input should be greater than 0; Field required"


def test_extract_error_detail_falls_back_to_response_text_for_non_json():
    response = FakeResponse(text="Gateway timeout", json_error=ValueError("not json"))

    assert extract_error_detail(response) == "Gateway timeout"
