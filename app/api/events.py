"""The event contract is internal to the transactional outbox, not an HTTP feed.

OrderAccepted envelopes are persisted with orders and consumed by the worker;
there is intentionally no public event route in this assignment.
"""
