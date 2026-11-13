"""The healthy-traffic log templates now live in incidentiq/synthetic.py (the load-time log
scaler shares them); re-exported here so the generator code stays as it was."""

from incidentiq.synthetic import NOISE, SYMPTOM, UNIVERSAL

__all__ = ["NOISE", "SYMPTOM", "UNIVERSAL"]
