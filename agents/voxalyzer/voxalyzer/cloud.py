"""Helpers of the on-demand deployment (modal_app.py): the server posts an mp3 to a web endpoint and gets the analysis back as JSON.

Kept free of the web framework and of Modal so they can be tested without either. The access control is Modal's proxy auth.
"""
import os
from tempfile import NamedTemporaryFile

MAX_UPLOAD_BYTES = 1 << 30


def analyze_bytes(data: bytes, session) -> dict:
    """Analyzes the content of an mp3 with an open session (voxalyzer.analyzer.begin_session) and returns the result as plain JSON types."""
    if not data:
        raise ValueError("Empty upload")
    from voxalyzer.agent import to_response
    from voxalyzer.analyzer import analyze_file

    with NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp.write(data)
    try:
        analysis = analyze_file(tmp.name, session_handler=session, force=True)
    finally:
        os.remove(tmp.name)
    if analysis is None:
        raise OSError("The analysis produced no result")
    return to_response(analysis)
