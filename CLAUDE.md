# fabric-wt-harness

A Python WebTransport client and server that test the Godot H3/WT implementation in
`fabric-godot-core` by swapping roles.

`README.md` gives the design. `CITATION.cff` says what this is built on; add a reference there
when you add a dependency here.

## It must not become the Godot implementation's twin

The value of this repository is that it was written from the specification and not from the
other end. So:

- Do NOT copy framing, constants or field offsets out of `modules/http3`. If both ends read the
  same source, they agree by construction and the test proves nothing.
- Do NOT relax a check here to make a Godot test pass. A disagreement is the finding. Fix the
  side that is wrong, and if the specification is ambiguous, say which reading each end took.
- Do NOT depend on the engine, a Godot build, or `fabric-godot-core` being checked out. This
  must run on its own against anything that speaks WebTransport, including a browser.

## Two modes, not three

H3/WT gives exactly two: reliable-sequenced on bidi streams, and unreliable-unsequenced on
datagrams. Anything else — unreliable-ordered in particular — is built at the endpoint, so it is
a claim the endpoint makes and this is what checks the claim.

Do NOT assume a datagram arrived in order. If a test needs ordering, it must carry its own
sequence and say so.

## Certificates

`verify_mode = CERT_NONE` against a local test server, and that is deliberate: the Godot demo
server builds a fresh self-signed certificate per run, so there is no chain and no stable hash.

Do NOT extend that to anything reachable off this machine. A harness that skips verification by
habit is one somebody eventually points at a deployment.

## Running it

```sh
pip install -r requirements.txt
python roster_client.py --port 54370 --clients 2
```

Exit code is the test result: zero when every client got a session.
