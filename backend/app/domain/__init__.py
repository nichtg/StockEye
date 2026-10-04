"""Pure analysis logic. No I/O, no clock reads, no network, no database.

Shared input convention for every function here: price history is a ``pandas.DataFrame``
with a strictly increasing, timezone-naive ``DatetimeIndex`` (session dates for daily bars)
and float columns ``open``, ``high``, ``low``, ``close``, ``volume``. Every row is a
*completed* bar. Callers drop any in-progress bar before calling in.

Functions never look at rows after the row they are evaluating, unless the name says
so explicitly (``forward_returns``).
"""
