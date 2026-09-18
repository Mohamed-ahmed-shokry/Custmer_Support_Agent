"""A minimal fake Streamlit that records calls and returns canned values.

Covers only the attributes the client modules use so tests can exercise
`app/` wiring without a real Streamlit runtime.
"""

from __future__ import annotations


class Call:
    __slots__ = ("channel", "fn", "args", "kwargs")

    def __init__(self, channel, fn, args, kwargs):
        self.channel = channel
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def __repr__(self):  # pragma: no cover - debug aid
        return f"Call({self.channel!r}, {self.fn!r}, {self.args!r}, {self.kwargs!r})"


class FakeSessionState(dict):
    """dict that also supports attribute-style access like streamlit's."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        del self[name]


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Placeholder:
    def __init__(self, recorder, channel):
        self._recorder = recorder
        self._channel = channel

    def markdown(self, content):
        self._recorder._call(self._channel, "markdown", content)


class FakeStreamlit:
    """Records every call and returns configured values by key."""

    def __init__(self, values=None, buttons=None, chat_input=None, uploads=None):
        self.values = values or {}
        self.buttons = buttons or {}
        self._chat_input_value = chat_input
        self.uploads = uploads
        self.session_state = FakeSessionState()
        self.calls = []
        self.errors = []
        self.toasts = []
        self.successes = []
        self.reruns = 0
        self.sidebar = _Side(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def _call(self, channel, fn, *args, **kwargs):
        self.calls.append(Call(channel, fn, args, kwargs))
        return kwargs.get("key") if fn == "feedback" else None

    # --- simple recorders -------------------------------------------------
    def error(self, message):
        self.errors.append(message)

    def success(self, message):
        self.successes.append(message)

    def toast(self, message):
        self.toasts.append(message)

    def caption(self, *args, **kwargs):
        self.calls.append(Call("st", "caption", args, kwargs))

    def subheader(self, *args, **kwargs):
        self.calls.append(Call("st", "subheader", args, kwargs))

    def code(self, *args, **kwargs):
        self.calls.append(Call("st", "code", args, kwargs))

    def markdown(self, content):
        self.calls.append(Call("st", "markdown", (content,), {}))

    def write(self, *args, **kwargs):
        self.calls.append(Call("st", "write", args, kwargs))

    def text(self, *args, **kwargs):
        self.calls.append(Call("st", "text", args, kwargs))

    def header(self, text):
        self.calls.append(Call("st", "header", (text,), {}))

    def metric(self, label, value, delta=None):
        self.calls.append(Call("st", "metric", (label, value, delta), {}))

    def set_page_config(self, **kwargs):
        self.calls.append(Call("st", "set_page_config", (), kwargs))

    def title(self, text):
        self.calls.append(Call("st", "title", (text,), {}))

    def rerun(self):
        self.reruns += 1

    # --- value-returning widgets ------------------------------------------
    def button(self, label, key=None):
        self.calls.append(Call("st", "button", (label,), {"key": key}))
        if key and key in self.buttons:
            return self.buttons[key]
        return self.buttons.get(label, False)

    def checkbox(self, label, value=False, key=None):
        self.calls.append(Call("st", "checkbox", (label,), {"value": value, "key": key}))
        return self.values.get(key, value)

    def selectbox(self, label, options=None, index=0, format_func=None, key=None):
        self.calls.append(
            Call(
                "st",
                "selectbox",
                (label,),
                {"options": options, "format_func": format_func, "index": index, "key": key},
            )
        )
        if key in self.values:
            return self.values[key]
        return options[index] if options else None

    def multiselect(self, label, options=None, default=None, format_func=None, key=None):
        self.calls.append(
            Call(
                "st",
                "multiselect",
                (label,),
                {"options": options, "format_func": format_func, "default": default, "key": key},
            )
        )
        if key in self.values:
            return self.values[key]
        return list(default) if default else []

    def text_input(self, label, value="", max_chars=None, key=None, placeholder=None):
        self.calls.append(
            Call(
                "st", "text_input", (label,),
                {"value": value, "max_chars": max_chars, "key": key, "placeholder": placeholder},
            )
        )
        return self.values.get(key, value)

    def chat_input(self, placeholder):
        self.calls.append(Call("st", "chat_input", (placeholder,), {}))
        return self._chat_input_value

    def feedback(self, kind, key=None):
        self.calls.append(Call("st", "feedback", (kind,), {"key": key}))
        return self.values.get(key)

    def file_uploader(self, label, type=None, accept_multiple_files=False):
        self.calls.append(
            Call(
                "st", "file_uploader", (label,),
                {"type": type, "accept_multiple_files": accept_multiple_files},
            )
        )
        return self.uploads

    def download_button(self, label, data, file_name=None, mime=None, key=None):
        self.calls.append(
            Call(
                "st",
                "download_button",
                (label,),
                {"data": data, "file_name": file_name, "mime": mime, "key": key},
            )
        )
        return True

    # --- context managers --------------------------------------------------
    def spinner(self, text):
        self.calls.append(Call("st", "spinner", (text,), {}))
        return _NullContext()

    def expander(self, label):
        self.calls.append(Call("st", "expander", (label,), {}))
        return self

    def chat_message(self, role):
        self.calls.append(Call("st", "chat_message", (role,), {}))
        return self

    def columns(self, count):
        self.calls.append(Call("st", "columns", (count,), {}))
        return [self for _ in range(count)]

    def empty(self):
        self.calls.append(Call("st", "empty", (), {}))
        return _Placeholder(self, "placeholder")


class _Side:
    def __init__(self, app):
        self._app = app

    def __getattr__(self, name):
        def proxy(*args, **kwargs):
            method = getattr(self._app, name)
            return method(*args, **kwargs)

        return proxy
