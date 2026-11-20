"""Softphone simulator page availability."""

from __future__ import annotations


async def test_softphone_page_is_served(client):
    response = await client.get("/softphone")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Softphone Simulator" in response.text
    assert "text_utterance" in response.text
    assert "audio_chunk" in response.text
    assert "barge_in" in response.text
    assert "pending-outbound" in response.text
    assert "Ring for new outbound calls" in response.text


async def test_softphone_page_does_not_embed_groq_key(client):
    response = await client.get("/softphone")

    assert response.status_code == 200
    assert "gsk_" not in response.text
