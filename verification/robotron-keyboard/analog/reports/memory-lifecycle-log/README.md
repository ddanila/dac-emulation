# Compact metadata through memory destruction and reconstruction

The unchanged generated C logger replays retained scope metadata, object references and memory metadata through four native destruction/reconstruction cycles at one address. All 30 frames reconstruct exactly, including removal and fresh monotonic identities. This is serialized evidence replay, not a new HDL execution, complete graph teardown or operational board qualification.

Each of the three streams has ten frames: nine full and one reuse. Dense evidence is 5558 bytes and compact evidence is 5654 bytes. These are fixture measurements, not operational bounds. Four tests check full replay, stale reuse separately in each stream, an omitted reference stream and changed logger source. Native lifecycle evidence and built logger source are retained with identities.
