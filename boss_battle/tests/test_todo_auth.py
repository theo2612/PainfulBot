"""Regression test for the /todo/control authorization bypass that allowed any
unauthenticated WebSocket client to invoke cmd_save_rundown and rewrite the
live rundown (reported by CypherEnigma/MadameFabulous, 2026-05-24).

Run from the boss_battle/ directory:
    .venv/bin/python -m pytest tests/test_todo_auth.py -v
or as a plain script:
    .venv/bin/python tests/test_todo_auth.py
"""

import os
import sys

# Configure a CF Access verifier before importing server so the prod-mode
# auth path is exercised. Values are fake — verify() will reject anything
# without a real JWT, which is exactly what we want to test.
os.environ.setdefault('CF_ACCESS_TEAM_DOMAIN', 'testteam.cloudflareaccess.com')
os.environ.setdefault('CF_ACCESS_AUD', 'aud-for-tests')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


def _connect_as_attacker():
    """Open a /todo socket connection as if coming through Cloudflare with no
    JWT. The Cf-Connecting-Ip header is what flips the server out of the
    localhost-dev allow path."""
    return server.socketio.test_client(
        server.app,
        namespace='/todo',
        headers={
            'Cf-Ray': 'test-ray-id',
            'Cf-Connecting-Ip': '198.51.100.42',
        },
    )


def _connect_as_localhost():
    """No CF headers — simulates direct localhost dev access, which is allowed."""
    return server.socketio.test_client(server.app, namespace='/todo')


def test_unauthenticated_cmd_save_rundown_is_rejected():
    # Seed with a known rundown.
    with server.todo_lock:
        server.todo_state['show_title'] = 'Original Show'
        server.todo_state['items'] = [
            {
                'id': 'intro', 'label': 'INTRO', 'sublabel': '',
                'duration': 60, 'remaining': 60,
                'color': '#E8A020', 'status': 'pending',
            },
        ]
    baseline_title = server.todo_state['show_title']
    baseline_label = server.todo_state['items'][0]['label']

    client = _connect_as_attacker()
    assert client.is_connected('/todo'), 'attacker connect should succeed (public namespace)'

    # The attacker's SID must NOT have landed in the authorized set.
    assert not server._todo_authorized, \
        f'attacker SID was authorized — {server._todo_authorized}'

    # Fire the privileged event. Before the fix this would have rewritten state.
    client.emit('cmd_save_rundown', {
        'show_title': 'PWNED',
        'items': [{
            'id': 'intro',
            'label': 'Just Do It',
            'sublabel': '',
            'duration': 60,
            'color': 'red; font-size: 48px;',
        }],
    }, namespace='/todo')

    # State must be unchanged.
    assert server.todo_state['show_title'] == baseline_title, \
        f'show_title was mutated by unauthorized client: {server.todo_state["show_title"]!r}'
    assert server.todo_state['items'][0]['label'] == baseline_label, \
        f'item label was mutated by unauthorized client: {server.todo_state["items"][0]["label"]!r}'

    # And the server must have surfaced an auth_error to the attacker.
    received = client.get_received('/todo')
    auth_errors = [m for m in received if m['name'] == 'auth_error']
    assert auth_errors, f'expected auth_error to attacker, got events: {[m["name"] for m in received]}'

    client.disconnect(namespace='/todo')


def test_color_injection_is_rejected_for_authorized_operator():
    """Even when the operator IS authorized, a malicious `color` payload must
    not be persisted — defends against the CSS injection vector in case any
    operator's session is hijacked or compromised."""
    with server.todo_lock:
        server.todo_state['show_title'] = 'PainfulIT Live'
        server.todo_state['items'] = [
            {
                'id': 'intro', 'label': 'INTRO', 'sublabel': '',
                'duration': 60, 'remaining': 60,
                'color': '#E8A020', 'status': 'pending',
            },
        ]

    client = _connect_as_localhost()  # auto-authorized in dev mode
    assert client.is_connected('/todo')
    assert server._todo_authorized, 'localhost dev connection should be authorized'

    client.emit('cmd_save_rundown', {
        'show_title': 'PainfulIT Live',
        'items': [{
            'id': 'intro',
            'label': 'INTRO',
            'sublabel': '',
            'duration': 60,
            'color': 'red; font-size: 48px; text-shadow: 0 0 10px red',
        }],
    }, namespace='/todo')

    stored = server.todo_state['items'][0]['color']
    assert stored == server.DEFAULT_TODO_COLOR, \
        f'CSS injection in color field was persisted: {stored!r}'

    client.disconnect(namespace='/todo')


if __name__ == '__main__':
    failures = 0
    for fn in (test_unauthenticated_cmd_save_rundown_is_rejected,
               test_color_injection_is_rejected_for_authorized_operator):
        try:
            fn()
            print(f'PASS  {fn.__name__}')
        except AssertionError as e:
            failures += 1
            print(f'FAIL  {fn.__name__}: {e}')
    sys.exit(1 if failures else 0)
