# fabric-wt-harness

The second opinion. A Python WebTransport client and server, used to test the Godot H3/WT
implementation in `fabric-godot-core` by swapping roles.

## Why it is not in the engine

A Godot client talking to a Godot server agrees with itself. Any assumption both ends get wrong
— a frame the spec does not have, a close message never sent, a session id read from the wrong
place — passes every test the pair can run and then fails against a browser. So one end has to
be an implementation that was written from the specification instead of from the other end, and
that is what aioquic is here.

Keeping it out of the engine fork is the same argument one level up. Vendored into
`modules/http3/demo`, this would be versioned with the engine and rebased through every
assembly, and the one thing it must not do is move when the engine moves.

## The two roles

```sh
# Godot serves, Python connects.
godot --headless --script modules/http3/demo/wt_server_demo.gd    # in fabric-godot-core
python roster_client.py --port 54370 --clients 2

# Python serves, Godot connects.        (not written yet — see below)
python echo_server.py --port 54370
godot --headless --script modules/http3/demo/wt_client_test.gd
```

## What `roster_client.py` is for

The part a single connection cannot show.

`WebTransportPeer` tracked its clients in one bool until August 2026, so everything worked with
one client and the second was invisible: `peer_connected` was never emitted at all, and
`disconnect_peer` closed the whole server. None of that is reachable with one session in the
room, which is why it survived so long.

So this opens several, staggered, and holds them open:

- two sessions live at once, with distinguishable joins
- the server dropping one must reach only that client
- the other must still be connected afterwards

## Certificates

`verify_mode = CERT_NONE`. The Godot demo server builds a fresh self-signed P-256 certificate on
every run, so there is no chain to check and no stable hash to pin — pinning one would mean
editing this file every time the server restarted. It talks to localhost, on a port it was told,
for a test.

A deployment is a different question and is not this repository's.

## Not written yet

- `echo_server.py`, the Python end of the other role. `wt_client_test.gd` currently expects an
  external `webtransportd`, so the Godot-as-client direction depends on a binary that is not
  in the workspace.
- Unreliable-ordered. H3/WT has exactly two modes — reliable-sequenced on streams and
  unreliable-unsequenced on datagrams — so a third is the endpoint's to build, and there is
  nothing here yet that would catch it being claimed and not delivered.
