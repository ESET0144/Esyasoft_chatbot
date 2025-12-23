import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

import nl2sql
from main import app
from db import DB_PATH, init_db


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    # Ensure DB and tables exist
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Insert a known revenue row for 11-12-2015
    cur.execute("DELETE FROM Revenue_data;")
    cur.execute("INSERT INTO Revenue_data (Datetime, Revenue) VALUES (?, ?);", ('11-12-2015 00:00', 100.0))
    conn.commit()
    conn.close()
    yield
    # cleanup
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM Revenue_data;")
    conn.commit()
    conn.close()


def test_planner_cannot_access_revenue(monkeypatch):
    client = TestClient(app)

    # Mock NL2SQL to return a revenue-selecting SQL
    def fake_nl2sql(question, schema):
        return ("SELECT substr(Datetime,7,4) || '-' || substr(Datetime,4,2) || '-' || substr(Datetime,1,2) AS date, "
                "SUM(Revenue) AS total_revenue, AVG(Revenue) AS avg_revenue FROM Revenue_data "
                "WHERE substr(Datetime,7,4) || '-' || substr(Datetime,4,2) || '-' || substr(Datetime,1,2) = '2015-12-11' GROUP BY date;")

    monkeypatch.setattr(nl2sql, 'natural_to_sql', fake_nl2sql)

    # Login as planner
    resp = client.post('/token', data={'username': 'planner', 'password': 'planner123'})
    assert resp.status_code == 200
    token = resp.json()['access_token']

    # Call /chat and expect 403 forbidden
    headers = {'Authorization': f'Bearer {token}'}
    r = client.post('/chat', json={'question': 'revenue on 11-12-2015'}, headers=headers)
    assert r.status_code == 403
    assert 'forbidden' in r.json().get('error', '').lower()


def test_admin_can_query_revenue(monkeypatch):
    client = TestClient(app)

    # Same NL2SQL mock
    def fake_nl2sql(question, schema):
        return ("SELECT substr(Datetime,7,4) || '-' || substr(Datetime,4,2) || '-' || substr(Datetime,1,2) AS date, "
                "SUM(Revenue) AS total_revenue, AVG(Revenue) AS avg_revenue FROM Revenue_data "
                "WHERE substr(Datetime,7,4) || '-' || substr(Datetime,4,2) || '-' || substr(Datetime,1,2) = '2015-12-11' GROUP BY date;")

    monkeypatch.setattr(nl2sql, 'natural_to_sql', fake_nl2sql)

    # Login as admin
    resp = client.post('/token', data={'username': 'admin', 'password': 'admin123'})
    assert resp.status_code == 200
    token = resp.json()['access_token']

    headers = {'Authorization': f'Bearer {token}'}
    r = client.post('/chat', json={'question': 'revenue on 11-12-2015'}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert 'generated_sql' in data
    assert 'result' in data
    # result should contain at least one row with totals
    assert len(data['result']) >= 1
