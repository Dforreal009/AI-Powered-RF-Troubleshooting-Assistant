# AI-Powered-RF-Troubleshooting-Assistant
SJSU CMPE 295A/295B project developing an AI-powered assistant for RF measurement analysis and troubleshooting.

## LitePoint SCPI experiments

The safe, dependency-free collector identifies the tester, runs read-only
queries, and can reproduce one non-RF parser error while logging JSONL:

```powershell
python tools/litepoint_scpi.py identify
python tools/litepoint_scpi.py --output data/scpi_events.jsonl reproduce-command-error
```

See [docs/litepoint_scpi_research.md](docs/litepoint_scpi_research.md) for the
verified tester state, terminology, fetch-status meanings, UI/SCPI workflow,
and recommended ML dataset schema.
