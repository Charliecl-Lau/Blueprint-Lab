def test_unknown_run_and_condition_return_404(client):
    assert client.get("/runs/999999").status_code == 404
    assert client.post("/runs/999999/retry").status_code == 404
    assert client.post("/conditions/999999/runs", json={}).status_code == 404
