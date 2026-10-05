# LitePoint IQgig-5G SCPI research and failure-data plan

## Verified tester and interfaces

The connected tester identified itself as:

```text
LitePoint,IQGIG-5GB,IQ1404A9031,1.24.0
```

Its built-in SCPI reference is revision `1.24.0.288143`. The command/control
socket is TCP `192.168.100.254:24000`. Messages and responses are ASCII and end
with a line feed. Do not attempt to read a response after a non-query command.

The dashboard's Trace Tool can record `GUI` or `EXT` traffic. `EXT` is the right
source for validating Python automation. The dashboard and an external client
must not attempt to control the same session concurrently.

## What was safely verified

- `*IDN?` works both in the dashboard SCPI Console and over TCP port 24000.
- `SYST:ERR:ALL?` returned `0,"No error"` while the dashboard still displayed
  an analysis failure. Therefore, the red dashboard analysis state is not the
  same data source as the SCPI system error queue.
- A deliberately invalid, non-RF header (`SYST:THIS_IS_NOT_A_COMMAND`) produced:

```text
-100,"Command error; 01:01:00020031; SYS; CHAN1; N/A; Command not recognized: SYST:THIS_IS_NOT_A_COMMAND"
```

- The Trace Tool in `EXT` mode recorded the identity query and the error-query
  response, including timestamps.
- A read-only existing-result query,
  `CHAN1;5G;FETC:SEGM1:TXQ:STR1:CC1:EVM?`, returned
  `-33,9.91E+37`. Status `-33` is `RESULT_UNAVAILABLE`; `9.91E+37` is a
  non-physical sentinel and must not be treated as EVM training data.
- The dashboard's existing analysis error was:

```text
Analysis: Incorrect component carrier frequency or frequency offsets as specified: 1, 4
```

## Current tester state observed in the UI

These are observations, not settings applied by this project:

- Channel: `CHAN1`, technology: `5G`, direction shown as uplink.
- Center frequency: `27925 MHz`.
- VSA reference level: `10 dBm`; sample rate: `2457.6 MHz`; capture length:
  `2 ms`; trigger source: immediate.
- NR: FR2-style configuration, numerology `3`, bandwidth `50 MHz`, CC1 enabled,
  256-QAM in the SCPI history, TDD, relative carrier-frequency mode.
- Slot detection: threshold `-20 dB`, gap `50 us`, first-slot acquisition,
  frequency search off, continuous signal, acquire one component carrier.
- VSG1 was already playing a waveform at `27925 MHz`, power `-20 dBm`, with
  `RF(on)` selected. The read-only exploration did not enable or disable it.

## The two failure channels

### 1. SCPI/system error queue

Use `SYST:ERR:ALL?` immediately after a failed command. The response contains:

- a standard SCPI-family code such as `-100`;
- a LitePoint hexadecimal/subsystem identifier such as `01:01:00020031`;
- module/channel context (`SYS`, `CHAN1`, and sometimes a resource);
- a human-readable detail string.

Reading the error queue consumes returned entries. Log the response before any
other recovery step. Relevant families include command errors (`-100` range),
execution errors (`-200` range), device/system errors (`-300` range), query
errors (`-400` range), and event/status entries (`-500` and below).

### 2. Measurement fetch status

Calculation and fetch are separate operations. `CALCulate...` computes a
measurement; `FETCh...?...` returns it. A numeric measurement is not valid just
because a response arrived. Fetch responses carry a status code that must be
stored independently from the numeric payload.

Important status codes from the tester's built-in reference:

| Code | Meaning | Dataset interpretation |
| ---: | --- | --- |
| 14 | Partial data | warning; result only partly valid |
| 13 | Signal acquisition off | warning; timing validity undetermined |
| 12 | Unreliable result | warning |
| 11 | Signal type mismatch | warning; validity undetermined |
| 3 | Analysis interval limited | warning |
| 2 | Limit not defined | valid result; no pass/fail limit |
| 1 | Limit fail | valid measurement that failed a limit |
| 0 | Result OK | valid result |
| -1 | Calculation not defined | fetch issued before matching calculation |
| -2 | Calculation out of range | invalid calculation parameter or length |
| -3 | Calculation pending | synchronization/polling issue |
| -11 | No capture | capture missing |
| -12 | Capture timeout | trigger/signal/timing failure |
| -13 | Invalid capture | capture property or sample-rate mismatch |
| -21 | Analysis failed | waveform not recognized |
| -22 | Acquisition failed | frame/slot acquisition failed |
| -31 | Signal dimension unavailable | missing signal/stream/CC |
| -33 | Result unavailable | unsupported result for this calculation |
| -41 | Invalid analysis configuration | unsupported/inapplicable config |
| -111 | Analysis error | analysis engine error |
| -225 | Out of memory | calculation allocation failure |

## Terminology that matters

- **VSG** - vector signal generator. Loads an IQ waveform and transmits it.
  `RF(on)` is a real radiating/output state and is not a harmless UI toggle.
- **VSA** - vector signal analyzer. Captures complex I/Q samples and feeds the
  measurement engine.
- **ROUT** - maps physical RF connectors (for example `RF1A`) to resources such
  as `VSG1` and `VSA1`.
- **CC** - component carrier. Carrier aggregation can analyze multiple CCs.
- **FR2** - 5G frequency range above 24.25 GHz. The observed 27.925 GHz setup is
  in FR2.
- **Numerology** - subcarrier-spacing family. Numerology 3 corresponds to
  120 kHz subcarrier spacing in normal NR operation.
- **RB** - resource block, 12 adjacent OFDM subcarriers. RB offset and duration
  describe occupied placement inside a channel.
- **DMRS** - demodulation reference signal used for channel estimation and
  coherent demodulation.
- **PTRS** - phase-tracking reference signal used to track phase noise, which is
  especially important at mmWave frequencies.
- **SRS** - sounding reference signal used to characterize the uplink channel.
- **EVM** - error vector magnitude: distance between measured and ideal
  constellation points, normally reported as percent or dB. Lower is better.
- **ACLR** - adjacent-channel leakage ratio: wanted-channel power versus leakage
  into adjacent channels. Higher magnitude separation is better.
- **SEM** - spectrum emission mask: pass/fail limits across frequency offsets.
- **OBW** - occupied bandwidth containing a configured percentage (commonly 99%)
  of integrated signal power.
- **CCDF** - complementary cumulative distribution function, showing how often
  instantaneous power exceeds average power; useful for crest factor/PAPR.
- **Reference level (RLEV)** - expected VSA input ceiling/range. Too low risks
  overload/clipping; too high wastes dynamic range and can hide weak details.
- **Trigger** - condition that starts capture. Immediate triggering is simple;
  edge/level/external triggers can cause timeout or timing-offset failures.
- **Slot acquisition** - locating NR slot boundaries before demodulation. It is
  essential for standards-aligned TDD measurements.
- **Tracking** - correction of amplitude, phase, symbol clock, and channel
  estimate drift before calculating metrics. Settings affect both result values
  and reproducibility.

## UI-to-SCPI workflow

1. Select channel and technology (`CHAN1;5G`).
2. Route physical ports to VSG/VSA resources.
3. Load a waveform, configure power, and deliberately control RF output.
4. Configure VSA frequency, reference level, sample rate, capture duration, and
   trigger.
5. Configure NR direction, frequency range, CCs, numerology, bandwidth, RBs,
   DMRS/PTRS/SRS, slot format, acquisition, and tracking.
6. Capture (`VSA1;INIT`) and synchronize with `*OPC?` when required.
7. Calculate (`CALCulate...`) and then fetch (`FETCh...?...`).
8. Store the fetch status separately from measurements.
9. On any failure, store `SYST:ERR:ALL?`, command trace, tester identity/software,
   routing, RF state, capture settings, analysis settings, and timestamps.

## Recommended ML record

One experiment should have a stable `run_id` and contain:

- tester model, serial, software and SCPI-reference revisions;
- complete ordered command/response trace with UTC timestamps and latency;
- VSG/VSA/ROUT state, waveform path/hash, RF frequency and power;
- cable/path-loss table and calibration/warm-up metadata;
- NR configuration (direction, FR, CC count, numerology, bandwidth, modulation,
  RB/DMRS/PTRS/SRS/slot configuration);
- capture/trigger/reference-level/sample-rate settings;
- raw fetch response, parsed fetch status, units and measurement vector;
- raw SCPI error response and parsed family/detail;
- expected fault injection, observed failure label, and operator notes.

Never train directly on a response after discarding its status code. That turns
invalid placeholder numbers into apparently valid targets.

## Safe command-line examples

```powershell
python tools/litepoint_scpi.py identify

python tools/litepoint_scpi.py --output data/scpi_events.jsonl query "*IDN?" `
  --label instrument_identity

python tools/litepoint_scpi.py --output data/scpi_events.jsonl `
  reproduce-command-error
```

For a fetch-status probe, use an exact query from revision `1.24.0.288143` and
label the expected precondition, for example "no capture" or "calculation not
run." Do not guess command mnemonics. Validate them in the built-in SCPI HTML
reference first.

## Safe next experiments

Start with faults that do not transmit RF or risk hardware:

1. Undefined header (`-100`, command parser).
2. Wrong parameter count/type/range on a non-RF analysis configuration command.
3. Fetch before calculate (`-1` fetch status).
4. Calculate/fetch with no capture (`-11`).
5. Analysis configuration mismatch (`-41`) using a saved capture file.
6. Sample-rate mismatch (`-13`) using a copied capture file.

Use saved captures for most data generation. They allow repeatable fault
injection without repeatedly keying the VSG or depending on changing cables,
antennas, or DUT state.
